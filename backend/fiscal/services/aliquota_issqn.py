"""Regra única da alíquota do ISSQN (`pAliq`) na DPS, conforme o Anexo VI da NT SE/CGNFS-e 009.

Antes da issue #29 o sistema decidia só pelo regime do prestador. A regra oficial depende também
do **convênio do município de incidência do ISSQN na data de competência** e da **retenção do
ISSQN**; o erro mais grave era um prestador não optante num município conveniado enviar `pAliq`
(rejeição E0617). Este módulo tem duas partes:

1. `decidir_aliquota` — função **pura** que implementa as regras E0600, E0604, E0617, E0619, E0621,
   E0625, E0628, E0631, E0635 e E0640 (e E0595, o teto de 5%);
2. `avaliar` — junta a decisão com o município de incidência (Anexo VI, LC 116 art. 3º), o
   convênio desse município e a alíquota do serviço, e devolve o que vai na DPS, a explicação para
   a prévia e o eventual bloqueio da emissão.

Limites assumidos e registrados na ADR 0010:

- o freenfse não envia benefício municipal (`tpBM`), então a condição "sem benefício municipal ou
  diferente de isenção/alíquota diferenciada" das regras E0621/E0625 é sempre satisfeita, e a
  E0612 não se aplica;
- só emite serviço tributável (`tribISSQN = 1`), então a E0602 não se aplica;
- "convênio ativo" é lido de `aderenteAmbienteNacional` (e da data de ativação) da consulta de
  parâmetros municipais, cuja semântica a biblioteca `freedfe` registra como não documentada;
- o regime do prestador é o dos parâmetros da empresa **de agora**, não o da data de competência.
"""

import datetime as dt
import enum
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from fiscal.referencias import incidencia

OPCAO_NAO_OPTANTE, OPCAO_MEI, OPCAO_ME_EPP = 1, 2, 3
APURACAO_PELO_SIMPLES = 1
REGIMES_ESPECIAIS_QUE_PROIBEM = (1, 2, 3, 4, 5, 6)  # E0604
ALIQUOTA_MINIMA_COM_RETENCAO = Decimal("1.8")  # E0621 / E0628
ALIQUOTA_MAXIMA = Decimal("5")  # E0595
RETENCAO_COM_TOMADOR = "tpRetISSQN = 2 ou 3"


class Situacao(enum.Enum):
    """O que a regra manda fazer com o campo `pAliq`."""

    OBRIGATORIA = "obrigatoria"
    PROIBIDA = "proibida"
    FACULTATIVA = "facultativa"  # o Anexo VI não obriga nem proíbe
    CONFLITO = "conflito"  # duas regras do anexo se contradizem: não há como atender
    INDETERMINADA = "indeterminada"  # falta dado para decidir (ex.: convênio desconhecido)


@dataclass(frozen=True)
class Decisao:
    """Resultado de `decidir_aliquota`."""

    situacao: Situacao
    codigo: str | None
    explicacao: str
    minimo: Decimal | None = None


def _decisao(situacao, codigo, explicacao, minimo=None):
    return Decisao(situacao, codigo, explicacao, minimo)


def _base_do_simples(apuracao, ativo, retido):
    """Regras E0621–E0640: prestador ME/EPP (`opSimpNac = 3`)."""
    if apuracao is None:
        return _decisao(
            Situacao.INDETERMINADA,
            None,
            "Informe, nos parâmetros fiscais, como os tributos do Simples Nacional são apurados.",
        )
    if apuracao == APURACAO_PELO_SIMPLES:
        if retido:
            codigo = "E0621" if ativo else "E0628"
            lugar = "ativo" if ativo else "não ativo"
            return _decisao(
                Situacao.OBRIGATORIA,
                codigo,
                f"ME/EPP com ISSQN apurado pelo Simples, ISSQN retido e município de incidência "
                f"com convênio {lugar} na competência: a alíquota é obrigatória (mínimo de 1,8%).",
                ALIQUOTA_MINIMA_COM_RETENCAO,
            )
        codigo = "E0625" if ativo else "E0631"
        lugar = "ativo" if ativo else "não ativo"
        return _decisao(
            Situacao.PROIBIDA,
            codigo,
            f"ME/EPP com ISSQN apurado pelo Simples, sem retenção e município de incidência com "
            f"convênio {lugar} na competência: a alíquota não pode ser informada.",
        )
    if ativo:
        return _decisao(
            Situacao.PROIBIDA,
            "E0635",
            "ME/EPP com ISSQN apurado fora do Simples e município de incidência com convênio "
            "ativo na competência: a alíquota não pode ser informada (vale a do município).",
        )
    return _decisao(
        Situacao.OBRIGATORIA,
        "E0640",
        "ME/EPP com ISSQN apurado fora do Simples e município de incidência sem convênio ativo "
        "na competência: a alíquota é obrigatória.",
    )


