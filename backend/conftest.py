"""Fixtures compartilhadas. Todos os dados são fictícios.

CNPJs de teste têm dígito verificador válido (gerados por `calcular_digitos_cnpj`);
e-mails usam o domínio reservado `.test`; senhas são descartáveis.
"""

import pytest
from allauth.account.models import EmailAddress
from rest_framework.test import APIClient

from core.models import Empresa, Usuario, VinculoUsuarioEmpresa
from core.permissoes import Perfil
from core.validators import calcular_digitos_cnpj

SENHA_DE_TESTE = "senha-descartavel-de-teste-93"


def cnpj_de_teste(base12):
    """Completa uma base de 12 posições com os dígitos verificadores."""
    return base12 + calcular_digitos_cnpj(base12)


CNPJ_A = cnpj_de_teste("112223330001")  # 11222333000181
CNPJ_B = cnpj_de_teste("114447770001")  # 11444777000161
CNPJ_C = cnpj_de_teste("112223330002")


def criar_usuario_de_teste(email, *, master=False, perfil_senha=SENHA_DE_TESTE, **extra):
    """Cria um usuário já com e-mail verificado no allauth."""
    fabrica = Usuario.objects.create_superuser if master else Usuario.objects.create_user
    usuario = fabrica(email=email, password=perfil_senha, nome=email.split("@")[0], **extra)
    EmailAddress.objects.create(user=usuario, email=usuario.email, verified=True, primary=True)
    return usuario


@pytest.fixture
def empresa_a(db):
    """Primeira empresa de teste (com schema próprio)."""
    return Empresa.objects.create(razao_social="Empresa Alfa Teste Ltda", cnpj=CNPJ_A)


@pytest.fixture
def empresa_b(db):
    """Segunda empresa de teste (com schema próprio)."""
    return Empresa.objects.create(razao_social="Empresa Beta Teste Ltda", cnpj=CNPJ_B)


@pytest.fixture
def master(db):
    """Usuário com papel Master."""
    return criar_usuario_de_teste("master@exemplo.test", master=True)


@pytest.fixture
def usuario(db):
    """Usuário comum, sem vínculos."""
    return criar_usuario_de_teste("usuario@exemplo.test")


@pytest.fixture
def vincular(db):
    """Fábrica de vínculos: `vincular(usuario, empresa, Perfil.EMISSOR, ...)`."""

    def _vincular(usuario, empresa, perfil=Perfil.CONSULTA, **extra):
        return VinculoUsuarioEmpresa.objects.create(
            usuario=usuario, empresa=empresa, perfil=perfil, **extra
        )

    return _vincular


@pytest.fixture
def cliente_de():
    """Fábrica de clientes HTTP autenticados por sessão: `cliente_de(usuario)`."""

    def _cliente(usuario=None):
        cliente = APIClient()
        if usuario is not None:
            cliente.force_login(usuario)
        return cliente

    return _cliente


@pytest.fixture(autouse=True)
def _cache_limpo():
    """Isola os testes: contadores de bloqueio de login e códigos 2FA usados ficam no cache."""
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()
