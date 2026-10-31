"""Copiar cadastro de outra empresa: exige acesso às duas, é cópia (não vínculo) e é auditada."""

import pytest
from django_tenants.utils import schema_context

from cadastros.models import PerfilPessoa, Pessoa
from cadastros.tests.conftest import Api, pessoa_estrangeira
from conftest import CPF_A, CPF_B
from core.models import LogAuditoria, VinculoUsuarioEmpresa
from core.permissoes import Perfil

COPIA = "/api/cadastros/copia/pessoas/"
pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _municipios(municipios_basicos):
    """Os endereços das pessoas copiadas precisam dos municípios no schema público."""


@pytest.fixture
def origem_com_pessoas(empresa_a, criar_pessoa):
    """Empresa A (origem) com duas pessoas: uma com dois perfis e uma estrangeira."""
    with schema_context(empresa_a.schema_name):
        extra = PerfilPessoa.objects.create(codigo="transportadora", nome="Transportadora")
    maria = criar_pessoa(empresa_a, documento=CPF_A, nome="Maria da Origem")
    estrangeiro = criar_pessoa(
        empresa_a, **{**pessoa_estrangeira(), "documento": "", "nome": "John da Origem"}
    )
    with schema_context(empresa_a.schema_name):
        maria.perfis.set([PerfilPessoa.objects.get(codigo="cliente"), extra])
        estrangeiro.perfis.set([PerfilPessoa.objects.get(codigo="fornecedor")])
    return maria, estrangeiro


@pytest.fixture
def vinculos_nas_duas(vincular, usuario, empresa_a, empresa_b):
    """O usuário é Emissor na origem (A) e no destino (B)."""
    vincular(usuario, empresa_a, Perfil.EMISSOR)
    vincular(usuario, empresa_b, Perfil.EMISSOR)


def _api(cliente_de, usuario, empresa):
    return Api(cliente_de(usuario), empresa)


def _nomes(empresa):
    with schema_context(empresa.schema_name):
        return sorted(Pessoa.objects.values_list("nome", flat=True))


def test_com_vinculo_nas_duas_empresas_copia_as_pessoas(
    cliente_de, usuario, empresa_a, empresa_b, origem_com_pessoas, vinculos_nas_duas
):
    api = _api(cliente_de, usuario, empresa_b)

    resposta = api.post(COPIA, {"empresa_origem": empresa_a.pk, "todas": True})

    assert resposta.status_code == 201, resposta.json()
    assert resposta.json() == {"copiadas": 2, "ignoradas": []}
    assert _nomes(empresa_b) == ["John da Origem", "Maria da Origem"]
    with schema_context(empresa_b.schema_name):
        maria = Pessoa.objects.get(nome="Maria da Origem")
        assert sorted(maria.perfis.values_list("codigo", flat=True)) == [
            "cliente",
            "transportadora",
        ]  # o perfil que só existia na origem foi criado no destino
        assert maria.documento == CPF_A and maria.codigo_municipio == "1721000"
        john = Pessoa.objects.get(nome="John da Origem")
        assert john.nif == "AB1234567" and john.documento == ""


def test_copia_so_das_pessoas_escolhidas(
    cliente_de, usuario, empresa_a, empresa_b, origem_com_pessoas, vinculos_nas_duas
):
    maria, _ = origem_com_pessoas
    api = _api(cliente_de, usuario, empresa_b)

    resposta = api.post(COPIA, {"empresa_origem": empresa_a.pk, "ids": [maria.pk, 999999]})

    assert resposta.json() == {"copiadas": 1, "ignoradas": []}
    assert _nomes(empresa_b) == ["Maria da Origem"]


