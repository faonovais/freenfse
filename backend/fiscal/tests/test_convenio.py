"""Verificação do convênio do município via freedfe, com o transporte HTTP simulado (sem rede)."""

import datetime as dt
import logging

import pytest
from django_tenants.utils import schema_context

from conftest import CNPJ_A
from core.models import LogAuditoria
from core.permissoes import Perfil
from fiscal import gateway
from fiscal.models import Certificado, ParametrosFiscais
from fiscal.tests.apoio import (
    SENHA_DO_PFX,
    TransporteFalso,
    convenio_aderente,
    convenio_nao_aderente,
    falha_de_rede,
    gerar_pfx,
)

PARAMETROS = "/api/fiscal/parametros/"
VERIFICAR = "/api/fiscal/parametros/verificar-convenio/"
CERTIFICADO = "/api/fiscal/certificado/"
BALSAS = "2101400"
pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _municipios(municipios_basicos):
    """O município emissor é validado e nomeado pela tabela de municípios."""


@pytest.fixture
def transporte(monkeypatch):
    """`transporte(rotas)`: troca só o HTTP do gateway; o resto da freedfe roda de verdade."""
    original = gateway.verificar_convenio  # a de verdade, mesmo se instalar mais de uma vez

    def _instalar(rotas):
        falso = TransporteFalso(rotas)
        monkeypatch.setattr(
            gateway,
            "verificar_convenio",
            lambda **kw: original(**{**kw, "transporte": falso, "pausa": lambda segundos: None}),
        )
        return falso

    return _instalar


@pytest.fixture
def empresa_configurada(api_de, empresa_a):
    """Empresa A pronta para verificar: município emissor e certificado válido."""
    api = api_de(empresa_a)
    api.patch(PARAMETROS, {"codigo_municipio_emissor": BALSAS})
    resposta = api.post_arquivo(CERTIFICADO, gerar_pfx(CNPJ_A), nome="c.pfx", senha=SENHA_DO_PFX)
    assert resposta.status_code == 201, resposta.json()
    return api


def test_municipio_aderente_guarda_o_resultado_com_a_data(empresa_configurada, transporte):
    falso = transporte(
        {"/convenio": convenio_aderente(), f"/{CNPJ_A}": (200, {"retencoes": {"iss": "nao"}})}
    )

    resposta = empresa_configurada.post(VERIFICAR)

    assert resposta.status_code == 200, resposta.json()
    convenio = resposta.json()["convenio"]
    assert convenio["aderente"] is True
    assert "aderiu à NFS-e Nacional" in convenio["mensagem"] and "Balsas/MA" in convenio["mensagem"]
    assert "02/05/2024" in convenio["mensagem"]
    assert convenio["data_ativacao"] == "2024-05-02"
    assert convenio["contribuinte"] == {"retencoes": {"iss": "nao"}}
    assert convenio["atual"] is True and convenio["codigo_municipio"] == BALSAS
    assert dt.datetime.fromisoformat(convenio["verificado_em"]).date() == dt.date.today()
    # A consulta foi ao ambiente nacional de PRODUÇÃO RESTRITA (o padrão), pelo transporte falso.
    assert [
        (m, u.split("nfse.gov.br")[0], u.split("nfse.gov.br")[1]) for m, u in falso.chamadas
    ] == [
        ("GET", "https://adn.producaorestrita.", f"/parametrizacao/{BALSAS}/convenio"),
        ("GET", "https://adn.producaorestrita.", f"/parametrizacao/{BALSAS}/{CNPJ_A}"),
    ]


def test_resultado_fica_gravado_e_aparece_na_consulta_seguinte(empresa_configurada, transporte):
    transporte({"/convenio": convenio_aderente(), f"/{CNPJ_A}": (200, {})})
    empresa_configurada.post(VERIFICAR)

    convenio = empresa_configurada.get(PARAMETROS).json()["convenio"]

    assert convenio["aderente"] is True and convenio["verificado_em"]