def _base_do_nao_optante(ativo, regime_especial):
    """Regras E0617 e E0619: prestador não optante pelo Simples (`opSimpNac = 1`)."""
    if ativo:
        return _decisao(
            Situacao.PROIBIDA,
            "E0617",
            "Prestador não optante pelo Simples Nacional e município de incidência com convênio "
            "ativo na competência: a alíquota não pode ser informada (vale a do município).",
        )
    if regime_especial == 0:
        return _decisao(
            Situacao.OBRIGATORIA,
            "E0619",
            "Prestador não optante pelo Simples Nacional, sem regime especial de tributação, e "
            "município de incidência sem convênio ativo na competência: a alíquota é obrigatória.",
        )
    return None  # com regime especial: decide a sobreposição da E0604 (ou nenhuma regra)


def decidir_aliquota(
    *, opcao_simples, regime_apuracao, regime_especial, convenio_ativo, iss_retido
):
    """Diz se `pAliq` é obrigatória, proibida, facultativa, contraditória ou indeterminada.

    `opcao_simples` é o `opSimpNac` (1 não optante, 2 MEI, 3 ME/EPP); `regime_apuracao`, o
    `regApTribSN` (1, 2 ou 3; só vale para ME/EPP); `regime_especial`, o `regEspTrib`;
    `convenio_ativo` diz se o município de incidência tem convênio **ativo na data de
    competência** (`None` = não foi possível saber); `iss_retido`, se há retenção do ISSQN.
    """
    opcao_simples = int(opcao_simples)
    regime_especial = int(regime_especial or 0)
    if opcao_simples == OPCAO_MEI:
        return _decisao(
            Situacao.PROIBIDA,
            "E0600",
            "Prestador MEI: a alíquota do ISSQN não pode ser informada.",
        )
    com_regime_especial = regime_especial in REGIMES_ESPECIAIS_QUE_PROIBEM
    if convenio_ativo is None:
        return _decisao(
            Situacao.INDETERMINADA,
            None,
            "Não foi possível confirmar se o município de incidência do ISSQN tem convênio ativo "
            "na data de competência; sem isso não dá para saber se a alíquota deve ir na nota.",
        )

    if opcao_simples == OPCAO_ME_EPP:
        base = _base_do_simples(
            None if regime_apuracao is None else int(regime_apuracao), convenio_ativo, iss_retido
        )
    else:
        base = _base_do_nao_optante(convenio_ativo, regime_especial)

    if com_regime_especial:
        if base is not None and base.situacao is Situacao.OBRIGATORIA:
            return _decisao(
                Situacao.CONFLITO,
                f"{base.codigo}/E0604",
                f"A regra {base.codigo} exige a alíquota, mas a E0604 a proíbe para prestador com "
                f"regime especial de tributação ({regime_especial}). O Anexo VI não diz qual "
                "prevalece; emita esta nota pelo emissor oficial ou revise os parâmetros fiscais.",
            )
        if base is not None and base.situacao is Situacao.PROIBIDA:
            return base
        return _decisao(
            Situacao.PROIBIDA,
            "E0604",
            "Prestador com regime especial de tributação: a alíquota não pode ser informada.",
        )
    if base is None:  # não optante, convênio não ativo, regime especial 9 ("outros")
        return _decisao(
            Situacao.FACULTATIVA,
            None,
            "O Anexo VI não obriga nem proíbe a alíquota para este caso (regime especial "
            '"outros"); ela vai se o serviço tiver alíquota cadastrada.',
        )
    return base