def test_depois_da_copia_os_dados_sao_independentes(
    cliente_de, usuario, empresa_a, empresa_b, origem_com_pessoas, vinculos_nas_duas
):
    maria, _ = origem_com_pessoas
    api_b = _api(cliente_de, usuario, empresa_b)
    api_a = _api(cliente_de, usuario, empresa_a)
    api_b.post(COPIA, {"empresa_origem": empresa_a.pk, "todas": True})

    # Alterar e desativar a original não mexe na cópia...
    api_a.patch(f"/api/cadastros/pessoas/{maria.pk}/", {"nome": "Maria Alterada", "ativo": False})
    # ...e alterar a cópia não mexe na original.
    copia = next(
        p for p in api_b.get("/api/cadastros/pessoas/").json()["results"] if p["documento"] == CPF_A
    )
    api_b.patch(f"/api/cadastros/pessoas/{copia['id']}/", {"telefone": "63999990000"})

    with schema_context(empresa_b.schema_name):
        na_copia = Pessoa.objects.get(documento=CPF_A)
        assert (na_copia.nome, na_copia.ativo, na_copia.telefone) == (
            "Maria da Origem",
            True,
            "63999990000",
        )
    with schema_context(empresa_a.schema_name):
        original = Pessoa.objects.get(pk=maria.pk)
        assert (original.nome, original.ativo, original.telefone) == ("Maria Alterada", False, "")
        assert Pessoa.objects.count() == 2


def test_copiar_nao_cria_vinculo_nenhum(
    cliente_de, usuario, empresa_a, empresa_b, origem_com_pessoas, vinculos_nas_duas
):
    antes = VinculoUsuarioEmpresa.objects.count()

    _api(cliente_de, usuario, empresa_b).post(
        COPIA, {"empresa_origem": empresa_a.pk, "todas": True}
    )

    assert VinculoUsuarioEmpresa.objects.count() == antes


def test_sem_vinculo_na_origem_recebe_403(
    cliente_de, usuario, vincular, empresa_a, empresa_b, origem_com_pessoas
):
    vincular(usuario, empresa_b, Perfil.EMISSOR)  # só no destino
    api = _api(cliente_de, usuario, empresa_b)

    postar = api.post(COPIA, {"empresa_origem": empresa_a.pk, "todas": True})
    listar = api.get(COPIA, empresa=empresa_a.pk)

    for resposta in (postar, listar):
        assert resposta.status_code == 403
        assert resposta.json()["codigo"] == "sem_acesso_a_empresa"
    assert _nomes(empresa_b) == []


def test_vinculo_revogado_na_origem_tambem_recebe_403(
    cliente_de, usuario, vincular, empresa_a, empresa_b, origem_com_pessoas
):
    vincular(usuario, empresa_a, Perfil.EMISSOR, ativo=False)
    vincular(usuario, empresa_b, Perfil.EMISSOR)

    resposta = _api(cliente_de, usuario, empresa_b).post(
        COPIA, {"empresa_origem": empresa_a.pk, "todas": True}
    )

    assert resposta.status_code == 403


def test_sem_permissao_de_leitura_na_origem_recebe_403(
    cliente_de, usuario, vincular, empresa_a, empresa_b, origem_com_pessoas
):
    vincular(usuario, empresa_a, Perfil.EMISSOR, permissoes_removidas=["cadastro.consultar"])
    vincular(usuario, empresa_b, Perfil.EMISSOR)

    resposta = _api(cliente_de, usuario, empresa_b).post(
        COPIA, {"empresa_origem": empresa_a.pk, "todas": True}
    )

    assert resposta.status_code == 403
    assert _nomes(empresa_b) == []


def test_origem_inexistente_responde_igual_a_sem_acesso(cliente_de, usuario, vincular, empresa_b):
    vincular(usuario, empresa_b, Perfil.EMISSOR)

    inexistente = _api(cliente_de, usuario, empresa_b).post(
        COPIA, {"empresa_origem": 99999, "todas": True}
    )
    invalida = _api(cliente_de, usuario, empresa_b).post(
        COPIA, {"empresa_origem": "abc", "todas": True}
    )

    assert inexistente.status_code == invalida.status_code == 403
    assert inexistente.json() == invalida.json()


def test_exige_cadastro_editar_no_destino(
    cliente_de, usuario, vincular, empresa_a, empresa_b, origem_com_pessoas
):
    vincular(usuario, empresa_a, Perfil.EMISSOR)
    vincular(usuario, empresa_b, Perfil.CONSULTA)  # lê, mas não edita o destino

    resposta = _api(cliente_de, usuario, empresa_b).post(
        COPIA, {"empresa_origem": empresa_a.pk, "todas": True}
    )

    assert resposta.status_code == 403
    assert _nomes(empresa_b) == []


