"""Pessoas: validação de documento, estrangeiro/NIF, endereço com IBGE, e-mails e permissões."""

import pytest
from django_tenants.utils import schema_context

from cadastros.models import PerfilPessoa, Pessoa
from cadastros.tests.conftest import pessoa_estrangeira, pessoa_pf, pessoa_pj
from conftest import CNPJ_A, CPF_A
from core.permissoes import Perfil

URL = "/api/cadastros/pessoas/"
pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _municipios(municipios_basicos):
    """Todos os testes de pessoas precisam da tabela de municípios."""


# --- Documento ------------------------------------------------------------------------


@pytest.mark.parametrize("documento", ["52998224724", "11111111111", "123", "abc"])
def test_cpf_invalido_e_recusado(api_de, empresa_a, documento):
    resposta = api_de(empresa_a).post(URL, pessoa_pf(documento=documento))

    assert resposta.status_code == 400
    assert "CPF inválido" in resposta.json()["documento"][0]


@pytest.mark.parametrize("documento", ["11222333000180", "00000000000000", "123", "ABCDEFGHIJKL00"])
def test_cnpj_invalido_e_recusado(api_de, empresa_a, documento):
    resposta = api_de(empresa_a).post(URL, pessoa_pj(documento=documento))

    assert resposta.status_code == 400
    assert "CNPJ inválido" in resposta.json()["documento"][0]


def test_documento_valido_com_pontuacao_e_gravado_normalizado(api_de, empresa_a):
    api = api_de(empresa_a)

    pf = api.post(URL, pessoa_pf(documento="529.982.247-25"))
    pj = api.post(
        URL,
        pessoa_pj(
            documento=CNPJ_A[:2]
            + "."
            + CNPJ_A[2:5]
            + "."
            + CNPJ_A[5:8]
            + "/"
            + CNPJ_A[8:12]
            + "-"
            + CNPJ_A[12:]
        ),
    )

    assert pf.status_code == 201, pf.json()
    assert pf.json()["documento"] == CPF_A
    assert pf.json()["documento_formatado"] == "529.982.247-25"
    assert pj.status_code == 201, pj.json()
    assert pj.json()["documento"] == CNPJ_A
    assert pj.json()["documento_formatado"] == "11.222.333/0001-81"


def test_cnpj_alfanumerico_e_aceito(api_de, empresa_a):
    from conftest import cnpj_de_teste

    resposta = api_de(empresa_a).post(URL, pessoa_pj(documento=cnpj_de_teste("A1B2C3D4E5F6")))

    assert resposta.status_code == 201, resposta.json()


def test_documento_repetido_na_mesma_empresa_e_recusado(api_de, empresa_a):
    api = api_de(empresa_a)
    assert api.post(URL, pessoa_pf()).status_code == 201

    repetido = api.post(URL, pessoa_pf(nome="Outro Nome"))

    assert repetido.status_code == 400
    assert "Já existe uma pessoa" in repetido.json()["documento"][0]


# --- Estrangeiro e NIF ---------------------------------------------------------------


def test_estrangeiro_sem_documento_nacional_e_aceito_com_nif(api_de, empresa_a):
    resposta = api_de(empresa_a).post(URL, pessoa_estrangeira())

    assert resposta.status_code == 201, resposta.json()
    assert resposta.json()["documento"] == ""
    assert resposta.json()["nif"] == "AB1234567"


def test_estrangeiro_aceita_motivo_no_lugar_do_nif(api_de, empresa_a):
    resposta = api_de(empresa_a).post(URL, pessoa_estrangeira(nif="", motivo_sem_nif=1))

    assert resposta.status_code == 201, resposta.json()


@pytest.mark.parametrize(
    ("ajuste", "campo"),
    [
        ({"nif": "", "motivo_sem_nif": None}, "nif"),  # nem NIF nem motivo
        ({"motivo_sem_nif": 2}, "motivo_sem_nif"),  # os dois
        ({"documento": CPF_A}, "documento"),  # estrangeiro com CPF
    ],
)
def test_estrangeiro_invalido_e_recusado(api_de, empresa_a, ajuste, campo):
    resposta = api_de(empresa_a).post(URL, pessoa_estrangeira(**ajuste))

    assert resposta.status_code == 400
    assert campo in resposta.json()


def test_nif_nao_vale_para_pessoa_nacional(api_de, empresa_a):
    resposta = api_de(empresa_a).post(URL, pessoa_pf(nif="AB1234567"))

    assert resposta.status_code == 400
    assert "só para estrangeiros" in resposta.json()["nif"][0]


