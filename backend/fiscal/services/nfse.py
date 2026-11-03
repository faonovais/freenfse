"""Rascunho da nota: valida os dados, guarda o snapshot e monta a DPS.

O que vai na nota é uma **cópia** do tomador, do serviço e dos valores no momento em que o
rascunho é criado. Depois disso, mudar o cadastro não altera a nota (nem a que já foi emitida,
nem a que será reenviada após uma rejeição).
"""

import datetime as dt
import re
from dataclasses import dataclass, field

from django.utils import timezone

from cadastros.models import Pessoa, Servico
from fiscal.models import Nfse, ParametrosFiscais
from fiscal.services import calculo

MOTIVOS_DE_SUBSTITUICAO = {
    "01": "Desenquadramento do Simples Nacional",
    "02": "Enquadramento no Simples Nacional",
    "03": "Inclusão retroativa de imunidade ou isenção",
    "04": "Exclusão retroativa de imunidade ou isenção",
    "05": "Rejeição da nota pelo tomador ou intermediário",
    "99": "Outros motivos",
}

CAMPOS_DO_TOMADOR = (
    "tipo",
    "documento",
    "nif",
    "motivo_sem_nif",
    "nome",
    "inscricao_municipal",
    "telefone",
    "emails_envio",
    "logradouro",
    "numero",
    "complemento",
    "bairro",
    "codigo_municipio",
    "cep",
    "pais",
    "codigo_postal",
    "cidade",
    "estado",
)
CAMPOS_DO_SERVICO = (
    "nome",
    "descricao",
    "codigo_tributacao_nacional",
    "codigo_tributacao_municipal",
    "nbs",
    "cst_ibs_cbs",
    "c_class_trib",
    "iss_retido",
)
PERCENTUAIS_DO_SERVICO = (
    "aliquota_iss",
    "retencao_irrf",
    "retencao_csll",
    "retencao_pis",
    "retencao_cofins",
    "retencao_inss",
)
CAMPOS_DE_VALORES = (
    "servico",
    "desconto_incondicionado",
    "desconto_condicionado",
    "deducao_valor",
    "deducao_percentual",
)


class ErroDeNota(Exception):
    """Dados da nota inválidos; `erros` mapeia o campo à mensagem para o usuário."""

    def __init__(self, erros):
        """Aceita um dicionário campo → mensagem ou uma mensagem única (campo `geral`)."""
        if isinstance(erros, str):
            erros = {"geral": erros}
        super().__init__("; ".join(erros.values()))
        self.erros = erros


@dataclass
class Preparo:
    """Dados validados e já copiados (snapshot), prontos para gravar ou mostrar na prévia."""

    pessoa: Pessoa
    servico_cadastrado: Servico
    competencia: dt.date
    tomador: dict
    servico: dict
    valores: dict
    totais: dict
    complementos: dict
    avisos: list = field(default_factory=list)


def snapshot_tomador(pessoa):
    """Cópia dos dados do tomador necessários à DPS."""
    return {campo: getattr(pessoa, campo) for campo in CAMPOS_DO_TOMADOR}


def snapshot_servico(servico):
    """Cópia da versão do serviço (com os percentuais em texto, sem perda de casas)."""
    copia = {campo: getattr(servico, campo) for campo in CAMPOS_DO_SERVICO}
    for campo in PERCENTUAIS_DO_SERVICO:
        valor = getattr(servico, campo)
        copia[campo] = None if valor is None else str(valor)
    copia["id"] = servico.pk
    copia["vigencia_inicio"] = servico.vigencia_inicio.isoformat()
    copia["vigencia_fim"] = servico.vigencia_fim.isoformat() if servico.vigencia_fim else None
    return copia


def _data(valor, campo, erros):
    if isinstance(valor, dt.date):
        return valor
    try:
        return dt.date.fromisoformat(str(valor))
    except ValueError:
        erros[campo] = "Informe a competência no formato AAAA-MM-DD."
        return None


