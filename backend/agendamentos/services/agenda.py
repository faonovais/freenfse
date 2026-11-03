"""Agendamentos: regras de negócio, suspensão e reativação, e o dispatcher que gera rascunhos.

Política (D12, D17; ver ADR 0006):

- Um agendamento só **gera rascunhos**. Nada é emitido nem apagado sozinho.
- **Uma data, no máximo um rascunho.** O dispatcher trava a linha do agendamento
  (`SELECT … FOR UPDATE SKIP LOCKED`: quem chega em segundo pula, não espera) e a tabela de
  execuções tem `UNIQUE (agendamento, data_execucao)`. As duas proteções são independentes.
- **Falha não conta.** Se o rascunho não pôde ser gerado, a data fica registrada como falha, o
  contador de execuções não anda e o agendamento tenta de novo na **próxima** data da série.
- **Sem disparo retroativo.** Ao criar, editar ou reativar, vale só a próxima data **futura**: o que
  passou durante uma suspensão não é gerado depois. Se o sistema ficou fora do ar, uma data só
  é executada com até `tolerancia()` de atraso; as mais antigas viram um aviso, não rascunhos.
- Responsável sem vínculo ativo ou sem `nfse.emitir` **suspende** o agendamento e avisa os
  administradores.
"""

import datetime as dt
import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction

from agendamentos import recorrencia
from agendamentos.models import Agendamento, ExecucaoAgendamento, OrigemNfse
from agendamentos.services import avisos, modelos
from core.models import LogAuditoria
from core.services import acesso, auditoria
from fiscal.services.nfse import ErroDeNota

logger = logging.getLogger(__name__)

A = Agendamento.Situacao
E = ExecucaoAgendamento.Situacao

# Resultados de `processar` (além de `None`: nada a fazer ou outro processo já cuida).
GERADA = "gerada"
FALHOU = "falhou"
PERDIDA = "perdida"
SUSPENSA = "suspensa"
JA_EXECUTADA = "ja_executada"

CAMPOS_DA_REGRA = (
    "frequencia", "intervalo", "dias_semana", "dia_do_mes", "mes", "hora", "data_inicio",
    "data_fim", "max_execucoes",
)  # fmt: skip
TOLERANCIA_MAXIMA_HORAS = 23  # abaixo do menor intervalo (1 dia): no máximo uma data por vez


class ErroDeAgendamento(Exception):
    """Dados ou operação inválidos; `erros` mapeia o campo à mensagem para o usuário."""

    def __init__(self, erros):
        """Aceita um dicionário campo → mensagem ou uma mensagem única (campo `geral`)."""
        if isinstance(erros, str):
            erros = {"geral": erros}
        super().__init__("; ".join(erros.values()))
        self.erros = erros


def tolerancia():
    """Atraso máximo com que uma data ainda é executada (sempre menor que um dia)."""
    horas = min(settings.FREENFSE_AGENDAMENTO_TOLERANCIA_HORAS, TOLERANCIA_MAXIMA_HORAS)
    return dt.timedelta(hours=max(horas, 0))


def regra_do(agendamento):
    """Monte a `Regra` de recorrência do agendamento."""
    return recorrencia.Regra(
        frequencia=agendamento.frequencia,
        hora=agendamento.hora,
        data_inicio=agendamento.data_inicio,
        intervalo=agendamento.intervalo,
        dias_semana=tuple(agendamento.dias_semana or ()),
        dia_do_mes=agendamento.dia_do_mes,
        mes=agendamento.mes,
        data_fim=agendamento.data_fim,
        max_execucoes=agendamento.max_execucoes,
    )


def previa_de_datas(regra, *, executadas, agora, quantidade):
    """As próximas `quantidade` execuções (UTC) depois de `agora`, para a tela mostrar."""
    return recorrencia.proximas_execucoes(
        regra, executadas=executadas, depois_de=agora, quantidade=quantidade
    )


# --- Responsável ---------------------------------------------------------------------------


