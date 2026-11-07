"""Regra única de `pAliq` (Anexo VI, E0595–E0640): um teste tabular por código de erro da Sefin."""

import datetime as dt
from decimal import Decimal
from types import SimpleNamespace

import pytest

from fiscal.services import aliquota_issqn as regra
from fiscal.services.aliquota_issqn import Situacao

NAO_OPTANTE, MEI, ME_EPP = 1, 2, 3
PELO_SIMPLES, FORA_ISSQN, FORA_TUDO = 1, 2, 3
OBRIG, PROIB, FACUL = Situacao.OBRIGATORIA, Situacao.PROIBIDA, Situacao.FACULTATIVA

# (id/código, opSimpNac, regApTribSN, regEspTrib, convênio ativo, ISS retido, situação, mínimo)
TABELA = [
    ("E0600-mei-convenio-ativo", MEI, None, 0, True, False, PROIB, None),
    ("E0600-mei-convenio-nao-ativo", MEI, None, 0, False, True, PROIB, None),
    ("E0617-nao-optante-convenio-ativo", NAO_OPTANTE, None, 0, True, False, PROIB, None),
    ("E0617-nao-optante-convenio-ativo-retido", NAO_OPTANTE, None, 0, True, True, PROIB, None),
    ("E0619-nao-optante-convenio-nao-ativo", NAO_OPTANTE, None, 0, False, False, OBRIG, None),
    ("E0621-simples1-ativo-retido", ME_EPP, PELO_SIMPLES, 0, True, True, OBRIG, Decimal("1.8")),
    ("E0625-simples1-ativo-sem-retencao", ME_EPP, PELO_SIMPLES, 0, True, False, PROIB, None),
    (
        "E0628-simples1-nao-ativo-retido",
        ME_EPP,
        PELO_SIMPLES,
        0,
        False,
        True,
        OBRIG,
        Decimal("1.8"),
    ),
    ("E0631-simples1-nao-ativo-sem-retencao", ME_EPP, PELO_SIMPLES, 0, False, False, PROIB, None),
    ("E0635-simples2-ativo", ME_EPP, FORA_ISSQN, 0, True, False, PROIB, None),
    ("E0635-simples3-ativo-retido", ME_EPP, FORA_TUDO, 0, True, True, PROIB, None),
    ("E0640-simples2-nao-ativo", ME_EPP, FORA_ISSQN, 0, False, False, OBRIG, None),
    ("E0640-simples3-nao-ativo-retido", ME_EPP, FORA_TUDO, 0, False, True, OBRIG, None),
]
CODIGO_ESPERADO = {identificador: identificador.split("-")[0] for identificador, *_ in TABELA}


@pytest.mark.parametrize(
    ("identificador", "opcao", "apuracao", "especial", "ativo", "retido", "situacao", "minimo"),
    TABELA,
    ids=[linha[0] for linha in TABELA],
)
def test_cada_regra_da_sefin(
    identificador, opcao, apuracao, especial, ativo, retido, situacao, minimo
):
    decisao = regra.decidir_aliquota(
        opcao_simples=opcao,
        regime_apuracao=apuracao,
        regime_especial=especial,
        convenio_ativo=ativo,
        iss_retido=retido,
    )

    assert decisao.situacao is situacao
    assert decisao.codigo == CODIGO_ESPERADO[identificador]
    assert decisao.minimo == minimo
    assert decisao.explicacao


def test_o_caso_grave_da_issue_nao_optante_em_municipio_conveniado_nao_envia_a_aliquota():
    """Antes da correção o gateway mandava `pAliq` e a Sefin rejeitava todas as notas (E0617)."""
    decisao = regra.decidir_aliquota(
        opcao_simples=NAO_OPTANTE,
        regime_apuracao=None,
        regime_especial=0,
        convenio_ativo=True,
        iss_retido=False,
    )
    envia, bloqueio = regra.aplicar_ao_valor(decisao, "2.00")

    assert (envia, bloqueio) == (False, None)


@pytest.mark.parametrize("especial", [1, 2, 3, 4, 5, 6])
def test_e0604_regime_especial_proibe_a_aliquota_do_nao_optante(especial):
    decisao = regra.decidir_aliquota(
        opcao_simples=NAO_OPTANTE,
        regime_apuracao=None,
        regime_especial=especial,
        convenio_ativo=False,
        iss_retido=False,
    )

    assert (decisao.situacao, decisao.codigo) == (PROIB, "E0604")


