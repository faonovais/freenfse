"""Emissão, reconciliação, consulta, cancelamento e DANFSe da NFS-e.

Princípios (nesta ordem):

1. **Nunca emitir duas vezes a mesma nota.** Depois de um envio sem resultado claro (timeout,
   5xx), a nota fica "incerta" e a única ação automática é *consultar* a Sefin. O reenvio só
   acontece por pedido explícito e, mesmo assim, a biblioteca consulta antes de enviar.
2. **O estado gravado manda.** Se o processo cair no meio, a situação da nota é recuperada do
   registro de emissões (`EmissaoDps`), que é confirmado antes de cada envio.
3. **A situação só muda por `nfse_estados.transicionar`**, e só depois de a Sefin confirmar
   (cancelamento e substituição mudam a nota apenas quando o evento aparece).
"""

import datetime as dt
import hashlib
import logging
from dataclasses import dataclass

from django.utils import timezone
from django_tenants.utils import schema_context
from lxml import etree

from core.models import Empresa, LogAuditoria
from core.services import auditoria
from fiscal import gateway
from fiscal.models import (
    Certificado,
    EventoNfse,
    Nfse,
    ParametrosFiscais,
)
from fiscal.persistencia.fabrica import criar_persistencia
from fiscal.persistencia.modelos import EmissaoDps, EventoFiscal
from fiscal.services import bloqueios as servico_bloqueios
from fiscal.services import mensagens_sefin
from fiscal.services import nfse as servico_nfse
from fiscal.services.certificado import abrir_em_memoria
from fiscal.services.nfse_estados import transicionar

logger = logging.getLogger(__name__)

NS = "{http://www.sped.fazenda.gov.br/nfse}"
EVENTOS_DE_CANCELAMENTO = {"101101", "105104", "305101"}
EVENTO_DE_SUBSTITUICAO = "105102"
ENVIANDO_PRESO_APOS = dt.timedelta(minutes=10)
# Sem nenhum rastro no registro de emissões, "enviando" costuma ser só fila (várias emissões da
# mesma empresa esperam a trava): só depois deste prazo a nota volta a rascunho.
ENVIANDO_SEM_RASTRO_APOS = dt.timedelta(minutes=30)
ESPERA_DA_TRAVA_NA_CONSULTA = 5.0
ESPERA_DA_TRAVA_NO_CANCELAMENTO = 15.0

S = Nfse.Situacao
E = EmissaoDps.Situacao


class ErroDeEmissao(Exception):
    """Operação recusada por algo que o usuário pode entender e corrigir; a mensagem é didática."""


class BloqueioDeEmissao(ErroDeEmissao):
    """A empresa não está pronta para emitir; `bloqueios` traz cada motivo e a tela para ajustar."""

    def __init__(self, bloqueios):
        """Guarda os bloqueios e junta as mensagens."""
        super().__init__(" ".join(b.mensagem for b in bloqueios))
        self.bloqueios = bloqueios


class CancelamentoRecusado(ErroDeEmissao):
    """A Sefin recusou o cancelamento; `erros` traz código, explicação e o que fazer."""

    def __init__(self, erros):
        """Guarda os erros já traduzidos."""
        super().__init__(mensagens_sefin.resumo(erros))
        self.erros = erros


class CancelamentoIncerto(ErroDeEmissao):
    """Não foi possível confirmar o cancelamento: a nota segue autorizada até a Sefin confirmar."""


@dataclass(frozen=True)
class ResumoDaReconciliacao:
    """Contagem do que a rotina periódica fez, para log e testes."""

    empresas: int = 0
    autorizadas: int = 0
    ainda_incertas: int = 0
    sem_resposta: int = 0
    soltas: int = 0
    substituicoes_confirmadas: int = 0


def opcoes_de_execucao():
    """Transporte, pausa e relógio das operações. Ponto de troca dos testes (Sefin simulada)."""
    return {"transporte": None, "pausa": None, "relogio": gateway.relogio_utc}


