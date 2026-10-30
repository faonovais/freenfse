"""Fixtures dos testes fiscais."""

import pytest

from cadastros.tests.conftest import Api
from conftest import CNPJ_A, CNPJ_B
from core.models import Empresa
from core.permissoes import Perfil


@pytest.fixture
def api_de(cliente_de, vincular, usuario):
    """`api_de(empresa, perfil)`: vincula o usuário comum à empresa e devolve o cliente."""

    def _api(empresa, perfil=Perfil.ADMINISTRADOR, **extra):
        vincular(usuario, empresa, perfil, **extra)
        return Api(cliente_de(usuario), empresa)

    return _api


@pytest.fixture
def api_do_master(cliente_de, master):
    """`api_do_master(empresa)`: o Master operando a empresa."""

    def _api(empresa):
        return Api(cliente_de(master), empresa)

    return _api


# -- emissão com a Sefin simulada ---------------------------------------------------------


@pytest.fixture
def relogio_fiscal():
    """Relógio dos testes de emissão (2026-11-02, antes da virada de leiaute de produção)."""
    from fiscal.tests.apoio import RelogioControlavel

    return RelogioControlavel()


@pytest.fixture
def sefin(monkeypatch, relogio_fiscal):
    """Sefin simulada no lugar do transporte HTTP: nada sai para a rede e nada dorme."""
    from fiscal.services import emissao
    from fiscal.tests.sefin_simulada import SefinSimulada

    simulada = SefinSimulada()
    monkeypatch.setattr(
        emissao,
        "opcoes_de_execucao",
        lambda: {"transporte": simulada, "pausa": lambda _s: None, "relogio": relogio_fiscal},
    )
    return simulada


@pytest.fixture
def empresa_pronta(empresa_a):
    """Empresa A pronta para emitir (certificado, parâmetros e convênio), com o schema ativo."""
    from django_tenants.utils import schema_context

    from fiscal.tests.apoio import preparar_empresa_para_emitir

    with schema_context(empresa_a.schema_name):
        preparar_empresa_para_emitir(empresa_a)
        yield empresa_a


@pytest.fixture
def nova_nota(empresa_pronta):
    """Fábrica de rascunhos: `nova_nota(valor="1000.00")` no schema ativo."""
    from fiscal.tests.apoio import criar_rascunho_de_teste

    def _criar(**ajustes):
        return criar_rascunho_de_teste(**ajustes)

    return _criar


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