def test_municipio_sem_convenio_avisa_que_as_notas_seriam_rejeitadas(
    empresa_configurada, transporte
):
    transporte({"/convenio": convenio_nao_aderente(), f"/{CNPJ_A}": (200, {})})

    convenio = empresa_configurada.post(VERIFICAR).json()["convenio"]

    assert convenio["aderente"] is False
    assert "NÃO tem convênio" in convenio["mensagem"] and "E0037" in convenio["mensagem"]


def test_resposta_ambigua_nao_afirma_nada(empresa_configurada, transporte):
    transporte({"/convenio": (200, {"parametrosConvenio": {}}), f"/{CNPJ_A}": (200, {})})

    convenio = empresa_configurada.post(VERIFICAR).json()["convenio"]

    assert convenio["aderente"] is None
    assert "não deixou claro" in convenio["mensagem"]


def test_municipio_fora_do_emissor_nacional_gera_aviso_na_resposta_bruta(
    empresa_configurada, transporte
):
    transporte(
        {
            "/convenio": (
                200,
                {
                    "parametrosConvenio": {
                        "aderenteAmbienteNacional": 1,
                        "aderenteEmissorNacional": 0,
                    }
                },
            ),
            f"/{CNPJ_A}": (200, {}),
        }
    )

    convenio = empresa_configurada.post(VERIFICAR).json()["convenio"]

    assert convenio["aderente"] is True and convenio["aderente_emissor_nacional"] is False


def test_falha_de_rede_da_mensagem_clara_e_nao_apaga_o_ultimo_resultado(
    empresa_configurada, transporte
):
    transporte({"/convenio": convenio_aderente(), f"/{CNPJ_A}": (200, {})})
    empresa_configurada.post(VERIFICAR)
    falho = transporte({"/convenio": falha_de_rede()})

    resposta = empresa_configurada.post(VERIFICAR)

    assert resposta.status_code == 502
    assert resposta.json()["codigo"] == "convenio_indisponivel"
    assert "sem internet" in resposta.json()["detalhe"]
    assert len(falho.chamadas) == 3  # tentativa inicial + 2 repetições (esperas simuladas)
    ultimo = empresa_configurada.get(PARAMETROS).json()["convenio"]
    assert ultimo["aderente"] is True  # o resultado anterior foi mantido


def test_recusa_do_ambiente_nacional_e_explicada(empresa_configurada, transporte):
    transporte(
        {
            "/convenio": (
                400,
                {"erros": [{"codigo": "E0001", "descricao": "Município inválido"}]},
            )
        }
    )

    resposta = empresa_configurada.post(VERIFICAR)

    assert resposta.status_code == 502
    assert "E0001" in resposta.json()["detalhe"]


def test_falha_nos_parametros_do_contribuinte_nao_impede_o_convenio(
    empresa_configurada, transporte
):
    transporte({"/convenio": convenio_aderente(), f"/{CNPJ_A}": falha_de_rede()})

    resposta = empresa_configurada.post(VERIFICAR)

    assert resposta.status_code == 200
    convenio = resposta.json()["convenio"]
    assert convenio["aderente"] is True and convenio["contribuinte"] == {}
    assert "retenções e benefícios" in convenio["avisos"][0]


def test_producao_consulta_o_host_de_producao(empresa_configurada, transporte):
    empresa_configurada.patch(PARAMETROS, {"ambiente": "producao", "confirmar_producao": True})
    falso = transporte({"/convenio": convenio_aderente(), f"/{CNPJ_A}": (200, {})})

    resposta = empresa_configurada.post(VERIFICAR)

    assert resposta.status_code == 200
    assert falso.chamadas[0][1].startswith("https://adn.nfse.gov.br/parametrizacao/")
    assert resposta.json()["convenio"]["ambiente"] == "producao"