def test_estrangeiro_com_endereco_no_exterior_exige_o_conjunto_completo(api_de, empresa_a):
    api = api_de(empresa_a)
    incompleto = api.post(URL, pessoa_estrangeira(pais="US", cidade="Austin"))
    completo = api.post(
        URL,
        pessoa_estrangeira(
            nif="ZZ99",
            pais="us",
            cidade="Austin",
            estado="Texas",
            codigo_postal="78701",
            logradouro="Congress Ave",
            numero="1",
            bairro="Downtown",
        ),
    )

    assert incompleto.status_code == 400
    assert {"codigo_postal", "estado", "logradouro"} <= set(incompleto.json())
    assert completo.status_code == 201, completo.json()
    assert completo.json()["pais"] == "US"


# --- Endereço com IBGE ----------------------------------------------------------------


@pytest.mark.parametrize("fabrica", [pessoa_pf, pessoa_pj])
def test_endereco_sem_ibge_e_recusado_para_pessoa_nacional(api_de, empresa_a, fabrica):
    dados = fabrica(codigo_municipio="")
    dados["documento"] = dados["documento"] if fabrica is pessoa_pf else CNPJ_A

    resposta = api_de(empresa_a).post(URL, dados)

    assert resposta.status_code == 400
    assert "código IBGE" in resposta.json()["codigo_municipio"][0]


def test_pessoa_nacional_sem_endereco_nenhum_tambem_e_recusada(api_de, empresa_a):
    resposta = api_de(empresa_a).post(
        URL, {"tipo": "pf", "documento": CPF_A, "nome": "Sem Endereço"}
    )

    assert resposta.status_code == 400
    assert {"logradouro", "numero", "bairro", "cep", "codigo_municipio"} <= set(resposta.json())


def test_ibge_inexistente_e_recusado(api_de, empresa_a):
    resposta = api_de(empresa_a).post(URL, pessoa_pf(codigo_municipio="9999999"))

    assert resposta.status_code == 400
    assert "não encontrado" in resposta.json()["codigo_municipio"][0]


def test_cep_precisa_de_8_digitos(api_de, empresa_a):
    resposta = api_de(empresa_a).post(URL, pessoa_pf(cep="7700"))

    assert resposta.status_code == 400
    assert "cep" in resposta.json()


def test_resposta_traz_o_nome_do_municipio(api_de, empresa_a):
    resposta = api_de(empresa_a).post(URL, pessoa_pf(cep="77.001-000"))

    assert resposta.json()["municipio_nome"] == "Palmas/TO"
    assert resposta.json()["cep"] == "77001000"


# --- E-mails de envio, perfis e telefone ------------------------------------------------


def test_emails_de_envio_sao_normalizados_e_sem_repeticao(api_de, empresa_a):
    resposta = api_de(empresa_a).post(
        URL,
        pessoa_pf(emails_envio=[" Fiscal@Exemplo.TEST ", "fiscal@exemplo.test", "b@exemplo.test"]),
    )

    assert resposta.json()["emails_envio"] == ["fiscal@exemplo.test", "b@exemplo.test"]


@pytest.mark.parametrize("emails", [["sem-arroba"], ["a@b"], ["x@" + "d" * 80 + ".test"]])
def test_email_invalido_e_recusado(api_de, empresa_a, emails):
    resposta = api_de(empresa_a).post(URL, pessoa_pf(emails_envio=emails))

    assert resposta.status_code == 400
    assert "emails_envio" in resposta.json()


def test_limite_de_emails(api_de, empresa_a):
    muitos = [f"p{i}@exemplo.test" for i in range(11)]

    resposta = api_de(empresa_a).post(URL, pessoa_pf(emails_envio=muitos))

    assert resposta.status_code == 400


def test_pessoa_pode_ter_varios_perfis(api_de, empresa_a):
    api = api_de(empresa_a)

    resposta = api.post(URL, pessoa_pf(perfis=["cliente", "fornecedor"]))

    assert resposta.status_code == 201, resposta.json()
    assert sorted(resposta.json()["perfis"]) == ["cliente", "fornecedor"]
    assert api.get(URL, perfil="fornecedor").json()["count"] == 1
    assert api.get(URL, perfil="intermediario").json()["count"] == 0


def test_perfil_inexistente_e_recusado(api_de, empresa_a):
    resposta = api_de(empresa_a).post(URL, pessoa_pf(perfis=["nao-existe"]))

    assert resposta.status_code == 400


