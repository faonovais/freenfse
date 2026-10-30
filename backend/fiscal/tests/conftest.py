"""Fixtures dos testes fiscais."""

import pytest

from cadastros.tests.conftest import Api
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