# -- contexto ----------------------------------------------------------------------------


def contexto_fiscal(empresa, *, nfse_id=None, espera_da_trava=None):
    """Contexto da empresa ativa: certificado aberto **só em memória** e persistência do schema."""
    parametros = ParametrosFiscais.obter()
    certificado = Certificado.objects.first()
    if certificado is None:
        raise BloqueioDeEmissao(servico_bloqueios.verificar_prontidao())
    try:
        a1 = abrir_em_memoria(certificado)
    except Exception:  # noqa: BLE001 - qualquer falha ao abrir vira mensagem; nada vaza
        raise ErroDeEmissao(
            "Não foi possível abrir o certificado digital. Envie-o novamente em Certificado A1."
        ) from None
    opcoes = opcoes_de_execucao()
    argumentos = {}
    if espera_da_trava is not None:
        argumentos["espera_da_trava"] = espera_da_trava
    return gateway.ContextoFiscal(
        cnpj=empresa.cnpj,
        ambiente_producao=parametros.ambiente == ParametrosFiscais.Ambiente.PRODUCAO,
        certificado=a1,
        persistencia=criar_persistencia(
            interessado=empresa.cnpj,
            nfse_id=nfse_id,
            relogio=opcoes["relogio"],
            pausa=opcoes["pausa"],
            **argumentos,
        ),
        transporte=opcoes["transporte"],
        pausa=opcoes["pausa"],
        relogio=opcoes["relogio"],
    )


# -- solicitar e executar ----------------------------------------------------------------


def solicitar_emissao(nfse, *, usuario, request=None, empresa=None):
    """Valida e coloca a nota em "enviando". O envio acontece na fila (`executar_emissao`).

    Conferências: empresa pronta (certificado, município, convênio), situação da nota, e — se
    a nota ainda vai receber um número novo — nenhuma outra nota da série com resultado
    pendente (numerar de novo por cima de uma nota incerta poderia duplicar a emissão).
    """
    pendencias = servico_bloqueios.verificar_prontidao()
    if pendencias:
        raise BloqueioDeEmissao(pendencias)
    if nfse.situacao not in (S.RASCUNHO, S.REJEITADA, S.INCERTA):
        raise ErroDeEmissao(
            f"Uma nota {nfse.get_situacao_display().lower()} não pode ser enviada de novo."
        )
    parametros = ParametrosFiscais.obter()
    if nfse.ambiente != parametros.ambiente:
        if nfse.id_dps:
            raise ErroDeEmissao(
                "O ambiente de emissão mudou desde a primeira tentativa desta nota. Crie uma "
                "nova nota no ambiente atual."
            )
        nfse.ambiente = parametros.ambiente
        nfse.save(update_fields=["ambiente", "atualizado_em"])
    if not nfse.id_dps:
        outras = EmissaoDps.objects.filter(
            serie=nfse.serie, situacao__in=[E.ENVIADA, E.INCERTA]
        ).exclude(nfse=nfse)
        if outras.exists():
            numeros = ", ".join(str(n) for n in outras.values_list("numero", flat=True))
            raise ErroDeEmissao(
                f"Há nota(s) da série {nfse.serie} sem resultado confirmado (DPS nº {numeros}). "
                "Aguarde a conferência com a Sefin antes de emitir outra: numerar por cima "
                "poderia duplicar uma nota."
            )
    transicionar(nfse, S.ENVIANDO, motivo="Emissão solicitada", usuario=usuario)
    auditoria.registrar(
        LogAuditoria.Acao.NFSE_EMISSAO_SOLICITADA,
        request=request,
        usuario=usuario,
        empresa=empresa,
        alvo=f"nfse:{nfse.pk}",
        detalhes={"serie": nfse.serie, "ambiente": nfse.ambiente},
    )
    return nfse


