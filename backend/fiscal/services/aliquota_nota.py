"""Liga a regra de `pAliq` (`aliquota_issqn`) a uma nota: parâmetros da empresa, tomador e convênio.

Há dois resolvedores de convênio do município de incidência:

- `convenio_gravado` usa só o que já está no banco (a última verificação da Fase 2, que cobre o
  município do emissor): serve à prévia e à solicitação da emissão, sem rede;
- `convenio_com_consulta` acrescenta a consulta ao ambiente nacional (com o cache de 24 h da
  empresa) para os outros municípios, e roda na hora do envio, que já tem o certificado aberto.

Quando não dá para saber o convênio, o resolvedor devolve `None` e a regra bloqueia a emissão com
uma mensagem, em vez de adivinhar.
"""

from fiscal import gateway
from fiscal.services import aliquota_issqn, local_prestacao


def convenio_gravado(parametros):
    """Resolvedor sem rede: só o município do emissor, e só se a verificação ainda vale."""

    def resolver(codigo_municipio):
        if codigo_municipio == parametros.codigo_municipio_emissor and parametros.convenio_atual:
            resultado = parametros.convenio_resultado or {}
            return {
                "aderente": resultado.get("aderente"),
                "data_ativacao": resultado.get("data_ativacao"),
            }
        return None

    return resolver


def convenio_com_consulta(parametros, contexto):
    """Resolvedor completo: o gravado e, para outros municípios, a consulta com cache."""
    gravado = convenio_gravado(parametros)

    def resolver(codigo_municipio):
        achado = gravado(codigo_municipio)
        if achado is not None:
            return achado
        try:
            return gateway.consultar_convenio_municipio(contexto, codigo_municipio)
        except gateway.ErroDeConsultaFiscal:
            return None

    return resolver


def avaliar_nota(
    *,
    parametros,
    servico,
    competencia,
    iss_retido,
    tomador,
    resolver,
    municipio_prestacao,
    origem_prestacao,
):
    """Aplica a regra de `pAliq` aos dados de uma nota (snapshots de serviço e tomador).

    `municipio_prestacao` e `origem_prestacao` vêm de `local_prestacao.resolver`: só pesam nos
    serviços cujo ISSQN é devido no local da prestação.
    """
    return aliquota_issqn.avaliar(
        parametros=parametros,
        servico=servico,
        competencia=competencia,
        iss_retido=iss_retido,
        municipio_tomador=(tomador or {}).get("codigo_municipio") or None,
        municipio_prestacao=municipio_prestacao,
        origem_prestacao=origem_prestacao,
        convenio_do_municipio=resolver,
    )


def avaliar_da_nota(nfse, parametros, resolver):
    """Mesma avaliação, a partir de uma `Nfse` já gravada (usa o snapshot dela)."""
    prestacao, origem = local_prestacao.da_nota(nfse, parametros)
    return avaliar_nota(
        parametros=parametros,
        servico=nfse.servico,
        competencia=nfse.competencia,
        iss_retido=bool((nfse.totais or {}).get("iss_retido")),
        tomador=nfse.tomador,
        resolver=resolver,
        municipio_prestacao=prestacao,
        origem_prestacao=origem,
    )


def bloqueio_na_solicitacao(avaliacao, parametros):
    """Mensagem de bloqueio que já vale na solicitação (sem rede), ou `None`.

    Quando o município de incidência não é o do emissor e o convênio dele ainda não é conhecido, a
    decisão fica para o envio (que consulta a Sefin); o resto bloqueia já.
    """
    if not avaliacao.bloqueio:
        return None
    ainda_sem_saber = (
        avaliacao.decisao.situacao is aliquota_issqn.Situacao.INDETERMINADA
        and avaliacao.municipio_incidencia != parametros.codigo_municipio_emissor
    )
    return None if ainda_sem_saber else avaliacao.bloqueio