# -- o que vai na DPS e o que bloqueia -----------------------------------------------------------


def _como_decimal(valor):
    if valor in (None, ""):
        return None
    try:
        return Decimal(str(valor))
    except InvalidOperation:
        return None


def aplicar_ao_valor(decisao, aliquota):
    """`(envia, bloqueio)`: se `pAliq` vai na DPS e, se a emissão não pode seguir, o motivo.

    `aliquota` é a alíquota do cadastro do serviço (texto ou `Decimal`; `None` se não há).
    """
    valor = _como_decimal(aliquota)
    codigo = f" (regra {decisao.codigo})" if decisao.codigo else ""
    if decisao.situacao in (Situacao.CONFLITO, Situacao.INDETERMINADA):
        return False, decisao.explicacao
    if decisao.situacao is Situacao.PROIBIDA:
        return False, None
    if valor is not None and valor > ALIQUOTA_MAXIMA:
        return False, (
            f"A alíquota do ISS do serviço ({valor}%) passa de 5%, o máximo aceito pela Sefin "
            "(regra E0595). Corrija o cadastro do serviço."
        )
    if decisao.situacao is Situacao.FACULTATIVA:
        return valor is not None, None
    if valor is None:
        return False, (
            f"Para esta nota a Sefin exige a alíquota do ISS{codigo}, mas o serviço não tem "
            f"alíquota cadastrada. {decisao.explicacao} Informe a alíquota no cadastro do serviço."
        )
    if decisao.minimo is not None and valor < decisao.minimo:
        return False, (
            f"A alíquota do serviço ({valor}%) é menor que o mínimo de {decisao.minimo}% exigido "
            f"para este caso{codigo}. {decisao.explicacao} Corrija o cadastro do serviço."
        )
    return True, None


# -- município de incidência e convênio ----------------------------------------------------------


def municipio_de_incidencia(
    *, codigo_tributacao_nacional, municipio_emissor, municipio_tomador, municipio_prestacao
):
    """`(município, regra, aviso)`: onde incide o ISSQN, pela aba oficial do Anexo VI.

    - estabelecimento do prestador → município do emissor;
    - **local da prestação** → o município da prestação informado na nota (o emissor, se ninguém
      informou outro). Sem município da prestação, devolve `None` e o chamador bloqueia;
    - estabelecimento do tomador → município do tomador.

    Serviço que o anexo não traz, ou caso que não dá para resolver, usa a **regra geral**
    (município do prestador) e devolve um aviso para a prévia.
    """
    regra = incidencia.regra_de_incidencia(codigo_tributacao_nacional)
    if regra is None:
        return (
            municipio_emissor,
            incidencia.EP,
            "O serviço não consta da tabela de incidência do Anexo VI; foi usada a regra geral "
            "(ISSQN devido no município do prestador).",
        )
    if regra == incidencia.EP:
        return municipio_emissor, regra, None
    if regra == incidencia.LP:
        return municipio_prestacao or None, regra, None
    if regra == incidencia.ET:
        if municipio_tomador:
            return municipio_tomador, regra, None
        return (
            municipio_emissor,
            incidencia.EP,
            "Para este serviço o ISSQN é devido no município do tomador, mas o tomador não tem "
            "município brasileiro cadastrado; foi usada a regra geral (município do prestador).",
        )
    return (
        municipio_emissor,
        incidencia.EP,
        "O Anexo VI indica serviço sem incidência de ISSQN, que o sistema ainda não emite como "
        "tal (só emite serviço tributável); foi usada a regra geral.",
    )


