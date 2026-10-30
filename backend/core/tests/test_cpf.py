"""CPF: validação do dígito verificador e formatação (dados fictícios)."""

import pytest
from django.core.exceptions import ValidationError

from core.validators import cpf_valido, formatar_cpf, normalizar_cpf, validar_cpf

# CPFs de teste com dígito verificador válido (geração aritmética, não pertencem a pessoas).
VALIDOS = ["52998224725", "111.444.777-35", "529.982.247-25"]
INVALIDOS = [
    "52998224724",  # dígito errado
    "11111111111",  # sequência repetida
    "00000000000",
    "123",  # curto
    "",
    None,
    "5299822472a",
]


@pytest.mark.parametrize("cpf", VALIDOS)
def test_cpf_valido_com_ou_sem_pontuacao(cpf):
    assert cpf_valido(cpf) is True
    validar_cpf(cpf)  # não levanta


@pytest.mark.parametrize("cpf", INVALIDOS)
def test_cpf_invalido_e_recusado(cpf):
    assert cpf_valido(cpf) is False
    with pytest.raises(ValidationError) as erro:
        validar_cpf(cpf)
    assert erro.value.code == "cpf_invalido"


def test_normalizar_e_formatar():
    assert normalizar_cpf("529.982.247-25") == "52998224725"
    assert formatar_cpf("52998224725") == "529.982.247-25"
    assert formatar_cpf("123") == "123"