def _ibs_cbs(bruto, servico, erros):
    if not bruto:
        return None
    indicador = str(bruto.get("codigo_indicador_operacao") or "").strip()
    destinatario = bruto.get("indicador_destinatario")
    if not re.fullmatch(r"\d{6}", indicador):
        erros["ibs_cbs"] = "O código do indicador da operação tem 6 dígitos."
    elif destinatario not in (0, 1, "0", "1"):
        erros["ibs_cbs"] = "Informe se o destinatário é o próprio tomador (0 ou 1)."
    elif not (servico.cst_ibs_cbs and servico.c_class_trib and servico.nbs):
        erros["ibs_cbs"] = (
            "O serviço precisa ter NBS, CST e classificação do IBS/CBS para informar esse grupo."
        )
    else:
        return {"codigo_indicador_operacao": indicador, "indicador_destinatario": int(destinatario)}
    return None


def preparar(dados):
    """Valida a entrada e devolve o `Preparo` (sem gravar nada).

    Levanta `ErroDeNota` com um erro por campo. Serve ao rascunho e à prévia da tela.
    """
    erros = {}
    pessoa = Pessoa.objects.filter(pk=dados.get("tomador"), ativo=True).first()
    if pessoa is None:
        erros["tomador"] = "Escolha um tomador ativo do cadastro de pessoas."
    competencia = _data(dados.get("competencia"), "competencia", erros)
    if competencia is not None and competencia > timezone.localdate():
        erros["competencia"] = "A competência não pode ser uma data futura."

    servico = None
    if competencia is not None:
        servico = Servico.objects.vigentes_em(competencia).filter(pk=dados.get("servico")).first()
        if servico is None:
            erros["servico"] = (
                f"Escolha um serviço vigente em {competencia:%d/%m/%Y}. Serviços sem vigência "
                "nessa data não podem ser usados."
            )
    elif "competencia" not in erros:
        erros["competencia"] = "Informe a competência."

    if servico is not None and any(
        (getattr(servico, campo) or 0) > 0 for campo in ("retencao_pis", "retencao_cofins")
    ):
        erros["servico"] = (
            "Este serviço tem retenção de PIS/COFINS, que o sistema ainda não envia na nota. "
            "Remova a retenção no cadastro do serviço ou emita esta nota pelo emissor oficial."
        )
    if erros:
        raise ErroDeNota(erros)

    entrada = dados.get("valores") or {}
    valores = {campo: entrada.get(campo) for campo in CAMPOS_DE_VALORES}
    copia_servico = snapshot_servico(servico)
    try:
        totais = calculo.calcular(valores, copia_servico)
    except calculo.ErroDeValores as erro:
        raise ErroDeNota({f"valores.{campo}": m for campo, m in erro.erros.items()}) from None

    complementos_erros = {}
    simples = calculo.decimal_ou_none(
        dados.get("percentual_total_tributos_simples"),
        "percentual_total_tributos_simples",
        complementos_erros,
    )
    ibs = _ibs_cbs(dados.get("ibs_cbs"), servico, complementos_erros)
    if complementos_erros:
        raise ErroDeNota(complementos_erros)

    avisos = []
    if servico.cst_ibs_cbs and servico.c_class_trib and ibs is None:
        avisos.append(
            "O serviço tem classificação de IBS/CBS, mas o indicador da operação não foi "
            "informado: a nota será emitida sem o grupo de IBS/CBS."
        )
    if competencia.replace(day=1) != timezone.localdate().replace(day=1):
        avisos.append("A competência é de outro mês. Confira se é isso mesmo.")

    return Preparo(
        pessoa=pessoa,
        servico_cadastrado=servico,
        competencia=competencia,
        tomador=snapshot_tomador(pessoa),
        servico=copia_servico,
        valores={
            campo: (None if valor in (None, "") else str(valor)) for campo, valor in valores.items()
        },
        totais=totais.para_dict(),
        complementos={
            "informacoes_complementares": (dados.get("informacoes_complementares") or "").strip(),
            "percentual_total_tributos_simples": None if simples is None else str(simples),
            "ibs_cbs": ibs,
        },
        avisos=avisos,
    )


def _campos_da_nota(preparo):
    return {
        "competencia": preparo.competencia,
        "tomador": preparo.tomador,
        "servico": preparo.servico,
        "valores": preparo.valores,
        "totais": preparo.totais,
        "complementos": preparo.complementos,
        "tomador_nome": preparo.pessoa.nome,
        "tomador_documento": preparo.pessoa.documento,
        "valor_servico": preparo.totais["valor_servico"],
        "tomador_ref": preparo.pessoa,
        "servico_ref": preparo.servico_cadastrado,
    }


