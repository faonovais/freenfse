"""Apoio dos testes de cadastros: chamadas à API com a empresa ativa (`X-Empresa`)."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django_tenants.utils import schema_context

from cadastros.models import Pessoa
from conftest import CNPJ_C, CPF_A, CPF_B
from core.permissoes import Perfil


class Api:
    """Cliente HTTP de um usuário numa empresa: `api.get(url)`, `api.post(url, dados)`…"""

    def __init__(self, cliente, empresa):
        self.cliente, self.empresa = cliente, empresa

    def _cabecalho(self):
        return {"HTTP_X_EMPRESA": str(self.empresa.pk)}

    def get(self, url, **params):
        return self.cliente.get(url, params, **self._cabecalho())

    def post(self, url, dados=None):
        return self.cliente.post(url, dados or {}, format="json", **self._cabecalho())

    def patch(self, url, dados):
        return self.cliente.patch(url, dados, format="json", **self._cabecalho())

    def post_arquivo(self, url, arquivo, nome="arquivo.bin", campo="arquivo", **campos):
        """POST multipart com um arquivo (certificado, logo)."""
        enviado = SimpleUploadedFile(nome, arquivo)
        return self.cliente.post(
            url, {campo: enviado, **campos}, format="multipart", **self._cabecalho()
        )

    def put_arquivo(self, url, arquivo, nome="arquivo.bin", campo="arquivo", **campos):
        """PUT multipart com um arquivo."""
        enviado = SimpleUploadedFile(nome, arquivo)
        return self.cliente.put(
            url, {campo: enviado, **campos}, format="multipart", **self._cabecalho()
        )

    def delete(self, url):
        return self.cliente.delete(url, **self._cabecalho())


@pytest.fixture
def api_de(cliente_de, vincular, usuario):
    """`api_de(empresa, perfil)`: vincula o usuário comum à empresa e devolve a `Api`."""

    def _api(empresa, perfil=Perfil.EMISSOR, **extra):
        vincular(usuario, empresa, perfil, **extra)
        return Api(cliente_de(usuario), empresa)

    return _api


@pytest.fixture
def api_do_master(cliente_de, master):
    """`api_do_master(empresa)`: o Master operando a empresa."""

    def _api(empresa):
        return Api(cliente_de(master), empresa)

    return _api


def pessoa_pf(**extra):
    """Dados de uma pessoa física nacional válida (JSON da API)."""
    return {
        "tipo": "pf",
        "documento": CPF_A,
        "nome": "Maria Teste da Silva",
        "logradouro": "Rua das Flores",
        "numero": "100",
        "bairro": "Centro",
        "cep": "77001000",
        "codigo_municipio": "1721000",
        **extra,
    }


def pessoa_pj(**extra):
    """Dados de uma pessoa jurídica nacional válida (JSON da API)."""
    return {
        "tipo": "pj",
        "documento": CNPJ_C,
        "nome": "Comercial Teste Ltda",
        "logradouro": "Avenida Principal",
        "numero": "S/N",
        "bairro": "Distrito Industrial",
        "cep": "65800000",
        "codigo_municipio": "2101400",
        **extra,
    }


def pessoa_estrangeira(**extra):
    """Dados de um estrangeiro com NIF, sem endereço (JSON da API)."""
    return {"tipo": "estrangeiro", "nif": "AB1234567", "nome": "John Test", **extra}


def servico_json(**extra):
    """Dados de um serviço válido (JSON da API)."""
    return {
        "nome": "Consultoria agrícola",
        "descricao": "Serviços de consultoria e assessoria técnica agrícola.",
        "codigo_tributacao_nacional": "170101",
        "aliquota_iss": "3.00",
        "vigencia_inicio": "2026-01-01",
        **extra,
    }


@pytest.fixture
def criar_pessoa():
    """`criar_pessoa(empresa, **campos)`: grava uma pessoa direto no schema da empresa."""

    def _criar(empresa, **campos):
        dados = {"tipo": "pf", "documento": CPF_B, "nome": "Pessoa de Teste", **campos}
        with schema_context(empresa.schema_name):
            pessoa = Pessoa(**{**pessoa_pf(), **dados})
            pessoa.clean()
            pessoa.save()
            return pessoa

    return _criar