def test_resultado_deixa_de_valer_se_o_municipio_ou_o_ambiente_mudam(
    empresa_configurada, transporte
):
    transporte({"/convenio": convenio_aderente(), f"/{CNPJ_A}": (200, {})})
    empresa_configurada.post(VERIFICAR)

    outro_municipio = empresa_configurada.patch(PARAMETROS, {"codigo_municipio_emissor": "1721000"})
    voltou = empresa_configurada.patch(PARAMETROS, {"codigo_municipio_emissor": BALSAS})
    outro_ambiente = empresa_configurada.patch(
        PARAMETROS, {"ambiente": "producao", "confirmar_producao": True}
    )

    assert outro_municipio.json()["convenio"]["atual"] is False
    assert voltou.json()["convenio"]["atual"] is True
    assert outro_ambiente.json()["convenio"]["atual"] is False


def test_sem_municipio_emissor_pede_para_informar(api_de, empresa_a):
    api = api_de(empresa_a)
    api.post_arquivo(CERTIFICADO, gerar_pfx(CNPJ_A), nome="c.pfx", senha=SENHA_DO_PFX)

    resposta = api.post(VERIFICAR)

    assert resposta.status_code == 400
    assert resposta.json()["codigo"] == "convenio_nao_verificado"
    assert "município emissor" in resposta.json()["detalhe"]


def test_sem_certificado_pede_para_enviar(api_de, empresa_a):
    api = api_de(empresa_a)
    api.patch(PARAMETROS, {"codigo_municipio_emissor": BALSAS})

    resposta = api.post(VERIFICAR)

    assert resposta.status_code == 400
    assert "certificado A1" in resposta.json()["detalhe"]


def test_certificado_vencido_no_banco_impede_a_verificacao(empresa_configurada, empresa_a):
    with schema_context(empresa_a.schema_name):
        Certificado.objects.update(valido_ate=dt.datetime.now(dt.UTC) - dt.timedelta(days=1))

    resposta = empresa_configurada.post(VERIFICAR)

    assert resposta.status_code == 400
    assert "vencido" in resposta.json()["detalhe"]


def test_verificacao_e_auditada(empresa_configurada, transporte, usuario, empresa_a):
    transporte({"/convenio": convenio_aderente(), f"/{CNPJ_A}": (200, {})})

    empresa_configurada.post(VERIFICAR)

    registro = LogAuditoria.objects.get(acao=LogAuditoria.Acao.CONVENIO_VERIFICADO)
    assert registro.usuario == usuario and registro.empresa == empresa_a
    assert registro.alvo == f"municipio:{BALSAS}"
    assert registro.detalhes == {"aderente": True, "ambiente": "producao_restrita"}


def test_senha_e_certificado_nao_vazam_na_verificacao(empresa_configurada, transporte, caplog):
    transporte({"/convenio": convenio_aderente(), f"/{CNPJ_A}": (200, {})})
    caplog.set_level(logging.DEBUG)

    resposta = empresa_configurada.post(VERIFICAR)

    assert SENHA_DO_PFX not in resposta.content.decode()
    assert SENHA_DO_PFX not in caplog.text


@pytest.mark.parametrize("perfil", [Perfil.CONSULTA, Perfil.FINANCEIRO, Perfil.EMISSOR])
def test_so_quem_edita_a_configuracao_verifica(api_de, empresa_a, perfil, transporte):
    falso = transporte({"/convenio": convenio_aderente()})

    resposta = api_de(empresa_a, perfil).post(VERIFICAR)

    assert resposta.status_code == 403
    assert falso.chamadas == []


def test_verificacao_da_empresa_a_nao_aparece_na_b(
    empresa_configurada, api_do_master, empresa_b, transporte
):
    transporte({"/convenio": convenio_aderente(), f"/{CNPJ_A}": (200, {})})
    empresa_configurada.post(VERIFICAR)

    assert api_do_master(empresa_b).get(PARAMETROS).json()["convenio"] is None
    with schema_context(empresa_b.schema_name):
        assert ParametrosFiscais.obter().convenio_verificado_em is None