def verificar_responsavel(usuario_id, empresa):
    """`(usuario, motivo)`: `motivo` é `None` se pode aprovar notas nesta empresa agora."""
    usuario = get_user_model().objects.filter(pk=usuario_id).first()
    if usuario is None:
        return None, "O responsável não existe mais no sistema."
    if not usuario.is_active:
        return usuario, f"O usuário responsável ({usuario.email}) está desativado."
    resolvido = acesso.acesso_a_empresa(usuario, empresa)
    if resolvido is None:
        return usuario, f"O responsável ({usuario.email}) não tem mais vínculo ativo com a empresa."
    if "nfse.emitir" not in resolvido[2]:
        return usuario, f"O responsável ({usuario.email}) não tem mais permissão para emitir notas."
    return usuario, None


# --- Criar, alterar, suspender e reativar -----------------------------------------------------


def _aplicar(agendamento, dados):
    """Aplica `dados` ao agendamento e devolve os campos da regra que mudaram de valor."""
    mudaram = set()
    for campo in ("nome", *CAMPOS_DA_REGRA):
        if campo in dados:
            if campo in CAMPOS_DA_REGRA and getattr(agendamento, campo) != dados[campo]:
                mudaram.add(campo)
            setattr(agendamento, campo, dados[campo])
    return mudaram


def _erros_do_agendamento(agendamento, *, empresa, hoje, checar_inicio, checar_responsavel):
    erros = recorrencia.validar(regra_do(agendamento), hoje=hoje if checar_inicio else None)
    if not (agendamento.nome or "").strip():
        erros["nome"] = "Dê um nome ao agendamento."
    elif (
        Agendamento.objects.filter(nome__iexact=agendamento.nome.strip())
        .exclude(pk=agendamento.pk)
        .exists()
    ):
        erros["nome"] = "Já existe um agendamento com este nome."
    if not agendamento.modelo.ativo:
        erros["modelo"] = f"O modelo “{agendamento.modelo.nome}” está inativo."
    if checar_responsavel:
        _usuario, motivo = verificar_responsavel(agendamento.responsavel_id, empresa)
        if motivo:
            erros["responsavel"] = motivo
    return erros


def salvar(
    dados, *, agendamento=None, modelo=None, responsavel=None, usuario, empresa, agora, request=None
):
    """Cria ou altera um agendamento (já com tipos Python) e calcula a próxima execução.

    `modelo` e `responsavel` (objetos) só vão quando informados/mudados. Levanta
    `ErroDeAgendamento`. Mudar a regra recalcula a próxima execução a partir de **agora**.
    """
    criando = agendamento is None
    if criando:
        agendamento = Agendamento(criado_por_id=usuario.pk, criado_por_email=usuario.email)
    campos_mudados = _aplicar(agendamento, dados)
    mudou_a_regra = criando or bool(campos_mudados)
    mudou_o_responsavel = criando
    if modelo is not None:
        agendamento.modelo = modelo
    if responsavel is not None:
        mudou_o_responsavel = mudou_o_responsavel or agendamento.responsavel_id != responsavel.pk
        agendamento.responsavel_id, agendamento.responsavel_email = (
            responsavel.pk,
            responsavel.email,
        )
    erros = _erros_do_agendamento(
        agendamento,
        empresa=empresa,
        hoje=recorrencia.data_local(agora),
        checar_inicio=criando or "data_inicio" in campos_mudados,
        checar_responsavel=mudou_o_responsavel,
    )
    if erros:
        raise ErroDeAgendamento(erros)

    if mudou_a_regra and agendamento.situacao in (A.ATIVO, A.ENCERRADO):
        proxima = recorrencia.proxima_execucao(
            regra_do(agendamento), executadas=agendamento.execucoes_realizadas, depois_de=agora
        )
        if proxima is None:
            raise ErroDeAgendamento(
                {"geral": "Com estas datas o agendamento não teria nenhuma execução futura."}
            )
        agendamento.proxima_execucao = proxima
        if agendamento.situacao == A.ENCERRADO:  # as datas mudaram e voltou a ter futuro
            agendamento.situacao, agendamento.motivo_situacao = A.ATIVO, ""
    agendamento.save()
    auditoria.registrar(
        LogAuditoria.Acao.AGENDAMENTO_SALVO,
        request=request,
        usuario=usuario,
        empresa=empresa,
        alvo=f"agendamento:{agendamento.pk}",
        detalhes={"criado": criando},
    )
    return agendamento