@pytest.mark.parametrize("especial", [1, 6])
def test_e0604_contra_regra_que_obriga_e_conflito_e_bloqueia(especial):
    """ME/EPP com regime especial e a regra E0640 exigindo `pAliq`: o anexo não diz quem vence."""
    decisao = regra.decidir_aliquota(
        opcao_simples=ME_EPP,
        regime_apuracao=FORA_ISSQN,
        regime_especial=especial,
        convenio_ativo=False,
        iss_retido=False,
    )
    envia, bloqueio = regra.aplicar_ao_valor(decisao, "2.00")

    assert decisao.situacao is Situacao.CONFLITO and decisao.codigo == "E0640/E0604"
    assert envia is False and "E0604" in bloqueio and "emissor oficial" in bloqueio


def test_e0604_com_regra_que_ja_proibe_mantem_o_codigo_especifico():
    decisao = regra.decidir_aliquota(
        opcao_simples=ME_EPP,
        regime_apuracao=PELO_SIMPLES,
        regime_especial=6,
        convenio_ativo=True,
        iss_retido=False,
    )

    assert (decisao.situacao, decisao.codigo) == (PROIB, "E0625")


def test_regime_especial_outros_nao_tem_regra_no_anexo_e_a_aliquota_fica_facultativa():
    decisao = regra.decidir_aliquota(
        opcao_simples=NAO_OPTANTE,
        regime_apuracao=None,
        regime_especial=9,
        convenio_ativo=False,
        iss_retido=False,
    )

    assert decisao.situacao is FACUL and decisao.codigo is None
    assert regra.aplicar_ao_valor(decisao, "3.00") == (True, None)
    assert regra.aplicar_ao_valor(decisao, None) == (False, None)


def test_regime_especial_outros_em_municipio_conveniado_segue_a_e0617():
    decisao = regra.decidir_aliquota(
        opcao_simples=NAO_OPTANTE,
        regime_apuracao=None,
        regime_especial=9,
        convenio_ativo=True,
        iss_retido=False,
    )

    assert (decisao.situacao, decisao.codigo) == (PROIB, "E0617")


def test_sem_saber_o_convenio_a_decisao_e_indeterminada_e_bloqueia():
    decisao = regra.decidir_aliquota(
        opcao_simples=NAO_OPTANTE,
        regime_apuracao=None,
        regime_especial=0,
        convenio_ativo=None,
        iss_retido=False,
    )
    envia, bloqueio = regra.aplicar_ao_valor(decisao, "2.00")

    assert decisao.situacao is Situacao.INDETERMINADA
    assert envia is False and "convênio ativo" in bloqueio


def test_mei_nao_depende_do_convenio():
    decisao = regra.decidir_aliquota(
        opcao_simples=MEI,
        regime_apuracao=None,
        regime_especial=0,
        convenio_ativo=None,
        iss_retido=False,
    )

    assert (decisao.situacao, decisao.codigo) == (PROIB, "E0600")


def test_me_epp_sem_regime_de_apuracao_e_indeterminada():
    decisao = regra.decidir_aliquota(
        opcao_simples=ME_EPP,
        regime_apuracao=None,
        regime_especial=0,
        convenio_ativo=True,
        iss_retido=False,
    )

    assert decisao.situacao is Situacao.INDETERMINADA
    assert "apurados" in decisao.explicacao


# -- o valor da alíquota -------------------------------------------------------------------------


def _obrigatoria(minimo=None):
    return regra.Decisao(OBRIG, "E0621", "explicação", minimo)


def test_obrigatoria_sem_aliquota_no_servico_bloqueia_com_o_codigo_da_regra():
    envia, bloqueio = regra.aplicar_ao_valor(_obrigatoria(), None)

    assert envia is False
    assert "E0621" in bloqueio and "alíquota" in bloqueio and "cadastro do serviço" in bloqueio


@pytest.mark.parametrize(
    ("aliquota", "envia", "bloqueia"),
    [
        ("1.79", False, True),
        ("1.80", True, False),
        ("1.81", True, False),
        ("0", False, True),
        (Decimal("2"), True, False),
    ],
)
def test_minimo_de_1_8_por_cento_quando_ha_retencao(aliquota, envia, bloqueia):
    resultado = regra.aplicar_ao_valor(_obrigatoria(Decimal("1.8")), aliquota)

    assert resultado[0] is envia
    assert (resultado[1] is not None) is bloqueia
    if bloqueia:
        assert "1.8%" in resultado[1] and "E0621" in resultado[1]


def test_sem_minimo_aceita_aliquota_baixa_quando_obrigatoria():
    assert regra.aplicar_ao_valor(_obrigatoria(None), "0.5") == (True, None)


def test_e0595_teto_de_5_por_cento():
    assert regra.aplicar_ao_valor(_obrigatoria(), "5") == (True, None)
    envia, bloqueio = regra.aplicar_ao_valor(_obrigatoria(), "5.01")

    assert envia is False and "E0595" in bloqueio