def executar_emissao(empresa, nfse_id):
    """Corpo da tarefa de emissão (já no schema da empresa). Idempotente.

    Reentregar a tarefa não reenvia nada: se a nota não está "enviando", não há o que fazer; se
    a nota já tem DPS no registro, a mesma DPS é reaproveitada e a biblioteca consulta a Sefin
    antes de qualquer novo envio. `TravaOcupadaErro` sobe para a tarefa reagendar.
    """
    nfse = Nfse.objects.get(pk=nfse_id)
    if nfse.situacao != S.ENVIANDO:
        return nfse.situacao
    parametros = ParametrosFiscais.obter()
    if nfse.ambiente != parametros.ambiente:
        return _voltar_ao_rascunho(
            nfse, "O ambiente de emissão foi alterado enquanto a nota esperava. Envie de novo."
        )
    try:
        contexto = contexto_fiscal(empresa, nfse_id=nfse.pk)
    except ErroDeEmissao as erro:
        return _voltar_ao_rascunho(nfse, str(erro))

    existente = EmissaoDps.objects.filter(nfse=nfse).order_by("-id").first()
    dados = servico_nfse.dados_da_dps(
        nfse, empresa=empresa, parametros=parametros, numero=existente.numero if existente else None
    )
    resultado = gateway.emitir(contexto, dados)
    return aplicar_resultado(empresa, nfse, resultado, contexto)


def _voltar_ao_rascunho(nfse, mensagem):
    transicionar(nfse, S.RASCUNHO, motivo="Nada foi enviado à Sefin", mensagem=mensagem)
    return S.RASCUNHO


# -- aplicar o desfecho ------------------------------------------------------------------


def _dados_do_registro(id_dps):
    registro = EmissaoDps.objects.filter(id_dps=id_dps).first() if id_dps else None
    return {} if registro is None else {"numero_dps": registro.numero, "serie": registro.serie}


def aplicar_resultado(empresa, nfse, resultado, contexto):
    """Grava no `Nfse` o desfecho da tentativa (autorizada, rejeitada, incerta…)."""
    if nfse.situacao != S.ENVIANDO:
        return nfse.situacao
    if resultado.estado == gateway.ESTADO_AUTORIZADA:
        return _autorizar(empresa, nfse, resultado, contexto)
    if resultado.estado == gateway.ESTADO_REJEITADA:
        erros = [
            mensagens_sefin.explicar(e["codigo"], e["descricao"], e["complemento"])
            for e in resultado.erros
        ]
        return _rejeitar(empresa, nfse, resultado.id_dps, erros, resultado.leiaute)
    if resultado.estado == gateway.ESTADO_INCERTA:
        return _marcar_incerta(empresa, nfse, resultado.id_dps, resultado.leiaute)
    if resultado.estado == gateway.ESTADO_NAO_ENVIADA:
        return _voltar_ao_rascunho(nfse, resultado.mensagem or "A nota não pôde ser montada.")
    return _resolver_pelo_registro(empresa, nfse, resultado.leiaute, contexto)


def _autorizar(empresa, nfse, resultado, contexto):
    raiz = etree.fromstring(resultado.xml_nfse)
    numero_nfse = (raiz.findtext(f".//{NS}nNFSe") or "").strip()
    processada = raiz.findtext(f".//{NS}dhProc")
    try:
        emitida_em = dt.datetime.fromisoformat(processada) if processada else timezone.now()
    except ValueError:
        emitida_em = timezone.now()
    transicionar(
        nfse,
        S.AUTORIZADA,
        motivo="Autorizada pela Sefin",
        id_dps=resultado.id_dps,
        chave=resultado.chave,
        numero_nfse=numero_nfse,
        emitida_em=emitida_em,
        xml_dps=resultado.xml_dps,
        xml_nfse=resultado.xml_nfse,
        hash_xml_nfse=hashlib.sha256(resultado.xml_nfse).hexdigest(),
        leiaute=resultado.leiaute,
        erros=[],
        mensagem="",
        **_dados_do_registro(resultado.id_dps),
    )
    auditoria.registrar(
        LogAuditoria.Acao.NFSE_AUTORIZADA,
        usuario=nfse.criado_por,
        empresa=empresa,
        alvo=f"nfse:{nfse.pk}",
        detalhes={"chave": resultado.chave, "leiaute": resultado.leiaute},
    )
    if nfse.substitui_id:
        _confirmar_substituicao(empresa, nfse.substitui, contexto)
    return S.AUTORIZADA