def suspender(agendamento, *, motivo="", usuario, empresa, request=None):
    """Suspende um agendamento ativo (as datas seguintes não são geradas até reativar)."""
    if agendamento.situacao != A.ATIVO:
        raise ErroDeAgendamento("Só um agendamento ativo pode ser suspenso.")
    agendamento.situacao = A.SUSPENSO
    agendamento.motivo_situacao = (motivo or f"Suspenso por {usuario.email}.")[:300]
    agendamento.proxima_execucao = None
    agendamento.save()
    auditoria.registrar(
        LogAuditoria.Acao.AGENDAMENTO_SUSPENSO,
        request=request,
        usuario=usuario,
        empresa=empresa,
        alvo=f"agendamento:{agendamento.pk}",
    )
    return agendamento


def reativar(agendamento, *, usuario, empresa, agora, request=None):
    """Reativa um agendamento suspenso. Vale **só a próxima data futura**: nada retroativo."""
    if agendamento.situacao != A.SUSPENSO:
        raise ErroDeAgendamento("Só um agendamento suspenso pode ser reativado.")
    _responsavel, motivo = verificar_responsavel(agendamento.responsavel_id, empresa)
    if motivo:
        raise ErroDeAgendamento({"responsavel": f"{motivo} Escolha outro responsável."})
    if not agendamento.modelo.ativo:
        raise ErroDeAgendamento({"modelo": f"O modelo “{agendamento.modelo.nome}” está inativo."})
    proxima = recorrencia.proxima_execucao(
        regra_do(agendamento), executadas=agendamento.execucoes_realizadas, depois_de=agora
    )
    if proxima is None:
        raise ErroDeAgendamento(
            "Não há mais datas futuras neste agendamento. Ajuste a data de fim ou o limite."
        )
    agendamento.situacao, agendamento.motivo_situacao = A.ATIVO, ""
    agendamento.proxima_execucao = proxima
    agendamento.save()
    auditoria.registrar(
        LogAuditoria.Acao.AGENDAMENTO_REATIVADO,
        request=request,
        usuario=usuario,
        empresa=empresa,
        alvo=f"agendamento:{agendamento.pk}",
    )
    return agendamento


# --- Dispatcher ------------------------------------------------------------------------------


def despachar(agora, *, empresa):
    """Executa, na empresa ativa, as datas vencidas. Devolve quantas de cada resultado."""
    totais = {GERADA: 0, FALHOU: 0, PERDIDA: 0, SUSPENSA: 0, JA_EXECUTADA: 0}
    vencidos = list(
        Agendamento.objects.filter(situacao=A.ATIVO, proxima_execucao__lte=agora)
        .order_by("proxima_execucao", "pk")
        .values_list("pk", flat=True)
    )
    for agendamento_id in vencidos:
        # Datas muito atrasadas viram aviso (PERDIDA) e a seguinte já pode estar no prazo.
        for _tentativa in range(2):
            try:
                resultado = processar(agendamento_id, agora=agora, empresa=empresa)
            except Exception:
                logger.exception("Agendamento %s: erro ao despachar.", agendamento_id)
                break
            if resultado in totais:
                totais[resultado] += 1
            if resultado != PERDIDA:
                break
    return totais