def test_master_copia_sem_vinculo(cliente_de, master, empresa_a, empresa_b, origem_com_pessoas):
    resposta = _api(cliente_de, master, empresa_b).post(
        COPIA, {"empresa_origem": empresa_a.pk, "todas": True}
    )

    assert resposta.status_code == 201
    assert resposta.json()["copiadas"] == 2


def test_documento_ja_existente_no_destino_e_ignorado_com_motivo(
    cliente_de, usuario, empresa_a, empresa_b, origem_com_pessoas, vinculos_nas_duas, criar_pessoa
):
    criar_pessoa(empresa_b, documento=CPF_A, nome="Maria que já existia")
    api = _api(cliente_de, usuario, empresa_b)

    resposta = api.post(COPIA, {"empresa_origem": empresa_a.pk, "todas": True}).json()

    assert resposta["copiadas"] == 1
    assert [i["nome"] for i in resposta["ignoradas"]] == ["Maria da Origem"]
    assert "Já existe" in resposta["ignoradas"][0]["motivo"]
    assert _nomes(empresa_b) == ["John da Origem", "Maria que já existia"]


def test_copiar_duas_vezes_nao_duplica(
    cliente_de, usuario, empresa_a, empresa_b, origem_com_pessoas, vinculos_nas_duas
):
    api = _api(cliente_de, usuario, empresa_b)
    api.post(COPIA, {"empresa_origem": empresa_a.pk, "todas": True})

    segunda = api.post(COPIA, {"empresa_origem": empresa_a.pk, "todas": True}).json()

    assert segunda["copiadas"] == 0 and len(segunda["ignoradas"]) == 2
    assert len(_nomes(empresa_b)) == 2


def test_origem_igual_ao_destino_e_recusada(
    cliente_de, usuario, vincular, empresa_a, origem_com_pessoas
):
    vincular(usuario, empresa_a, Perfil.EMISSOR)

    resposta = _api(cliente_de, usuario, empresa_a).post(
        COPIA, {"empresa_origem": empresa_a.pk, "todas": True}
    )

    assert resposta.status_code == 400


@pytest.mark.parametrize(
    "corpo",
    [
        {},  # nem ids nem todas
        {"ids": [1], "todas": True},  # os dois
        {"ids": []},
        {"ids": ["1"]},
        {"ids": [True]},
        {"ids": list(range(1001))},
        {"todas": "sim"},
    ],
)
def test_pedido_de_copia_mal_formado_e_recusado(
    cliente_de, usuario, empresa_a, empresa_b, origem_com_pessoas, vinculos_nas_duas, corpo
):
    resposta = _api(cliente_de, usuario, empresa_b).post(
        COPIA, {"empresa_origem": empresa_a.pk, **corpo}
    )

    assert resposta.status_code == 400
    assert _nomes(empresa_b) == []


def test_copia_e_auditada_sem_dados_pessoais(
    cliente_de, usuario, empresa_a, empresa_b, origem_com_pessoas, vinculos_nas_duas
):
    _api(cliente_de, usuario, empresa_b).post(
        COPIA, {"empresa_origem": empresa_a.pk, "todas": True}
    )

    registro = LogAuditoria.objects.get(acao=LogAuditoria.Acao.PESSOAS_COPIADAS)
    assert registro.usuario == usuario and registro.empresa == empresa_b
    assert registro.detalhes == {
        "origem": empresa_a.pk,
        "destino": empresa_b.pk,
        "copiadas": 2,
        "ignoradas": 0,
    }
    texto = f"{registro.alvo} {registro.detalhes}"
    assert CPF_A not in texto and "Maria" not in texto


def test_listagem_da_origem_para_escolher(
    cliente_de, usuario, empresa_a, empresa_b, origem_com_pessoas, vinculos_nas_duas
):
    api = _api(cliente_de, usuario, empresa_b)

    todas = api.get(COPIA, empresa=empresa_a.pk).json()
    filtradas = api.get(COPIA, empresa=empresa_a.pk, busca="john").json()

    assert [p["nome"] for p in todas] == ["John da Origem", "Maria da Origem"]
    assert set(todas[0]) == {"id", "tipo", "documento", "nome"}
    assert [p["nome"] for p in filtradas] == ["John da Origem"]
    assert api.get(COPIA, empresa=empresa_b.pk).status_code == 400  # a própria empresa
    assert CPF_B not in str(todas)