def _rejeitar(empresa, nfse, id_dps, erros, leiaute):
    transicionar(
        nfse,
        S.REJEITADA,
        motivo="Rejeitada pela Sefin",
        id_dps=id_dps or nfse.id_dps,
        erros=erros,
        mensagem=mensagens_sefin.resumo(erros),
        leiaute=leiaute,
        **_dados_do_registro(id_dps),
    )
    auditoria.registrar(
        LogAuditoria.Acao.NFSE_REJEITADA,
        usuario=nfse.criado_por,
        empresa=empresa,
        alvo=f"nfse:{nfse.pk}",
        detalhes={"codigos": [e["codigo"] for e in erros]},
    )
    return S.REJEITADA


def _marcar_incerta(empresa, nfse, id_dps, leiaute):
    transicionar(
        nfse,
        S.INCERTA,
        motivo="Resultado incerto",
        id_dps=id_dps or nfse.id_dps,
        leiaute=leiaute,
        mensagem=(
            "A Sefin não confirmou se recebeu esta nota (falha de comunicação). O sistema "
            "consulta a Sefin automaticamente e não envia de novo antes de confirmar. Não "
            "emita esta nota outra vez por conta própria."
        ),
        **_dados_do_registro(id_dps),
    )
    auditoria.registrar(
        LogAuditoria.Acao.NFSE_INCERTA,
        usuario=nfse.criado_por,
        empresa=empresa,
        alvo=f"nfse:{nfse.pk}",
        detalhes={"id_dps": id_dps},
    )
    return S.INCERTA


def _resolver_pelo_registro(empresa, nfse, leiaute, contexto):
    """Falha sem desfecho claro: o registro de emissões (confirmado antes do envio) decide."""
    registro = EmissaoDps.objects.filter(nfse=nfse).order_by("-id").first()
    if registro is None or registro.situacao == E.PENDENTE:
        return _voltar_ao_rascunho(
            nfse, "Não foi possível concluir o envio e nada chegou à Sefin. Envie de novo."
        )
    if registro.situacao in (E.ENVIADA, E.INCERTA):
        return _marcar_incerta(empresa, nfse, registro.id_dps, leiaute)
    if registro.situacao == E.REJEITADA:
        erros = [
            mensagens_sefin.explicar(e.get("codigo"), e.get("descricao"), e.get("complemento"))
            for e in registro.erros or []
        ]
        return _rejeitar(empresa, nfse, registro.id_dps, erros, leiaute)
    resultado = gateway.reconciliar(contexto, registro.id_dps)
    if resultado.estado == gateway.ESTADO_AUTORIZADA:
        return _autorizar(empresa, nfse, resultado, contexto)
    return _marcar_incerta(empresa, nfse, registro.id_dps, leiaute)


# -- reconciliação -----------------------------------------------------------------------


def reconciliar_nota(empresa, nfse, *, espera_da_trava=ESPERA_DA_TRAVA_NA_CONSULTA):
    """Consulte a Sefin sobre uma nota incerta (ou presa em "enviando"); nunca reenvia.

    Devolve a situação resultante. `TravaOcupadaErro` se há outra operação em andamento.
    """
    if not nfse.id_dps:
        return nfse.situacao
    contexto = contexto_fiscal(empresa, nfse_id=nfse.pk, espera_da_trava=espera_da_trava)
    resultado = gateway.reconciliar(contexto, nfse.id_dps)
    if nfse.situacao == S.INCERTA:
        if resultado.estado != gateway.ESTADO_AUTORIZADA:
            return nfse.situacao
        transicionar(nfse, S.ENVIANDO, motivo="Conferência encontrou a nota na Sefin")
    if nfse.situacao != S.ENVIANDO:
        return nfse.situacao
    if resultado.estado == gateway.ESTADO_AUTORIZADA:
        return _autorizar(empresa, nfse, resultado, contexto)
    if resultado.estado == gateway.ESTADO_INCERTA:
        return _marcar_incerta(empresa, nfse, nfse.id_dps, resultado.leiaute)
    return nfse.situacao