def processar(agendamento_id, *, agora, empresa):
    """Executa a data vencida de UM agendamento, se ninguém mais o estiver executando.

    Devolve o resultado (`GERADA`, `FALHOU`, `PERDIDA`, `SUSPENSA`, `JA_EXECUTADA`) ou `None`
    quando não há o que fazer (já executado por outro processo, suspenso, ainda não venceu).
    """
    with transaction.atomic():
        agendamento = (
            Agendamento.objects.select_for_update(skip_locked=True)
            .filter(pk=agendamento_id, situacao=A.ATIVO, proxima_execucao__lte=agora)
            .first()
        )
        if agendamento is None:
            return None
        previsto = agendamento.proxima_execucao
        data = recorrencia.data_local(previsto)
        regra = regra_do(agendamento)

        if agora - previsto > tolerancia():
            return _pular_por_atraso(agendamento, regra, previsto, data, agora, empresa)
        responsavel, motivo = verificar_responsavel(agendamento.responsavel_id, empresa)
        if motivo:
            return _suspender_automaticamente(agendamento, motivo, previsto, data, agora, empresa)
        try:
            with (
                transaction.atomic()
            ):  # ponto de salvamento: a violação do UNIQUE não derruba o resto
                execucao = ExecucaoAgendamento.objects.create(
                    agendamento=agendamento, data_execucao=data, previsto_para=previsto
                )
        except IntegrityError:
            _avancar(agendamento, regra, previsto, "A data já tinha sido executada.")
            agendamento.save()
            return JA_EXECUTADA
        return _gerar(agendamento, regra, execucao, responsavel, previsto, data, agora, empresa)


def _avancar(agendamento, regra, previsto, motivo_do_fim):
    """Calcula a próxima data depois de `previsto`; sem próxima, encerra o agendamento."""
    agendamento.proxima_execucao = recorrencia.proxima_execucao(
        regra, executadas=agendamento.execucoes_realizadas, depois_de=previsto
    )
    if agendamento.proxima_execucao is None:
        agendamento.situacao = A.ENCERRADO
        agendamento.motivo_situacao = motivo_do_fim[:300]


def _motivo_do_fim(agendamento):
    if agendamento.frequencia == Agendamento.Frequencia.UNICA:
        return "A execução única foi concluída."
    if agendamento.max_execucoes is not None and (
        agendamento.execucoes_realizadas >= agendamento.max_execucoes
    ):
        return f"As {agendamento.max_execucoes} execuções previstas foram realizadas."
    return "Chegou à data de fim."


def _gerar(agendamento, regra, execucao, responsavel, previsto, data, agora, empresa):
    try:
        with transaction.atomic():
            nfse = modelos.gerar_rascunho(
                agendamento.modelo, usuario=responsavel, data_execucao=data, execucao=execucao
            )
    except ErroDeNota as erro:
        return _falhar(
            agendamento, regra, execucao, previsto, " ".join(erro.erros.values()), agora, empresa
        )
    except Exception:
        logger.exception("Agendamento %s: erro inesperado ao gerar o rascunho.", agendamento.pk)
        return _falhar(
            agendamento, regra, execucao, previsto,
            "Erro inesperado ao gerar o rascunho. A equipe técnica foi avisada.", agora, empresa,
        )  # fmt: skip
    execucao.situacao, execucao.nfse, execucao.concluido_em = E.GERADA, nfse, agora
    execucao.save()
    agendamento.execucoes_realizadas += 1
    _avancar(agendamento, regra, previsto, _motivo_do_fim(agendamento))
    agendamento.save()
    auditoria.registrar(
        LogAuditoria.Acao.AGENDAMENTO_EXECUTADO,
        usuario=responsavel,
        empresa=empresa,
        alvo=f"nfse:{nfse.pk}",
        detalhes={"agendamento": agendamento.pk, "data": data.isoformat()},
    )
    avisos.avisar_rascunho_gerado(agendamento, execucao, empresa=empresa, agora=agora)
    return GERADA


def _falhar(agendamento, regra, execucao, previsto, texto, agora, empresa):
    """Registra a falha: a data não conta como execução e a série segue para a próxima."""
    execucao.situacao, execucao.erro, execucao.concluido_em = E.FALHOU, texto, agora
    execucao.save()
    _avancar(agendamento, regra, previsto, f"A última data prevista falhou: {texto}")
    agendamento.save()
    auditoria.registrar(
        LogAuditoria.Acao.AGENDAMENTO_FALHOU,
        empresa=empresa,
        alvo=f"agendamento:{agendamento.pk}",
        detalhes={"data": execucao.data_execucao.isoformat()},
    )
    avisos.avisar_falha(agendamento, execucao, empresa=empresa, agora=agora)
    return FALHOU