def test_proibida_nao_envia_mesmo_com_aliquota_cadastrada_e_nao_bloqueia():
    decisao = regra.Decisao(PROIB, "E0617", "explicação")

    assert regra.aplicar_ao_valor(decisao, "2.00") == (False, None)
    assert regra.aplicar_ao_valor(decisao, None) == (False, None)


# -- convênio ativo na data de competência ---------------------------------------------------------


@pytest.mark.parametrize(
    ("aderente", "ativacao", "competencia", "esperado"),
    [
        (True, None, dt.date(2026, 11, 1), True),
        (True, dt.date(2024, 5, 2), dt.date(2026, 11, 1), True),
        (True, dt.date(2026, 11, 1), dt.date(2026, 11, 1), True),  # ativa no próprio dia
        (True, dt.date(2026, 11, 2), dt.date(2026, 11, 1), False),  # ativação futura
        (True, dt.date(2999, 1, 1), dt.date(2026, 11, 1), False),
        (False, dt.date(2024, 5, 2), dt.date(2026, 11, 1), False),
        (None, dt.date(2024, 5, 2), dt.date(2026, 11, 1), None),
    ],
)
def test_convenio_ativo_na_data_de_competencia(aderente, ativacao, competencia, esperado):
    assert (
        regra.convenio_ativo_na_data(
            aderente=aderente, data_ativacao=ativacao, competencia=competencia
        )
        is esperado
    )


# -- município de incidência (Anexo VI) -----------------------------------------------------------

EMISSOR, TOMADOR, PRESTACAO = "2101400", "3550308", "4106902"


def _incidencia(codigo, tomador=TOMADOR, prestacao=PRESTACAO):
    return regra.municipio_de_incidencia(
        codigo_tributacao_nacional=codigo,
        municipio_emissor=EMISSOR,
        municipio_tomador=tomador,
        municipio_prestacao=prestacao,
    )


def test_regra_geral_o_servico_incide_no_municipio_do_prestador():
    assert _incidencia("010101") == (EMISSOR, "EP", None)


def test_local_da_prestacao_incide_no_municipio_da_prestacao_da_nota():
    assert _incidencia("030401") == (PRESTACAO, "LP", None)


def test_local_da_prestacao_com_a_prestacao_no_proprio_emissor_incide_no_emissor():
    assert _incidencia("030401", prestacao=EMISSOR) == (EMISSOR, "LP", None)


def test_local_da_prestacao_sem_municipio_da_prestacao_nao_inventa_um():
    # Nunca cai no emissor às escondidas: quem chama bloqueia a nota.
    assert _incidencia("030401", prestacao=None) == (None, "LP", None)
    assert _incidencia("030401", prestacao="") == (None, "LP", None)


def test_o_municipio_da_prestacao_nao_muda_a_incidencia_de_quem_nao_e_do_local_da_prestacao():
    assert _incidencia("010101") == (EMISSOR, "EP", None)  # estabelecimento do prestador
    assert _incidencia("170501") == (TOMADOR, "ET", None)  # estabelecimento do tomador
    municipio, regra_, _ = _incidencia("990101")  # sem incidência: regra geral
    assert (municipio, regra_) == (EMISSOR, "EP")
    municipio, regra_, _ = _incidencia("999999")  # fora do anexo: regra geral
    assert (municipio, regra_) == (EMISSOR, "EP")


def test_fornecimento_de_mao_de_obra_incide_no_municipio_do_tomador():
    assert _incidencia("170501") == (TOMADOR, "ET", None)


def test_mao_de_obra_com_tomador_sem_municipio_volta_a_regra_geral_e_avisa():
    municipio, regra_, aviso = _incidencia("170501", tomador=None)

    assert (municipio, regra_) == (EMISSOR, "EP")
    assert "município brasileiro" in aviso


def test_servico_fora_do_anexo_usa_a_regra_geral_e_avisa():
    municipio, regra_, aviso = _incidencia("999999")

    assert (municipio, regra_) == (EMISSOR, "EP")
    assert "não consta" in aviso


def test_servico_sem_incidencia_usa_a_regra_geral_e_avisa():
    municipio, regra_, aviso = _incidencia("990101")

    assert (municipio, regra_) == (EMISSOR, "EP")
    assert "sem incidência" in aviso


# -- avaliação completa ---------------------------------------------------------------------------


def _parametros(**campos):
    base = {
        "codigo_municipio_emissor": EMISSOR,
        "opcao_simples": NAO_OPTANTE,
        "regime_apuracao_simples": None,
        "regime_especial": 0,
    }
    return SimpleNamespace(**{**base, **campos})