def reconciliar_pendentes(agora=None, *, espera_da_trava=ESPERA_DA_TRAVA_NA_CONSULTA):
    """Rotina periódica: confere as notas incertas e presas de todas as empresas ativas.

    Só consulta a Sefin; nada é reenviado. Notas "enviando" há mais de 10 minutos são notas cujo
    processo caiu: o registro de emissões diz o que houve. Também confirma substituições cuja
    nova nota já foi autorizada mas o evento ainda não foi visto.
    """
    agora = agora or timezone.now()
    totais = {"empresas": 0, "autorizadas": 0, "ainda_incertas": 0, "sem_resposta": 0, "soltas": 0}
    substituicoes = 0
    for empresa in Empresa.objects.filter(ativo=True):
        with schema_context(empresa.schema_name):
            if not Certificado.objects.exists():
                continue
            totais["empresas"] += 1
            for nfse in _pendentes(agora):
                try:
                    antes = nfse.situacao
                    depois = _conferir(empresa, nfse, espera_da_trava, agora)
                except gateway.TravaOcupadaErro:
                    continue  # outra operação em andamento; a próxima rodada tenta de novo
                except Exception:
                    logger.exception("Falha ao reconciliar a nota %s", nfse.pk)
                    totais["sem_resposta"] += 1
                    continue
                if depois == S.AUTORIZADA:
                    totais["autorizadas"] += 1
                elif depois == S.INCERTA:
                    totais["ainda_incertas"] += 1
                elif depois == S.RASCUNHO and antes == S.ENVIANDO:
                    totais["soltas"] += 1
            substituicoes += _confirmar_substituicoes_pendentes(empresa, espera_da_trava)
    return ResumoDaReconciliacao(substituicoes_confirmadas=substituicoes, **totais)


def _pendentes(agora):
    incertas = list(Nfse.objects.filter(situacao=S.INCERTA))
    presas = list(
        Nfse.objects.filter(situacao=S.ENVIANDO, atualizado_em__lt=agora - ENVIANDO_PRESO_APOS)
    )
    return [*incertas, *presas]


def _conferir(empresa, nfse, espera_da_trava, agora):
    if nfse.situacao != S.ENVIANDO:
        return reconciliar_nota(empresa, nfse, espera_da_trava=espera_da_trava)
    registro = EmissaoDps.objects.filter(nfse=nfse).order_by("-id").first()
    sem_rastro = registro is None or registro.situacao == E.PENDENTE
    if sem_rastro and agora - nfse.atualizado_em < ENVIANDO_SEM_RASTRO_APOS:
        return nfse.situacao  # provavelmente só esperando a vez na fila
    # Presa em "enviando": o registro de emissões diz o que houve e, se a Sefin pode ter
    # processado a DPS, a conferência acontece já nesta rodada (sem reenviar nada).
    contexto = contexto_fiscal(empresa, nfse_id=nfse.pk, espera_da_trava=espera_da_trava)
    leiaute = gateway.leiaute_em_vigor(contexto.ambiente_producao, contexto.relogio)
    situacao = _resolver_pelo_registro(empresa, nfse, leiaute, contexto)
    if situacao != S.INCERTA:
        return situacao
    nfse.refresh_from_db()
    return reconciliar_nota(empresa, nfse, espera_da_trava=espera_da_trava)