def _registrar_sem_rascunho(agendamento, previsto, data, situacao, texto, agora):
    """Linha do histórico de uma data que não gerou rascunho (sem falhar se já existir)."""
    try:
        with transaction.atomic():
            return ExecucaoAgendamento.objects.create(
                agendamento=agendamento, data_execucao=data, previsto_para=previsto,
                situacao=situacao, erro=texto, concluido_em=agora,
            )  # fmt: skip
    except IntegrityError:
        return ExecucaoAgendamento.objects.get(agendamento=agendamento, data_execucao=data)


def _suspender_automaticamente(agendamento, motivo, previsto, data, agora, empresa):
    execucao = _registrar_sem_rascunho(agendamento, previsto, data, E.SUSPENSA, motivo, agora)
    agendamento.situacao = A.SUSPENSO
    agendamento.motivo_situacao = motivo[:300]
    agendamento.proxima_execucao = None
    agendamento.save()
    auditoria.registrar(
        LogAuditoria.Acao.AGENDAMENTO_SUSPENSO,
        empresa=empresa,
        alvo=f"agendamento:{agendamento.pk}",
        detalhes={"automatico": True},
    )
    avisos.avisar_suspensao(agendamento, execucao, empresa=empresa, agora=agora)
    return SUSPENSA


def _pular_por_atraso(agendamento, regra, previsto, data, agora, empresa):
    """Sistema fora do ar além da tolerância: avisa em vez de gerar rascunhos atrasados."""
    limite = agora - tolerancia()
    puladas = recorrencia.contar_ocorrencias_ate(regra, desde=data, ate=limite)
    texto = (
        f"O sistema não executou {puladas} data(s) prevista(s) a partir de {data:%d/%m/%Y} porque "
        "ficou fora do ar além da tolerância. Nenhum rascunho foi gerado para elas e elas não "
        "contam como execução realizada."
    )
    execucao = _registrar_sem_rascunho(agendamento, previsto, data, E.PERDIDA, texto, agora)
    agendamento.proxima_execucao = recorrencia.proxima_execucao(
        regra, executadas=agendamento.execucoes_realizadas, depois_de=limite
    )
    if agendamento.proxima_execucao is None:
        agendamento.situacao = A.ENCERRADO
        agendamento.motivo_situacao = "Não restaram datas depois do período em que o sistema parou."
    agendamento.save()
    avisos.avisar_execucao_perdida(agendamento, execucao, empresa=empresa, agora=agora)
    return PERDIDA


# --- Alerta diário de rascunhos pendentes ----------------------------------------------------


def alertar_rascunhos_pendentes(agora, *, empresa):
    """Um e-mail por responsável com os rascunhos gerados por agendamento ainda não decididos."""
    from fiscal.models import Nfse

    pendentes = OrigemNfse.objects.filter(
        execucao__isnull=False, nfse__situacao=Nfse.Situacao.RASCUNHO
    ).select_related("execucao__agendamento")
    por_responsavel = {}
    for origem in pendentes:
        agendamento = origem.execucao.agendamento
        chave = (agendamento.responsavel_id, agendamento.responsavel_email)
        itens = por_responsavel.setdefault(chave, {})
        itens[agendamento.nome] = itens.get(agendamento.nome, 0) + 1
    dia = recorrencia.data_local(agora)
    enviados = 0
    for (responsavel_id, responsavel_email), itens in por_responsavel.items():
        aviso = avisos.avisar_rascunhos_pendentes(
            empresa=empresa,
            responsavel_id=responsavel_id,
            responsavel_email=responsavel_email,
            itens=itens,
            dia=dia,
            agora=agora,
        )
        enviados += aviso is not None
    return enviados


def agendamentos_do_modelo(modelo):
    """Agendamentos que ainda usam o modelo (ativos ou suspensos)."""
    return modelo.agendamentos.exclude(situacao=A.ENCERRADO)
