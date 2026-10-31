"""Cálculo de valores: ISS, retenções, descontos e dedução (Decimal, meio para cima)."""

from decimal import Decimal

import pytest

from fiscal.services.calculo import ErroDeValores, calcular

SERVICO = {
    "aliquota_iss": "2.00",
    "iss_retido": False,
    "retencao_irrf": None,
    "retencao_csll": None,
    "retencao_inss": None,
}


def test_iss_simples_sobre_o_valor_do_servico():
    totais = calcular({"servico": "1000.00"}, SERVICO)

    assert totais.base_calculo == Decimal("1000.00")
    assert totais.valor_iss == Decimal("20.00")
    assert totais.valor_liquido == Decimal("1000.00")  # ISS não retido não reduz o líquido


def test_iss_retido_reduz_o_liquido():
    totais = calcular({"servico": "1000.00"}, {**SERVICO, "iss_retido": True})

    assert totais.iss_retido and totais.total_retencoes == Decimal("20.00")
    assert totais.valor_liquido == Decimal("980.00")


def test_retencoes_federais_incidem_sobre_a_base():
    servico = {
        **SERVICO,
        "retencao_irrf": "1.50",
        "retencao_csll": "1.00",
        "retencao_inss": "11.00",
    }
    totais = calcular({"servico": "2000.00"}, servico)

    assert (totais.retencao_irrf, totais.retencao_csll, totais.retencao_inss) == (
        Decimal("30.00"),
        Decimal("20.00"),
        Decimal("220.00"),
    )
    assert totais.valor_liquido == Decimal("1730.00")


def test_desconto_incondicionado_reduz_a_base_e_o_liquido_o_condicionado_nao():
    totais = calcular(
        {
            "servico": "1000.00",
            "desconto_incondicionado": "100.00",
            "desconto_condicionado": "50.00",
        },
        SERVICO,
    )

    assert totais.base_calculo == Decimal("900.00")
    assert totais.valor_iss == Decimal("18.00")
    assert totais.valor_liquido == Decimal("900.00")


def test_deducao_em_valor_e_em_percentual():
    em_valor = calcular({"servico": "1000.00", "deducao_valor": "200.00"}, SERVICO)
    em_percentual = calcular({"servico": "1000.00", "deducao_percentual": "20"}, SERVICO)

    assert em_valor.base_calculo == em_percentual.base_calculo == Decimal("800.00")


def test_arredondamento_meio_para_cima_em_centavos():
    totais = calcular({"servico": "100.25"}, {**SERVICO, "aliquota_iss": "5.00"})

    assert totais.valor_iss == Decimal("5.01")  # 5,0125 → 5,01; 5,015 sobe


@pytest.mark.parametrize(
    ("valores", "campo"),
    [
        ({}, "servico"),
        ({"servico": "0"}, "servico"),
        ({"servico": "abc"}, "servico"),
        ({"servico": "-5"}, "servico"),
        ({"servico": "10.123"}, "servico"),
        ({"servico": "100", "desconto_incondicionado": "150"}, "desconto_incondicionado"),
        ({"servico": "100", "deducao_valor": "150"}, "deducao_valor"),
        ({"servico": "100", "deducao_valor": "10", "deducao_percentual": "10"}, "deducao_valor"),
        ({"servico": "100", "deducao_percentual": "150"}, "deducao_percentual"),
    ],
)
def test_valores_invalidos_apontam_o_campo(valores, campo):
    with pytest.raises(ErroDeValores) as erro:
        calcular(valores, SERVICO)

    assert campo in erro.value.erros


def test_virgula_decimal_e_aceita():
    assert calcular({"servico": "1500,50"}, SERVICO).valor_servico == Decimal("1500.50")
