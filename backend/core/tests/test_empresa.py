import pytest
from django.db import connection
from django_tenants.utils import schema_exists

from core.models import Empresa


@pytest.mark.django_db(transaction=True)
def test_empresa_cria_e_remove_schema_proprio():
    empresa = Empresa.objects.create(schema_name="empresa_teste", nome="Empresa Teste")
    try:
        assert schema_exists("empresa_teste")
        assert str(empresa) == "Empresa Teste"
        # O schema público continua sendo o ativo: a empresa só é ativada por requisição.
        assert connection.schema_name == "public"
    finally:
        empresa.delete(force_drop=True)

    assert not schema_exists("empresa_teste")