def _confirmar_substituicoes_pendentes(empresa, espera_da_trava):
    confirmadas = 0
    originais = Nfse.objects.filter(
        situacao=S.AUTORIZADA, substitutas__situacao=S.AUTORIZADA
    ).distinct()
    for original in originais:
        try:
            contexto = contexto_fiscal(empresa, espera_da_trava=espera_da_trava)
            sincronizar_eventos(contexto, original)
        except Exception:
            logger.exception("Falha ao confirmar a substituição da nota %s", original.pk)
            continue
        original.refresh_from_db()
        confirmadas += original.situacao == S.SUBSTITUIDA
    return confirmadas


# -- eventos, consulta e substituição ----------------------------------------------------


def sincronizar_eventos(contexto, nfse):
    """Traz os eventos da nota da Sefin e atualiza a situação **só se o evento existir**."""
    eventos = gateway.listar_eventos(contexto, nfse.chave)
    guardados = {
        (e.tipo_evento, e.identificador): e
        for e in EventoFiscal.objects.filter(modelo="nfse", chave=nfse.chave)
    }
    for evento in eventos:
        origem = guardados.get((evento["tipo_evento"], evento["identificador"]))
        EventoNfse.objects.get_or_create(
            nfse=nfse,
            tipo_evento=evento["tipo_evento"],
            identificador=evento["identificador"],
            defaults={
                "descricao": evento["descricao"][:255],
                "registrado_em": evento["data_evento"],
                "xml": bytes(origem.xml) if origem else None,
                "hash_xml": origem.sha256 if origem else "",
            },
        )
    tipos = {e["tipo_evento"] for e in eventos}
    if nfse.situacao == S.AUTORIZADA:
        if tipos & EVENTOS_DE_CANCELAMENTO:
            transicionar(nfse, S.CANCELADA, motivo="Cancelamento confirmado pela Sefin")
        elif EVENTO_DE_SUBSTITUICAO in tipos:
            transicionar(nfse, S.SUBSTITUIDA, motivo="Substituição confirmada pela Sefin")
    return nfse


def _confirmar_substituicao(empresa, original, contexto):
    """Depois da nota nova, confere se a Sefin registrou a substituição da original."""
    try:
        sincronizar_eventos(contexto, original)
    except gateway.ErroDeConsultaFiscal, gateway.RejeicaoDeEventoErro:
        logger.warning("Substituição da nota %s ainda não confirmada.", original.pk)
        return
    if original.situacao == S.SUBSTITUIDA:
        auditoria.registrar(
            LogAuditoria.Acao.NFSE_SUBSTITUIDA,
            usuario=original.criado_por,
            empresa=empresa,
            alvo=f"nfse:{original.pk}",
            detalhes={"chave": original.chave},
        )


def consultar(empresa, nfse):
    """Atualiza a nota com o que a Sefin tem (XML e eventos). Exige uma chave."""
    if not nfse.chave:
        raise ErroDeEmissao("Esta nota ainda não foi autorizada: não há o que consultar na Sefin.")
    contexto = contexto_fiscal(
        empresa, nfse_id=nfse.pk, espera_da_trava=ESPERA_DA_TRAVA_NA_CONSULTA
    )
    try:
        gateway.consultar_nota(contexto, nfse.chave)
        sincronizar_eventos(contexto, nfse)
    except gateway.ErroDeConsultaFiscal as erro:
        raise ErroDeEmissao(str(erro)) from None
    except gateway.RejeicaoDeEventoErro as erro:
        raise ErroDeEmissao(
            mensagens_sefin.resumo(
                [
                    mensagens_sefin.explicar(e["codigo"], e["descricao"], e["complemento"])
                    for e in erro.erros
                ]
            )
        ) from None
    nfse.refresh_from_db()
    return nfse


# -- cancelamento ------------------------------------------------------------------------


