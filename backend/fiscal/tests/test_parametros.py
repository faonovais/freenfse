"""Parâmetros fiscais: validação, ambiente (produção exige confirmação) e permissões."""

import pytest
from django.db import IntegrityError
from django_tenants.utils import schema_context

from core.models import LogAuditoria
from core.permissoes import Perfil
from fiscal.models import ParametrosFiscais

URL = "/api/fiscal/parametros/"
pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _municipios(municipios_basicos):
    """A validação do município emissor consulta a tabela de municípios."""


def test_primeira_consulta_traz_os_padroes_com_producao_restrita(api_de, empresa_a):
    corpo = api_de(empresa_a).get(URL).json()

    assert corpo["ambiente"] == "producao_restrita"
    assert corpo["serie_dps"] == 1
    assert corpo["regime_especial"] == 0
    assert corpo["convenio"] is None
    assert corpo["codigo_municipio_emissor"] == ""


def test_resposta_traz_as_opcoes_para_montar_a_tela(api_de, empresa_a):
    opcoes = api_de(empresa_a).get(URL).json()["opcoes"]

    assert {o["valor"] for o in opcoes["ambiente"]} == {"producao_restrita", "producao"}
    assert {o["valor"] for o in opcoes["regime_tributario"]} >= {"mei", "simples_nacional"}
    assert {o["valor"] for o in opcoes["regime_apuracao_simples"]} == {1, 2, 3}
    assert 0 in {o["valor"] for o in opcoes["regime_especial"]}


def test_configuracao_completa_e_derivacao_da_opcao_pelo_simples(api_de, empresa_a):
    api = api_de(empresa_a)

    resposta = api.patch(
        URL,
        {
            "regime_tributario": "simples_nacional",
            "regime_apuracao_simples": 1,
            "regime_especial": 0,
            "serie_dps": 7,
            "codigo_municipio_emissor": "2101400",
        },
    )

    assert resposta.status_code == 200, resposta.json()
    corpo = resposta.json()
    assert corpo["opcao_simples"] == 3
    assert corpo["serie_dps"] == 7
    assert corpo["municipio_emissor"] == "Balsas/MA"
    mei = api.patch(URL, {"regime_tributario": "mei", "regime_apuracao_simples": None}).json()
    presumido = api.patch(URL, {"regime_tributario": "lucro_presumido"}).json()
    assert (mei["opcao_simples"], presumido["opcao_simples"]) == (2, 1)


@pytest.mark.parametrize(
    ("dados", "campo"),
    [
        ({"regime_tributario": "simples_nacional"}, "regime_apuracao_simples"),
        (
            {"regime_tributario": "lucro_real", "regime_apuracao_simples": 2},
            "regime_apuracao_simples",
        ),
        ({"serie_dps": 0}, "serie_dps"),
        ({"serie_dps": 100000}, "serie_dps"),
        ({"serie_dps": "abc"}, "serie_dps"),
        ({"codigo_municipio_emissor": "9999999"}, "codigo_municipio_emissor"),
        ({"codigo_municipio_emissor": "123"}, "codigo_municipio_emissor"),
        ({"regime_especial": 7}, "regime_especial"),
        ({"regime_tributario": "mei", "regime_apuracao_simples": 9}, "regime_apuracao_simples"),
        ({"ambiente": "homologacao"}, "ambiente"),
    ],
)
def test_parametros_invalidos_sao_recusados(api_de, empresa_a, dados, campo):
    resposta = api_de(empresa_a).patch(URL, dados)

    assert resposta.status_code == 400
    assert campo in resposta.json()


def test_recusa_nao_altera_o_que_estava_gravado(api_de, empresa_a):
    api = api_de(empresa_a)
    api.patch(URL, {"serie_dps": 5})

    api.patch(URL, {"serie_dps": 6, "codigo_municipio_emissor": "9999999"})

    assert api.get(URL).json()["serie_dps"] == 5


def test_trocar_para_producao_exige_confirmacao(api_de, empresa_a):
    api = api_de(empresa_a)

    sem_confirmar = api.patch(URL, {"ambiente": "producao"})
    confirmado_falso = api.patch(URL, {"ambiente": "producao", "confirmar_producao": False})

    for resposta in (sem_confirmar, confirmado_falso):
        assert resposta.status_code == 400
        assert resposta.json()["codigo"] == "confirmacao_necessaria"
    assert api.get(URL).json()["ambiente"] == "producao_restrita"
    assert not LogAuditoria.objects.filter(acao=LogAuditoria.Acao.AMBIENTE_ALTERADO).exists()


