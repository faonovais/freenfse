"""Fixtures compartilhadas. Todos os dados são fictícios.

CNPJs de teste têm dígito verificador válido (gerados por `calcular_digitos_cnpj`);
e-mails usam o domínio reservado `.test`; senhas são descartáveis.
"""

import pytest
from allauth.account.models import EmailAddress
from rest_framework.test import APIClient

from core.models import Empresa, Municipio, Usuario, VinculoUsuarioEmpresa
from core.municipios import ler_arquivo, normalizar_nome
from core.permissoes import Perfil
from core.validators import calcular_digitos_cnpj

SENHA_DE_TESTE = "senha-descartavel-de-teste-93"


def cnpj_de_teste(base12):
    """Completa uma base de 12 posições com os dígitos verificadores."""
    return base12 + calcular_digitos_cnpj(base12)


CNPJ_A = cnpj_de_teste("112223330001")  # 11222333000181
CNPJ_B = cnpj_de_teste("114447770001")  # 11444777000161
CNPJ_C = cnpj_de_teste("112223330002")


def cpf_de_teste(base9):
    """Completa uma base de 9 dígitos com os dois dígitos verificadores do CPF."""
    cpf = base9
    for tamanho in (9, 10):
        soma = sum(int(d) * p for d, p in zip(cpf, range(tamanho + 1, 1, -1), strict=True))
        cpf += str((soma * 10) % 11 % 10)
    return cpf


CPF_A = cpf_de_teste("529982247")  # 52998224725
CPF_B = cpf_de_teste("111444777")  # 11144477735
CODIGOS_DE_MUNICIPIOS_BASICOS = (
    "3550308",  # São Paulo/SP
    "1721000",  # Palmas/TO
    "2101400",  # Balsas/MA
    "2903201",  # Barreiras/BA
    "2211001",  # Teresina/PI
)


def criar_usuario_de_teste(email, *, master=False, perfil_senha=SENHA_DE_TESTE, **extra):
    """Cria um usuário já com e-mail verificado no allauth."""
    fabrica = Usuario.objects.create_superuser if master else Usuario.objects.create_user
    usuario = fabrica(email=email, password=perfil_senha, nome=email.split("@")[0], **extra)
    EmailAddress.objects.create(user=usuario, email=usuario.email, verified=True, primary=True)
    return usuario


@pytest.fixture
def municipios_basicos(db):
    """Alguns municípios reais (do arquivo versionado do IBGE) no schema público."""
    linhas = [m for m in ler_arquivo() if m[0] in CODIGOS_DE_MUNICIPIOS_BASICOS]
    Municipio.objects.bulk_create(
        [Municipio(codigo=c, nome=n, uf=u, nome_busca=normalizar_nome(n)) for c, n, u in linhas]
    )
    return {codigo: nome for codigo, nome, _ in linhas}


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
