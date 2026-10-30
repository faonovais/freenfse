"""Fixtures da persistência fiscal: empresa ativa (schema próprio) e relógio controlável."""

import datetime as dt

import pytest
from django_tenants.utils import schema_context

from conftest import CNPJ_A, CNPJ_B
from core.models import Empresa


class RelogioControlavel:
    """Relógio UTC que só anda quando o teste manda."""

    def __init__(self, inicio):
        self.agora = inicio

    def __call__(self):
        return self.agora

    def avancar(self, **intervalo):
        """Avança o relógio (`avancar(minutes=5)`)."""
        self.agora += dt.timedelta(**intervalo)


@pytest.fixture
def relogio():
    return RelogioControlavel(dt.datetime(2026, 11, 2, 15, 0, tzinfo=dt.UTC))


@pytest.fixture
def empresa_ativa(empresa_a):
    """Executa o teste no schema da empresa A (como a requisição faria)."""
    with schema_context(empresa_a.schema_name):
        yield empresa_a


@pytest.fixture
def outra_empresa(empresa_b):
    return empresa_b


@pytest.fixture
def empresas_confirmadas(transactional_db):
    """Duas empresas com schema próprio **confirmadas** no banco (para threads e processos).

    Os testes de concorrência usam conexões de verdade, que só enxergam dados confirmados.
    O schema é apagado ao final, para o próximo teste não herdar tabelas.
    """
    alfa = Empresa.objects.create(razao_social="Empresa Alfa Teste Ltda", cnpj=CNPJ_A)
    beta = Empresa.objects.create(razao_social="Empresa Beta Teste Ltda", cnpj=CNPJ_B)
    yield alfa, beta
    for empresa in (alfa, beta):
        empresa.delete(force_drop=True)
