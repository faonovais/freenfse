import pytest

from core.validators import (
    calcular_digitos_cnpj,
    cnpj_valido,
    formatar_cnpj,
    normalizar_cnpj,
)


@pytest.mark.parametrize("cnpj", ["11222333000181", "11.222.333/0001-81", "11444777000161"])
def test_cnpj_numerico_valido(cnpj):
    assert cnpj_valido(cnpj)


@pytest.mark.parametrize(
    "cnpj",
    [
        "11222333000182",  # dígito verificador errado
        "11222333000100",
        "00000000000000",  # sequência repetida
        "1122233300018",  # curto
        "112223330001811",  # longo
        "",
        None,
    ],
)
def test_cnpj_invalido(cnpj):
    assert not cnpj_valido(cnpj)


def test_cnpj_alfanumerico_com_digitos_calculados_e_valido():
    base = "12ABC34501DE"
    cnpj = base + calcular_digitos_cnpj(base)

    assert cnpj_valido(cnpj)
    assert cnpj_valido(cnpj.lower())
    assert not cnpj_valido(base + "00")


def test_normalizacao_e_formatacao():
    assert normalizar_cnpj(" 11.222.333/0001-81 ") == "11222333000181"
    assert formatar_cnpj("11222333000181") == "11.222.333/0001-81"
