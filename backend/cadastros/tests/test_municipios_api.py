"""Busca de municípios para os campos de endereço (dado público, qualquer vinculado)."""

import pytest

from core.permissoes import Perfil

URL = "/api/cadastros/municipios/"
pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _municipios(municipios_basicos):
    """Municípios reais de teste no schema público."""


def test_busca_por_nome_ignora_acento_e_caixa(api_de, empresa_a):
    api = api_de(empresa_a)

    assert [m["nome"] for m in api.get(URL, busca="SAO pau").json()] == ["São Paulo"]
    assert [m["codigo"] for m in api.get(URL, busca="  balsas ").json()] == ["2101400"]


def test_busca_filtra_por_uf(api_de, empresa_a):
    api = api_de(empresa_a)

    assert api.get(URL, busca="a", uf="MA").json() == [
        {"codigo": "2101400", "nome": "Balsas", "uf": "MA"}
    ]
    assert api.get(URL, busca="balsas", uf="SP").json() == []


def test_consulta_por_codigo_devolve_um_municipio(api_de, empresa_a):
    api = api_de(empresa_a)

    assert api.get(URL, codigo="1721000").json() == [
        {"codigo": "1721000", "nome": "Palmas", "uf": "TO"}
    ]
    assert api.get(URL, codigo="9999999").json() == []


def test_sem_criterio_nao_lista_tudo(api_de, empresa_a):
    assert api_de(empresa_a).get(URL).json() == []


def test_resultado_e_limitado_a_20(api_de, empresa_a):
    from core.models import Municipio

    Municipio.objects.bulk_create(
        [
            Municipio(
                codigo=f"31{i:05d}", nome=f"Vila Teste {i}", uf="MG", nome_busca=f"vila teste {i}"
            )
            for i in range(30)
        ]
    )

    assert len(api_de(empresa_a).get(URL, busca="vila teste").json()) == 20


@pytest.mark.parametrize("perfil", [Perfil.CONSULTA, Perfil.FINANCEIRO, Perfil.EMISSOR])
def test_qualquer_vinculado_pode_buscar(api_de, empresa_a, perfil):
    assert api_de(empresa_a, perfil).get(URL, busca="palmas").status_code == 200


def test_sem_vinculo_nao_busca(cliente_de, usuario, empresa_a):
    resposta = cliente_de(usuario).get(URL, {"busca": "palmas"}, HTTP_X_EMPRESA=str(empresa_a.pk))

    assert resposta.status_code == 403
