import pytest
from django.core.exceptions import ValidationError
from django.db import connection
from django_tenants.utils import schema_exists

from conftest import CNPJ_A
from core.models import Empresa


def test_empresa_cria_schema_proprio_a_partir_do_cnpj(empresa_a):
    assert empresa_a.schema_name == f"empresa_{CNPJ_A}"
    assert schema_exists(empresa_a.schema_name)
    # O schema público continua sendo o ativo: a empresa só é ativada por requisição.
    assert connection.schema_name == "public"


def test_cnpj_e_normalizado_ao_salvar(db):
    empresa = Empresa.objects.create(
        razao_social="Empresa Pontuada Ltda", cnpj="11.222.333/0001-81"
    )

    assert empresa.cnpj == "11222333000181"
    assert empresa.cnpj_formatado == "11.222.333/0001-81"
    assert str(empresa) == "Empresa Pontuada Ltda (11.222.333/0001-81)"


def test_cnpj_invalido_e_recusado_na_validacao(db):
    empresa = Empresa(razao_social="Empresa Invalida", cnpj="11222333000182")

    with pytest.raises(ValidationError) as erro:
        empresa.full_clean(exclude=["schema_name"])

    assert "cnpj" in erro.value.message_dict


def test_excluir_a_empresa_nao_remove_o_schema(empresa_a):
    schema = empresa_a.schema_name

    empresa_a.delete()

    # Guarda legal: dados fiscais não podem ser destruídos por uma exclusão acidental.
    assert schema_exists(schema)