def criar_rascunho(dados, *, usuario):
    """Cria o rascunho com o snapshot dos cadastros. Ambiente e série vêm dos parâmetros."""
    preparo = preparar(dados)
    parametros = ParametrosFiscais.obter()
    return Nfse.objects.create(
        ambiente=parametros.ambiente,
        serie=parametros.serie_dps,
        criado_por_id=getattr(usuario, "pk", None),
        criado_por_email=getattr(usuario, "email", ""),
        **_campos_da_nota(preparo),
    )


def atualizar_rascunho(nfse, dados):
    """Corrige um rascunho (ou uma nota rejeitada) refazendo o snapshot."""
    if not nfse.editavel:
        raise ErroDeNota(
            f"Uma nota {nfse.get_situacao_display().lower()} não pode mais ser alterada."
        )
    preparo = preparar(dados)
    for campo, valor in _campos_da_nota(preparo).items():
        setattr(nfse, campo, valor)
    nfse.save()
    return nfse


def criar_substituta(original, *, codigo_motivo, motivo, usuario):
    """Cria o rascunho da nota que substituirá `original`, com os mesmos dados.

    A substituída só passa a "substituída" quando a Sefin confirma o evento, depois que a nova
    nota for autorizada.
    """
    if original.situacao != Nfse.Situacao.AUTORIZADA:
        raise ErroDeNota(
            "Só uma nota autorizada pode ser substituída. "
            f"Esta está {original.get_situacao_display().lower()}."
        )
    if original.substitutas.exclude(situacao=Nfse.Situacao.REJEITADA).exists():
        raise ErroDeNota("Já existe uma nota substituta em andamento ou autorizada para esta.")
    codigo = str(codigo_motivo or "").strip().zfill(2)
    if codigo not in MOTIVOS_DE_SUBSTITUICAO:
        raise ErroDeNota({"codigo_motivo": "Escolha um dos motivos de substituição da lista."})
    motivo = (motivo or "").strip()
    if codigo == "99" and not 15 <= len(motivo) <= 255:
        raise ErroDeNota({"motivo": "Explique o motivo em 15 a 255 caracteres."})
    if motivo and not 15 <= len(motivo) <= 255:
        raise ErroDeNota({"motivo": "O motivo deve ter de 15 a 255 caracteres."})
    parametros = ParametrosFiscais.obter()
    return Nfse.objects.create(
        ambiente=parametros.ambiente,
        serie=parametros.serie_dps,
        competencia=original.competencia,
        tomador=original.tomador,
        servico=original.servico,
        valores=original.valores,
        totais=original.totais,
        complementos=original.complementos,
        tomador_nome=original.tomador_nome,
        tomador_documento=original.tomador_documento,
        valor_servico=original.valor_servico,
        tomador_ref=original.tomador_ref,
        servico_ref=original.servico_ref,
        substitui=original,
        substituicao_motivo=codigo,
        substituicao_texto=motivo,
        criado_por_id=getattr(usuario, "pk", None),
        criado_por_email=getattr(usuario, "email", ""),
    )


def dados_da_dps(nfse, *, empresa, parametros=None, numero=None):
    """Dados simples da DPS (para o gateway) a partir do snapshot da nota."""
    parametros = parametros or ParametrosFiscais.obter()
    complementos = nfse.complementos or {}
    return {
        "serie": nfse.serie,
        "numero": numero,
        "competencia": nfse.competencia,
        "codigo_municipio_emissor": parametros.codigo_municipio_emissor,
        "prestador": {
            "cnpj": empresa.cnpj,
            "opcao_simples": parametros.opcao_simples,
            "regime_apuracao_simples": parametros.regime_apuracao_simples,
            "regime_especial": parametros.regime_especial,
        },
        "tomador": nfse.tomador,
        "servico": nfse.servico,
        "valores": nfse.valores,
        "totais": nfse.totais,
        "informacoes_complementares": complementos.get("informacoes_complementares", ""),
        "percentual_total_tributos_simples": complementos.get("percentual_total_tributos_simples"),
        "ibs_cbs": complementos.get("ibs_cbs"),
        "substituicao": (
            {
                "chave": nfse.substitui.chave,
                "codigo_motivo": nfse.substituicao_motivo,
                "motivo": nfse.substituicao_texto,
            }
            if nfse.substitui_id
            else None
        ),
    }