def _avaliar(
    parametros,
    convenio,
    *,
    servico="010101",
    aliquota="2.00",
    retido=False,
    prestacao=EMISSOR,
    origem="emissor",
):
    consultados = []

    def convenio_do_municipio(codigo):
        consultados.append(codigo)
        return convenio

    resultado = regra.avaliar(
        parametros=parametros,
        servico={"codigo_tributacao_nacional": servico, "aliquota_iss": aliquota},
        competencia=dt.date(2026, 11, 1),
        iss_retido=retido,
        municipio_tomador=TOMADOR,
        municipio_prestacao=prestacao,
        origem_prestacao=origem,
        convenio_do_municipio=convenio_do_municipio,
    )
    return resultado, consultados


def test_avaliacao_nao_optante_em_municipio_ativo_nao_envia_e_explica():
    resultado, consultados = _avaliar(
        _parametros(), {"aderente": True, "data_ativacao": "2024-05-02"}
    )

    assert consultados == [EMISSOR]
    assert resultado.envia is False and resultado.bloqueio is None
    dados = resultado.para_dict()
    assert dados["codigo_regra"] == "E0617" and dados["convenio_ativo"] is True
    assert dados["municipio_incidencia"] == EMISSOR and dados["regra_incidencia"] == "EP"


def test_avaliacao_competencia_antes_da_ativacao_conta_como_convenio_nao_ativo():
    resultado, _ = _avaliar(_parametros(), {"aderente": True, "data_ativacao": "2026-11-02"})

    assert resultado.envia is True
    assert resultado.para_dict()["codigo_regra"] == "E0619"


def test_avaliacao_consulta_o_convenio_do_municipio_de_incidencia_nao_o_do_emissor():
    _, consultados = _avaliar(
        _parametros(), {"aderente": True, "data_ativacao": None}, servico="170501"
    )

    assert consultados == [TOMADOR]


def test_avaliacao_sem_convenio_conhecido_bloqueia():
    resultado, _ = _avaliar(_parametros(), None)

    assert resultado.envia is False
    assert resultado.decisao.situacao is Situacao.INDETERMINADA
    assert resultado.bloqueio


def test_avaliacao_simples_com_retencao_abaixo_do_minimo_bloqueia():
    parametros = _parametros(opcao_simples=ME_EPP, regime_apuracao_simples=PELO_SIMPLES)
    resultado, _ = _avaliar(
        parametros, {"aderente": True, "data_ativacao": None}, aliquota="1.50", retido=True
    )

    assert resultado.envia is False
    assert "E0621" in resultado.bloqueio and "1.8%" in resultado.bloqueio


def test_avaliacao_local_da_prestacao_consulta_o_convenio_do_municipio_da_prestacao():
    resultado, consultados = _avaliar(
        _parametros(),
        {"aderente": True, "data_ativacao": "2024-05-02"},
        servico="030401",
        prestacao=PRESTACAO,
        origem="nota",
    )

    assert consultados == [PRESTACAO]
    dados = resultado.para_dict()
    assert dados["municipio_incidencia"] == PRESTACAO and dados["regra_incidencia"] == "LP"
    assert dados["origem_prestacao"] == "nota"
    assert dados["codigo_regra"] == "E0617" and resultado.envia is False


def test_avaliacao_local_da_prestacao_usa_a_data_de_ativacao_do_municipio_da_prestacao():
    # O convênio do município da prestação só vale a partir de 2026-12-01; a competência é de
    # novembro: para esse município o convênio ainda não estava ativo e a alíquota é obrigatória.
    resultado, _ = _avaliar(
        _parametros(),
        {"aderente": True, "data_ativacao": "2026-12-01"},
        servico="030401",
        prestacao=PRESTACAO,
        origem="modelo",
    )

    assert resultado.para_dict()["codigo_regra"] == "E0619" and resultado.envia is True


def test_avaliacao_de_servico_que_nao_e_do_local_da_prestacao_ignora_o_municipio_da_prestacao():
    resultado, consultados = _avaliar(
        _parametros(), {"aderente": True, "data_ativacao": None}, prestacao=PRESTACAO, origem="nota"
    )

    assert consultados == [EMISSOR]
    dados = resultado.para_dict()
    assert dados["municipio_incidencia"] == EMISSOR and dados["regra_incidencia"] == "EP"
    assert dados["origem_prestacao"] is None  # só conta nos serviços do local da prestação


def test_avaliacao_local_da_prestacao_sem_municipio_da_prestacao_bloqueia_sem_consultar():
    resultado, consultados = _avaliar(
        _parametros(),
        {"aderente": True, "data_ativacao": None},
        servico="030401",
        prestacao=None,
        origem=None,
    )

    assert consultados == []
    assert resultado.envia is False
    assert resultado.decisao.situacao is Situacao.INDETERMINADA
    assert resultado.municipio_incidencia is None
    assert "município da prestação" in resultado.bloqueio
