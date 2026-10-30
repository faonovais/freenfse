"""Fixtures da persistência fiscal: empresa ativa (schema próprio) e relógio controlável."""

import pytest
from django_tenants.utils import schema_context

from fiscal.tests.apoio import RelogioControlavel


@pytest.fixture
def relogio():
    return RelogioControlavel()


@pytest.fixture
def empresa_ativa(empresa_a):
    """Executa o teste no schema da empresa A (como a requisição faria)."""
    with schema_context(empresa_a.schema_name):
        yield empresa_a


@pytest.fixture
def outra_empresa(empresa_b):
    return empresa_b
