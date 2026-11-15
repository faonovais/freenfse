"""Apoio dos testes de cadastros: chamadas à API com a empresa ativa (`X-Empresa`)."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django_tenants.utils import schema_context

from cadastros.models import Pessoa
from conftest import CNPJ_C, CPF_A, CPF_B
from core.models import Empresa, ServicoOficial
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

    def put(self, url, dados):
        return self.cliente.put(url, dados, format="json", **self._cabecalho())

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


_OFICIAIS_PADRAO = {
    "010101": {
        "nbs": "115021000",
        "cst_ibs_cbs": "000",
        "c_class_trib": "000001",
        "codigo_indicador_operacao": "100301",
    },
    "170101": {
        "nbs": "106084000",
        "cst_ibs_cbs": "000",
        "c_class_trib": "000001",
        "codigo_indicador_operacao": "100301",
    },
    "171901": {
        "nbs": "113022100",
        "cst_ibs_cbs": "000",
        "c_class_trib": "000001",
        "codigo_indicador_operacao": "100301",
    },
}


def garantir_servico_oficial(empresa=None, **campos):
    """Obtém ou cria um `ServicoOficial` válido e o vincula às empresas de teste."""
    bruto = str(campos.get("codigo_tributacao_nacional", "170101"))
    codigo = "".join(c for c in bruto if c.isdigit())
    padrao = _OFICIAIS_PADRAO.get(codigo, _OFICIAIS_PADRAO["170101"])
    chave = {
        "codigo_tributacao_nacional": codigo if codigo in _OFICIAIS_PADRAO else "170101",
        "nbs": campos.get("nbs", padrao["nbs"]),
        "cst_ibs_cbs": campos.get("cst_ibs_cbs", padrao["cst_ibs_cbs"]),
        "c_class_trib": campos.get("c_class_trib", padrao["c_class_trib"]),
        "codigo_indicador_operacao": campos.get(
            "codigo_indicador_operacao", padrao["codigo_indicador_operacao"]
        ),
    }
    oficial = ServicoOficial.objects.filter(**chave).first()
    if oficial is None:
        oficial = ServicoOficial(**chave)
        oficial.full_clean()
        oficial.save()
    empresas = [empresa] if empresa is not None else list(Empresa.objects.all())
    for item in empresas:
        item.servicos_oficiais.add(oficial)
    return oficial


def servico_json(**extra):
    """Dados de um serviço válido (JSON da API) já vinculado a um `ServicoOficial`."""
    dados = {
        "nome": "Consultoria agrícola",
        "descricao": "Serviços de consultoria e assessoria técnica agrícola.",
        "codigo_tributacao_nacional": "170101",
        "aliquota_iss": "3.00",
        "vigencia_inicio": "2026-01-01",
        **extra,
    }
    if "servico_oficial_id" not in dados:
        oficial = garantir_servico_oficial(
            codigo_tributacao_nacional=dados["codigo_tributacao_nacional"]
        )
        dados["servico_oficial_id"] = oficial.pk
    return dados


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