def convenio_ativo_na_data(*, aderente, data_ativacao, competencia):
    """Diz se o convênio estava ativo na competência: `True`, `False` ou `None` (sem saber).

    Aderência negativa ou competência anterior à data de ativação = não ativo. Aderente sem data
    de ativação conhecida vale como ativo.
    """
    if aderente is None:
        return None
    if aderente is False:
        return False
    if data_ativacao is not None and competencia < data_ativacao:
        return False
    return True


@dataclass
class Avaliacao:
    """O que a regra decidiu para uma nota: o que vai na DPS, por quê e se bloqueia a emissão."""

    envia: bool
    decisao: Decisao
    bloqueio: str | None
    municipio_incidencia: str | None
    regra_incidencia: str
    convenio_ativo: bool | None
    avisos: list = field(default_factory=list)
    origem_prestacao: str | None = None

    def para_dict(self):
        """Forma gravada na nota e mostrada na prévia."""
        return {
            "envia": self.envia,
            "situacao": self.decisao.situacao.value,
            "codigo_regra": self.decisao.codigo,
            "explicacao": self.decisao.explicacao,
            "minimo": None if self.decisao.minimo is None else str(self.decisao.minimo),
            "bloqueio": self.bloqueio,
            "municipio_incidencia": self.municipio_incidencia,
            "regra_incidencia": self.regra_incidencia,
            "regra_incidencia_descricao": incidencia.DESCRICAO.get(self.regra_incidencia, ""),
            "convenio_ativo": self.convenio_ativo,
            # Só conta quando o ISSQN é devido no local da prestação: de onde veio esse município.
            "origem_prestacao": self.origem_prestacao
            if self.regra_incidencia == incidencia.LP
            else None,
            "avisos": list(self.avisos),
        }


def avaliar(
    *,
    parametros,
    servico,
    competencia,
    iss_retido,
    municipio_tomador,
    municipio_prestacao,
    origem_prestacao,
    convenio_do_municipio,
):
    """Aplica as regras do Anexo VI a uma nota.

    `parametros` são os `ParametrosFiscais` da empresa; `servico`, o snapshot do serviço;
    `municipio_prestacao`, o município da prestação da nota (e `origem_prestacao`, de onde ele
    veio); `convenio_do_municipio(codigo)` devolve `{"aderente", "data_ativacao"}` do município
    (ou levanta/devolve `None` quando não dá para saber). Não acessa a rede por conta própria.
    """
    emissor = parametros.codigo_municipio_emissor
    municipio, regra, aviso = municipio_de_incidencia(
        codigo_tributacao_nacional=servico["codigo_tributacao_nacional"],
        municipio_emissor=emissor,
        municipio_tomador=municipio_tomador,
        municipio_prestacao=municipio_prestacao,
    )
    avisos = [aviso] if aviso else []
    if not municipio:  # serviço de incidência no local da prestação, sem município da prestação
        decisao = _decisao(
            Situacao.INDETERMINADA,
            None,
            "O ISSQN deste serviço é devido no local da prestação, mas a nota não tem o município "
            "da prestação.",
        )
        return Avaliacao(
            False,
            decisao,
            decisao.explicacao + " Informe o município da prestação na nota.",
            None,
            regra,
            None,
            avisos,
            origem_prestacao,
        )
    convenio = convenio_do_municipio(municipio)
    ativo = None
    if convenio is not None:
        ativacao = convenio.get("data_ativacao")
        if isinstance(ativacao, str):
            ativacao = dt.date.fromisoformat(ativacao)
        ativo = convenio_ativo_na_data(
            aderente=convenio.get("aderente"), data_ativacao=ativacao, competencia=competencia
        )
    decisao = decidir_aliquota(
        opcao_simples=parametros.opcao_simples,
        regime_apuracao=parametros.regime_apuracao_simples,
        regime_especial=parametros.regime_especial,
        convenio_ativo=ativo,
        iss_retido=iss_retido,
    )
    envia, bloqueio = aplicar_ao_valor(decisao, servico.get("aliquota_iss"))
    return Avaliacao(envia, decisao, bloqueio, municipio, regra, ativo, avisos, origem_prestacao)