def test_perfis_padrao_existem_em_cada_empresa_e_podem_ser_estendidos(api_de, empresa_a):
    api = api_de(empresa_a)
    assert {p["codigo"] for p in api.get("/api/cadastros/perfis/").json()} == {
        "cliente",
        "fornecedor",
        "intermediario",
    }

    criado = api.post(
        "/api/cadastros/perfis/", {"codigo": "transportadora", "nome": "Transportadora"}
    )

    assert criado.status_code == 201
    assert criado.json()["sistema"] is False
    assert api.post(URL, pessoa_pf(perfis=["transportadora"])).status_code == 201


def test_telefone_so_digitos(api_de, empresa_a):
    api = api_de(empresa_a)
    ok = api.post(URL, pessoa_pf(telefone="(63) 99999-0000"))
    ruim = api.post(URL, pessoa_pj(telefone="123"))

    assert ok.json()["telefone"] == "63999990000"
    assert ruim.status_code == 400


# --- Alteração, busca, desativação e permissões -----------------------------------------


def test_alterar_e_desativar_sem_perder_a_validacao(api_de, empresa_a):
    api = api_de(empresa_a)
    pessoa = api.post(URL, pessoa_pf()).json()

    desativada = api.patch(f"{URL}{pessoa['id']}/", {"ativo": False})
    invalida = api.patch(f"{URL}{pessoa['id']}/", {"documento": "123"})

    assert desativada.status_code == 200 and desativada.json()["ativo"] is False
    assert invalida.status_code == 400
    assert api.get(URL, ativo="false").json()["count"] == 1
    assert api.get(URL, ativo="true").json()["count"] == 0


def test_nao_existe_exclusao(api_de, empresa_a):
    api = api_de(empresa_a)
    pessoa = api.post(URL, pessoa_pf()).json()

    resposta = api.cliente.delete(f"{URL}{pessoa['id']}/", HTTP_X_EMPRESA=str(empresa_a.pk))

    assert resposta.status_code in (403, 405)  # sem rota de exclusão (e sem permissão declarada)
    assert api.get(f"{URL}{pessoa['id']}/").status_code == 200


def test_busca_por_nome_e_por_documento(api_de, empresa_a):
    api = api_de(empresa_a)
    api.post(URL, pessoa_pf(nome="Fazenda Boa Vista"))
    api.post(URL, pessoa_pj(nome="Armazéns Cerrado"))

    assert api.get(URL, busca="boa vista").json()["count"] == 1
    assert api.get(URL, busca="529.982").json()["count"] == 1
    assert api.get(URL, busca="zzz").json()["count"] == 0
    assert api.get(URL, tipo="pj").json()["count"] == 1


def test_perfil_consulta_le_mas_nao_cadastra(api_de, empresa_a, criar_pessoa):
    criar_pessoa(empresa_a)
    api = api_de(empresa_a, Perfil.CONSULTA)

    assert api.get(URL).status_code == 200
    assert api.post(URL, pessoa_pf(documento="11144477735")).status_code == 403


def test_emissor_pode_cadastrar_e_a_permissao_removida_bloqueia(api_de, empresa_a):
    api = api_de(empresa_a, Perfil.EMISSOR, permissoes_removidas=["cadastro.editar"])

    assert api.get(URL).status_code == 200
    assert api.post(URL, pessoa_pf()).status_code == 403


def test_sem_vinculo_nao_acessa(cliente_de, usuario, empresa_a):
    cliente = cliente_de(usuario)

    resposta = cliente.get(URL, HTTP_X_EMPRESA=str(empresa_a.pk))

    assert resposta.status_code == 403


# --- Isolamento entre empresas --------------------------------------------------------


def test_pessoas_da_empresa_a_nunca_aparecem_na_b(api_do_master, empresa_a, empresa_b):
    api_a, api_b = api_do_master(empresa_a), api_do_master(empresa_b)
    pessoa_a = api_a.post(URL, pessoa_pf(nome="Só da Alfa")).json()

    assert api_b.get(URL).json()["count"] == 0
    assert api_b.get(f"{URL}{pessoa_a['id']}/").status_code == 404
    # O mesmo CPF pode ser cadastrado na outra empresa: cadastros são independentes (D4).
    assert api_b.post(URL, pessoa_pf(nome="Da Beta")).status_code == 201
    assert [p["nome"] for p in api_a.get(URL).json()["results"]] == ["Só da Alfa"]
    with schema_context(empresa_a.schema_name):
        assert Pessoa.objects.count() == 1
    with schema_context(empresa_b.schema_name):
        assert Pessoa.objects.count() == 1
        assert PerfilPessoa.objects.count() == 3