def test_troca_confirmada_para_producao_e_auditada(api_de, empresa_a, usuario):
    api = api_de(empresa_a)

    resposta = api.patch(URL, {"ambiente": "producao", "confirmar_producao": True})

    assert resposta.status_code == 200 and resposta.json()["ambiente"] == "producao"
    registro = LogAuditoria.objects.get(acao=LogAuditoria.Acao.AMBIENTE_ALTERADO)
    assert registro.usuario == usuario and registro.empresa == empresa_a
    assert registro.detalhes == {"de": "producao_restrita", "para": "producao"}


def test_voltar_para_producao_restrita_nao_pede_confirmacao_e_e_auditado(api_de, empresa_a):
    api = api_de(empresa_a)
    api.patch(URL, {"ambiente": "producao", "confirmar_producao": True})

    resposta = api.patch(URL, {"ambiente": "producao_restrita"})

    assert resposta.status_code == 200
    assert LogAuditoria.objects.filter(acao=LogAuditoria.Acao.AMBIENTE_ALTERADO).count() == 2


def test_confirmar_producao_sem_trocar_de_ambiente_nao_audita_troca(api_de, empresa_a):
    api = api_de(empresa_a)

    api.patch(URL, {"serie_dps": 3, "confirmar_producao": True})

    assert not LogAuditoria.objects.filter(acao=LogAuditoria.Acao.AMBIENTE_ALTERADO).exists()
    registro = LogAuditoria.objects.get(acao=LogAuditoria.Acao.PARAMETROS_ALTERADOS)
    assert registro.detalhes == {"alterados": {"serie_dps": {"de": 1, "para": 3}}}


def test_alterar_sem_mudar_nada_nao_gera_auditoria(api_de, empresa_a):
    api = api_de(empresa_a)

    api.patch(URL, {"serie_dps": 1})

    assert not LogAuditoria.objects.filter(acao=LogAuditoria.Acao.PARAMETROS_ALTERADOS).exists()


def test_producao_exige_config_editar_mesmo_para_administrador(api_de, empresa_a):
    api = api_de(empresa_a, Perfil.ADMINISTRADOR, permissoes_removidas=["config.editar"])

    resposta = api.patch(URL, {"ambiente": "producao", "confirmar_producao": True})

    assert resposta.status_code == 403
    assert api.get(URL).json()["ambiente"] == "producao_restrita"


@pytest.mark.parametrize("perfil", [Perfil.CONSULTA, Perfil.FINANCEIRO])
def test_quem_so_consulta_le_mas_nao_altera(api_de, empresa_a, perfil):
    api = api_de(empresa_a, perfil)

    assert api.get(URL).status_code == 200
    assert api.patch(URL, {"serie_dps": 2}).status_code == 403
    assert api.patch(URL, {"ambiente": "producao", "confirmar_producao": True}).status_code == 403


def test_emissor_nao_acessa_a_configuracao(api_de, empresa_a):
    api = api_de(empresa_a, Perfil.EMISSOR)

    assert api.get(URL).status_code == 403
    assert api.patch(URL, {"serie_dps": 2}).status_code == 403


def test_parametros_sao_por_empresa(api_do_master, empresa_a, empresa_b):
    api_a, api_b = api_do_master(empresa_a), api_do_master(empresa_b)
    api_a.patch(URL, {"serie_dps": 9, "ambiente": "producao", "confirmar_producao": True})

    assert api_b.get(URL).json()["serie_dps"] == 1
    assert api_b.get(URL).json()["ambiente"] == "producao_restrita"
    assert api_a.get(URL).json()["serie_dps"] == 9


def test_so_existe_uma_linha_de_parametros_por_empresa(empresa_a):
    with schema_context(empresa_a.schema_name):
        ParametrosFiscais.obter()
        ParametrosFiscais(serie_dps=2).save()  # save() fixa a mesma linha

        assert ParametrosFiscais.objects.count() == 1
        with pytest.raises(IntegrityError):
            ParametrosFiscais.objects.bulk_create([ParametrosFiscais(pk=2)])
