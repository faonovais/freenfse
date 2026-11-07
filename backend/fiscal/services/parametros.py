"""Parâmetros fiscais da empresa e verificação do convênio do município."""

from django.db import transaction
from django.utils import timezone

from core.models import LogAuditoria, Municipio
from core.services import auditoria
from fiscal import gateway
from fiscal.models import Certificado, ParametrosFiscais
from fiscal.services import producao
from fiscal.services.certificado import abrir_em_memoria
from fiscal.services.producao import ProducaoNaoLiberada

CAMPOS_EDITAVEIS = (
    "regime_tributario",
    "regime_apuracao_simples",
    "regime_especial",
    "serie_dps",
    "ambiente",
    "codigo_municipio_emissor",
    "ibs_cbs_indicador_destinatario",
)
# O que a verificação do convênio grava (a gravação toca só estes campos, nunca a linha inteira).
CAMPOS_DO_CONVENIO = (
    "convenio_resultado",
    "convenio_verificado_em",
    "convenio_codigo_municipio",
    "convenio_ambiente",
)


class ProducaoSemConfirmacao(Exception):
    """A troca para o ambiente de produção exige confirmação explícita."""


class ErroDeVerificacao(Exception):
    """A verificação do convênio não pôde ser feita por algo que o usuário pode corrigir."""


class ErroDeConsultaExterna(Exception):
    """A consulta ao ambiente nacional falhou (rede, serviço fora do ar ou recusa)."""


def atualizar_parametros(*, request, dados, confirmar_producao=False):
    """Altera os parâmetros fiscais e audita; a troca de ambiente é auditada à parte.

    A permissão `config.editar` é verificada pela view. Trocar para **produção** (notas com valor
    fiscal) segue esta ordem, parando na primeira etapa que falhar e sem gravar nada:

    1. pendências locais (certificado enviado, em vigor e com o CNPJ conferido; município
       informado) → `ProducaoNaoLiberada`;
    2. confirmação explícita → `ProducaoSemConfirmacao`;
    3. convênio do município **consultado na hora, no ambiente de produção**, vigente →
       `ProducaoNaoLiberada`.

    Passando tudo, o resultado dessa consulta é gravado junto com a troca: a empresa já nasce em
    produção com o convênio válido para o ambiente e o município atuais. A consulta (rede) roda
    **fora** da transação: não se segura conexão aberta esperando a Sefin.
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
    convenio = None
    if indo_para_producao:
        convenio = _liberar_producao(request, parametros, confirmar_producao)

    campos = [campo for campo in CAMPOS_EDITAVEIS if campo in dados]
    with transaction.atomic():
        if convenio is not None:
            _guardar_convenio(parametros, convenio, ambiente_producao=True)
            campos += CAMPOS_DO_CONVENIO
        parametros.save(update_fields=[*campos, "atualizado_em"])

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
        if convenio is not None:
            auditoria.registrar(
                LogAuditoria.Acao.CONVENIO_VERIFICADO,
                request=request,
                alvo=f"municipio:{convenio.codigo_municipio}",
                detalhes={
                    "aderente": convenio.aderente,
                    "ambiente": ParametrosFiscais.Ambiente.PRODUCAO,
                    "na_troca_para_producao": True,
                },
            )
    return parametros


def _liberar_producao(request, parametros, confirmar_producao):
    """Confere tudo o que a produção exige e devolve o convênio consultado (ou levanta o motivo)."""
    certificado = Certificado.objects.first()
    pendencias = producao.pendencias_locais(
        empresa=request.empresa, parametros=parametros, certificado=certificado
    )
    if pendencias:
        raise ProducaoNaoLiberada(pendencias)
    if not confirmar_producao:
        raise ProducaoSemConfirmacao

    try:
        convenio = _consultar_convenio(
            cnpj=request.empresa.cnpj,
            codigo_municipio=parametros.codigo_municipio_emissor,
            ambiente_producao=True,
            certificado=certificado,
        )
    except ErroDeConsultaExterna as erro:
        raise ProducaoNaoLiberada([producao.sem_consulta(str(erro))]) from None
    pendencia = producao.avaliar_convenio(convenio, lugar=_lugar(convenio))
    if pendencia:
        raise ProducaoNaoLiberada([pendencia])
    return convenio


def _lugar(resultado):
    """`Nome/UF` do município do resultado (ou o código, se a tabela não o conhecer)."""
    municipio = Municipio.objects.filter(codigo=resultado.codigo_municipio).first()
    return f"{municipio.nome}/{municipio.uf}" if municipio else resultado.codigo_municipio


def _mensagem_do_convenio(resultado, lugar):
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


def _consultar_convenio(
    *, cnpj, codigo_municipio, ambiente_producao, certificado, transporte=None, pausa=None
):
    """Consulta o convênio via `freedfe` com o certificado da empresa; não grava nada."""
    if certificado is None:
        # Segunda trava (a primeira é a pendência `sem_certificado`): sem certificado não há como
        # se identificar na consulta, e isso vira uma recusa explícita, nunca um erro interno.
        raise ErroDeConsultaExterna("a empresa não tem certificado A1 para se identificar.")
    try:
        a1 = abrir_em_memoria(certificado)
        resultado = gateway.verificar_convenio(
            cnpj=cnpj,
            codigo_municipio=codigo_municipio,
            ambiente_producao=ambiente_producao,
            certificado=a1,
            transporte=transporte,
            pausa=pausa,
        )
    except gateway.ErroDeConsultaFiscal as erro:
        raise ErroDeConsultaExterna(str(erro)) from None
    resultado.mensagem = _mensagem_do_convenio(resultado, _lugar(resultado))
    return resultado


def _guardar_convenio(parametros, resultado, *, ambiente_producao):
    """Põe o resultado nos campos do convênio (quem chama grava), com o ambiente consultado."""
    ambiente = ParametrosFiscais.Ambiente
    parametros.convenio_resultado = resultado.para_dict()
    parametros.convenio_verificado_em = timezone.now()
    parametros.convenio_codigo_municipio = resultado.codigo_municipio
    parametros.convenio_ambiente = (
        ambiente.PRODUCAO if ambiente_producao else ambiente.PRODUCAO_RESTRITA
    )


def verificar_convenio(*, request, transporte=None, pausa=None):
    """Consulta o convênio do município emissor via `freedfe` e guarda o resultado com a data.

    Usa o certificado da empresa (mTLS) e o ambiente **gravado** nos parâmetros. Em caso de
    falha, o último resultado guardado é mantido e o usuário recebe uma mensagem clara
    (`ErroDeVerificacao`). A gravação toca só os campos do convênio: uma troca de ambiente feita
    por outra pessoa durante a consulta não é desfeita.
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

    em_producao = parametros.ambiente == ParametrosFiscais.Ambiente.PRODUCAO
    resultado = _consultar_convenio(
        cnpj=request.empresa.cnpj,
        codigo_municipio=parametros.codigo_municipio_emissor,
        ambiente_producao=em_producao,
        certificado=certificado,
        transporte=transporte,
        pausa=pausa,
    )

    _guardar_convenio(parametros, resultado, ambiente_producao=em_producao)
    parametros.save(update_fields=[*CAMPOS_DO_CONVENIO, "atualizado_em"])
    auditoria.registrar(
        LogAuditoria.Acao.CONVENIO_VERIFICADO,
        request=request,
        alvo=f"municipio:{resultado.codigo_municipio}",
        detalhes={"aderente": resultado.aderente, "ambiente": parametros.convenio_ambiente},
    )
    return parametros