def cancelar(empresa, nfse, *, codigo_motivo, justificativa, usuario, request=None):
    """Pede o cancelamento à Sefin. A nota só vira "cancelada" depois do evento confirmado."""
    if nfse.situacao != S.AUTORIZADA:
        raise ErroDeEmissao(
            "Só é possível cancelar uma nota autorizada. "
            f"Esta está {nfse.get_situacao_display().lower()}."
        )
    if int(codigo_motivo or 0) not in gateway.MOTIVOS_DE_CANCELAMENTO:
        raise servico_nfse.ErroDeNota({"codigo_motivo": "Escolha o motivo do cancelamento."})
    justificativa = (justificativa or "").strip()
    if not 15 <= len(justificativa) <= 255:
        raise servico_nfse.ErroDeNota(
            {"justificativa": "Explique o motivo do cancelamento em 15 a 255 caracteres."}
        )
    contexto = contexto_fiscal(empresa, espera_da_trava=ESPERA_DA_TRAVA_NO_CANCELAMENTO)
    alvo = f"nfse:{nfse.pk}"
    try:
        gateway.cancelar(contexto, nfse.chave, int(codigo_motivo), justificativa)
    except gateway.TravaOcupadaErro:
        raise ErroDeEmissao(
            "Há outra operação fiscal em andamento nesta empresa. Tente de novo em instantes."
        ) from None
    except gateway.DadosInvalidosErro as erro:
        raise servico_nfse.ErroDeNota({"justificativa": str(erro)}) from None
    except gateway.RejeicaoDeEventoErro as recusa:
        erros = [
            mensagens_sefin.explicar(e["codigo"], e["descricao"], e["complemento"])
            for e in recusa.erros
        ]
        auditoria.registrar(
            LogAuditoria.Acao.NFSE_CANCELAMENTO_RECUSADO,
            request=request,
            usuario=usuario,
            empresa=empresa,
            alvo=alvo,
            detalhes={"codigos": [e["codigo"] for e in erros]},
        )
        if any(e["codigo"] == "E0840" for e in erros):
            sincronizar_eventos(contexto, nfse)  # já estava cancelada na Sefin
        raise CancelamentoRecusado(erros) from None
    except gateway.OperacaoIncertaErro:
        auditoria.registrar(
            LogAuditoria.Acao.NFSE_CANCELAMENTO_RECUSADO,
            request=request,
            usuario=usuario,
            empresa=empresa,
            alvo=alvo,
            detalhes={"incerto": True},
        )
        raise CancelamentoIncerto(
            "Não foi possível confirmar o cancelamento com a Sefin. A nota continua autorizada "
            "aqui até a confirmação. Consulte a nota em alguns minutos antes de tentar de novo."
        ) from None

    sincronizar_eventos(contexto, nfse)
    nfse.refresh_from_db()
    if nfse.situacao != S.CANCELADA:
        raise CancelamentoIncerto(
            "A Sefin respondeu, mas o evento de cancelamento ainda não apareceu. A nota "
            "continua autorizada aqui. Consulte a nota em alguns minutos."
        )
    auditoria.registrar(
        LogAuditoria.Acao.NFSE_CANCELADA,
        request=request,
        usuario=usuario,
        empresa=empresa,
        alvo=alvo,
        detalhes={"chave": nfse.chave, "motivo": int(codigo_motivo)},
    )
    return nfse


# -- DANFSe ------------------------------------------------------------------------------


def gerar_danfse(empresa, nfse):
    """PDF do DANFSe, gerado na hora (não é guardado). Cancelada/substituída leva marca d'água."""
    if nfse.situacao not in (S.AUTORIZADA, S.CANCELADA, S.SUBSTITUIDA):
        raise ErroDeEmissao("O DANFSe só existe para nota autorizada, cancelada ou substituída.")
    contexto = contexto_fiscal(
        empresa, nfse_id=nfse.pk, espera_da_trava=ESPERA_DA_TRAVA_NA_CONSULTA
    )
    if (
        nfse.situacao != S.AUTORIZADA
        and not EventoFiscal.objects.filter(modelo="nfse", chave=nfse.chave).exists()
    ):
        sincronizar_eventos(contexto, nfse)  # a marca d'água depende dos eventos guardados
    try:
        return gateway.gerar_danfse(contexto, nfse.chave)
    except gateway.DadosInvalidosErro as erro:
        raise ErroDeEmissao(str(erro)) from None
