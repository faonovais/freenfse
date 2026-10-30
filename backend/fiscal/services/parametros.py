"""Parâmetros fiscais da empresa e verificação do convênio do município."""

from django.db import transaction
from django.utils import timezone

from core.models import LogAuditoria, Municipio
from core.services import auditoria
from fiscal import gateway
from fiscal.models import Certificado, ParametrosFiscais
from fiscal.services.certificado import abrir_em_memoria

CAMPOS_EDITAVEIS = (
    "regime_tributario",
    "regime_apuracao_simples",
    "regime_especial",
    "serie_dps",
    "ambiente",
    "codigo_municipio_emissor",
)


class ProducaoSemConfirmacao(Exception):
    """A troca para o ambiente de produção exige confirmação explícita."""


class ErroDeVerificacao(Exception):
    """A verificação do convênio não pôde ser feita por algo que o usuário pode corrigir."""


class ErroDeConsultaExterna(Exception):
    """A consulta ao ambiente nacional falhou (rede, serviço fora do ar ou recusa)."""


@transaction.atomic
def atualizar_parametros(*, request, dados, confirmar_producao=False):
    """Altera os parâmetros fiscais e audita; a troca de ambiente é auditada à parte.

    Trocar para **produção** (notas com valor fiscal) exige `confirmar_producao`. A permissão
    `config.editar` é verificada pela view.
    """
    parametros = ParametrosFiscais.obter()
    antes = {campo: getattr(parametros, campo) for campo in CAMPOS_EDITAVEIS}
    for campo in CAMPOS_EDITAVEIS:
        if campo in dados:
            setattr(parametros, campo, dados[campo])
    parametros.clean()

    indo_para_producao = (
        antes["ambiente"] != ParametrosFiscais.Ambiente.PRODUCAO
        and parametros.ambiente == ParametrosFiscais.Ambiente.PRODUCAO
    )
    if indo_para_producao and not confirmar_producao:
        raise ProducaoSemConfirmacao
    parametros.save()

    alterados = {
        campo: {"de": antes[campo], "para": getattr(parametros, campo)}
        for campo in CAMPOS_EDITAVEIS
        if antes[campo] != getattr(parametros, campo)
    }
    if alterados:
        auditoria.registrar(
            LogAuditoria.Acao.PARAMETROS_ALTERADOS, request=request, alvo="parametros-fiscais",
            detalhes={"alterados": alterados},
        )  # fmt: skip
    if "ambiente" in alterados:
        auditoria.registrar(
            LogAuditoria.Acao.AMBIENTE_ALTERADO,
            request=request,
            alvo="parametros-fiscais",
            detalhes=alterados["ambiente"],
        )
    return parametros


def _mensagem_do_convenio(resultado, municipio):
    lugar = f"{municipio.nome}/{municipio.uf}" if municipio else resultado.codigo_municipio
    if resultado.aderente is True:
        texto = f"O município {lugar} aderiu à NFS-e Nacional: já é possível emitir por aqui."
        if resultado.data_ativacao:
            ativacao = resultado.data_ativacao
            texto += f" Convênio ativo desde {ativacao[8:10]}/{ativacao[5:7]}/{ativacao[:4]}."
        return texto
    if resultado.aderente is False:
        return (
            f"O município {lugar} NÃO tem convênio com a NFS-e Nacional neste ambiente. As "
            "notas seriam rejeitadas (E0037). Confirme a adesão com a prefeitura."
        )
    return (
        f"A resposta não deixou claro se o município {lugar} aderiu à NFS-e Nacional. Tente "
        "novamente mais tarde ou confirme com a prefeitura."
    )


def verificar_convenio(*, request, transporte=None, pausa=None):
    """Consulta o convênio do município emissor via `freedfe` e guarda o resultado com a data.

    Usa o certificado da empresa (mTLS). Em caso de falha, o último resultado guardado é
    mantido e o usuário recebe uma mensagem clara (`ErroDeVerificacao`).
    """
    parametros = ParametrosFiscais.obter()
    if not parametros.codigo_municipio_emissor:
        raise ErroDeVerificacao("Informe o município emissor antes de verificar o convênio.")
    certificado = Certificado.objects.first()
    if certificado is None:
        raise ErroDeVerificacao(
            "Envie o certificado A1 da empresa antes de verificar o convênio: a consulta usa o "
            "certificado para se identificar."
        )
    if certificado.vencido():
        raise ErroDeVerificacao(
            "O certificado da empresa está vencido. Envie um certificado válido."
        )

    try:
        a1 = abrir_em_memoria(certificado)
        resultado = gateway.verificar_convenio(
            cnpj=request.empresa.cnpj,
            codigo_municipio=parametros.codigo_municipio_emissor,
            ambiente_producao=parametros.ambiente == ParametrosFiscais.Ambiente.PRODUCAO,
            certificado=a1,
            transporte=transporte,
            pausa=pausa,
        )
    except gateway.ErroDeConsultaFiscal as erro:
        raise ErroDeConsultaExterna(str(erro)) from None

    municipio = Municipio.objects.filter(codigo=resultado.codigo_municipio).first()
    resultado.mensagem = _mensagem_do_convenio(resultado, municipio)
    parametros.convenio_resultado = resultado.para_dict()
    parametros.convenio_verificado_em = timezone.now()
    parametros.convenio_codigo_municipio = parametros.codigo_municipio_emissor
    parametros.convenio_ambiente = parametros.ambiente
    parametros.save()
    auditoria.registrar(
        LogAuditoria.Acao.CONVENIO_VERIFICADO,
        request=request,
        alvo=f"municipio:{resultado.codigo_municipio}",
        detalhes={"aderente": resultado.aderente, "ambiente": parametros.ambiente},
    )
    return parametros
