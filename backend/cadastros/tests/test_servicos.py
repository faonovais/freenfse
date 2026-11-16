"""Serviços: validação fiscal, vigência sem sobreposição e consulta da versão vigente."""

import pytest
from django_tenants.utils import schema_context

from cadastros.models import Servico
from cadastros.tests.conftest import garantir_servico_oficial, servico_json
from core.models import ServicoOficial
from core.permissoes import Perfil

URL = "/api/cadastros/servicos/"
pytestmark = pytest.mark.django_db


def _vigente(api, data, nacional="170101", municipal=""):
    return api.get(
        f"{URL}vigente/", codigo_nacional=nacional, codigo_municipal=municipal, data=data
    )


def test_cria_servico_com_a_classificacao_tributaria(api_de, empresa_a):
    resposta = api_de(empresa_a).post(
        URL,
        servico_json(
            codigo_tributacao_municipal="001",
            nbs="1.0608.40.00",
            cst_ibs_cbs="000",
            c_class_trib="000001",
            iss_retido=True,
            retencao_irrf="1.50",
            retencao_inss="11.00",
        ),
    )

    assert resposta.status_code == 201, resposta.json()
    corpo = resposta.json()
    assert (corpo["nbs"], corpo["cst_ibs_cbs"], corpo["c_class_trib"]) == (
        "106084000",
        "000",
        "000001",
    )
    assert corpo["servico_oficial_id"] > 0
    assert corpo["servico_oficial_detalhes"]["nbs"] == "106084000"
    assert corpo["iss_retido"] is True and corpo["retencao_irrf"] == "1.50"


@pytest.mark.parametrize(
    ("ajuste", "campo"),
    [
        ({"codigo_tributacao_nacional": "1701"}, "codigo_tributacao_nacional"),
        ({"codigo_tributacao_municipal": "000"}, "codigo_tributacao_municipal"),
        ({"codigo_tributacao_municipal": "12"}, "codigo_tributacao_municipal"),
        ({"nbs": "123"}, "nbs"),
        ({"cst_ibs_cbs": "200"}, "cst_ibs_cbs"),  # diverge do serviço oficial
        ({"c_class_trib": "410001"}, "c_class_trib"),  # diverge do serviço oficial
        ({"codigo_indicador_operacao": "050101"}, "codigo_indicador_operacao"),
        ({"aliquota_iss": "5.01"}, "aliquota_iss"),
        ({"aliquota_iss": "-1"}, "aliquota_iss"),
        ({"retencao_pis": "100.01"}, "retencao_pis"),
        ({"vigencia_fim": "2025-12-31"}, "vigencia_fim"),
        ({"descricao": " "}, "descricao"),
        ({"nome": ""}, "nome"),
    ],
)
def test_servico_invalido_e_recusado(api_de, empresa_a, ajuste, campo):
    resposta = api_de(empresa_a).post(URL, servico_json(**ajuste))

    assert resposta.status_code == 400
    assert campo in resposta.json()


def test_sobreposicao_de_vigencia_e_recusada(api_de, empresa_a):
    api = api_de(empresa_a)
    assert (
        api.post(
            URL, servico_json(vigencia_inicio="2026-01-01", vigencia_fim="2026-06-30")
        ).status_code
        == 201
    )

    dentro = api.post(URL, servico_json(vigencia_inicio="2026-03-01", vigencia_fim="2026-04-30"))
    comeca_antes = api.post(
        URL, servico_json(vigencia_inicio="2025-06-01", vigencia_fim="2026-01-01")
    )
    aberta = api.post(URL, servico_json(vigencia_inicio="2026-06-30"))

    for resposta in (dentro, comeca_antes, aberta):
        assert resposta.status_code == 400
        assert "se sobrepõe" in resposta.json()["vigencia_inicio"][0]


def test_versoes_consecutivas_sem_sobreposicao_sao_aceitas(api_de, empresa_a):
    api = api_de(empresa_a)

    primeira = api.post(URL, servico_json(vigencia_inicio="2026-01-01", vigencia_fim="2026-06-30"))
    segunda = api.post(URL, servico_json(vigencia_inicio="2026-07-01", aliquota_iss="2.00"))
    antes = api.post(URL, servico_json(vigencia_inicio="2025-01-01", vigencia_fim="2025-12-31"))

    assert [r.status_code for r in (primeira, segunda, antes)] == [201, 201, 201]


def test_sobreposicao_so_vale_para_o_mesmo_servico(api_de, empresa_a):
    api = api_de(empresa_a)
    api.post(URL, servico_json())

    outro_codigo = api.post(URL, servico_json(codigo_tributacao_nacional="171901"))
    outro_municipal = api.post(URL, servico_json(codigo_tributacao_municipal="005"))

    assert outro_codigo.status_code == 201
    assert outro_municipal.status_code == 201


def test_versao_inativa_nao_bloqueia_a_vigencia(api_de, empresa_a):
    api = api_de(empresa_a)
    antiga = api.post(URL, servico_json()).json()
    assert api.patch(f"{URL}{antiga['id']}/", {"ativo": False}).status_code == 200

    nova = api.post(URL, servico_json(aliquota_iss="2.50"))

    assert nova.status_code == 201
    # Reativar a antiga agora sobreporia a nova.
    reativada = api.patch(f"{URL}{antiga['id']}/", {"ativo": True})
    assert reativada.status_code == 400


def test_alterar_a_vigencia_tambem_respeita_a_sobreposicao(api_de, empresa_a):
    api = api_de(empresa_a)
    v1 = api.post(URL, servico_json(vigencia_inicio="2026-01-01", vigencia_fim="2026-06-30")).json()
    v2 = api.post(URL, servico_json(vigencia_inicio="2026-07-01")).json()

    invade = api.patch(f"{URL}{v1['id']}/", {"vigencia_fim": "2026-07-15"})
    corrige_a_si_mesma = api.patch(f"{URL}{v1['id']}/", {"vigencia_fim": "2026-06-15"})

    assert invade.status_code == 400
    assert corrige_a_si_mesma.status_code == 200
    assert v2["id"] != v1["id"]


def test_consulta_da_versao_vigente_numa_data(api_de, empresa_a):
    api = api_de(empresa_a)
    api.post(
        URL,
        servico_json(vigencia_inicio="2026-01-01", vigencia_fim="2026-06-30", aliquota_iss="3.00"),
    )
    api.post(URL, servico_json(vigencia_inicio="2026-07-01", aliquota_iss="2.00"))

    na_primeira = _vigente(api, "2026-06-30")
    na_segunda = _vigente(api, "2026-07-01")
    muito_depois = _vigente(api, "2030-01-01")
    antes_de_tudo = _vigente(api, "2025-12-31")

    assert na_primeira.status_code == 200 and na_primeira.json()["aliquota_iss"] == "3.00"
    assert na_segunda.json()["aliquota_iss"] == "2.00"
    assert muito_depois.json()["aliquota_iss"] == "2.00"
    assert antes_de_tudo.status_code == 404
    assert "31/12/2025" in antes_de_tudo.json()["detalhe"]


def test_consulta_vigente_distingue_o_codigo_municipal_e_ignora_inativas(api_de, empresa_a):
    api = api_de(empresa_a)
    api.post(URL, servico_json(codigo_tributacao_municipal="001", aliquota_iss="4.00"))
    inativa = api.post(URL, servico_json(codigo_tributacao_municipal="002", ativo=False)).json()

    assert _vigente(api, "2026-05-01", municipal="001").json()["aliquota_iss"] == "4.00"
    assert _vigente(api, "2026-05-01", municipal="").status_code == 404
    assert _vigente(api, "2026-05-01", municipal="002").status_code == 404
    assert inativa["ativo"] is False


def test_lista_filtra_por_data_de_vigencia(api_de, empresa_a):
    api = api_de(empresa_a)
    api.post(URL, servico_json(vigencia_inicio="2026-01-01", vigencia_fim="2026-06-30"))
    api.post(URL, servico_json(vigencia_inicio="2026-07-01"))

    assert len(api.get(URL, vigente_em="2026-03-01").json()) == 1
    assert len(api.get(URL).json()) == 2
    assert api.get(URL, vigente_em="ontem").status_code == 400


@pytest.mark.parametrize(
    ("agora_fixo", "aliquota"),
    [
        # 23:30 de 31/10 em Brasília já é 01/11 em UTC: o "hoje" do usuário ainda é 31/10.
        ("2026-11-01T02:30:00Z", "3.00"),
        ("2026-11-01T03:00:00Z", "2.00"),  # meia-noite em Brasília: virou o dia
    ],
    indirect=["agora_fixo"],
)
def test_vigente_sem_data_usa_o_dia_de_hoje_em_brasilia(agora_fixo, api_de, empresa_a, aliquota):
    api = api_de(empresa_a)
    api.post(URL, servico_json(vigencia_inicio="2026-01-01", vigencia_fim="2026-10-31"))
    api.post(URL, servico_json(vigencia_inicio="2026-11-01", aliquota_iss="2.00"))

    resposta = api.get(f"{URL}vigente/", codigo_nacional="170101", codigo_municipal="")

    assert resposta.json()["aliquota_iss"] == aliquota


def test_consulta_vigente_exige_codigo_e_data_validos(api_de, empresa_a):
    api = api_de(empresa_a)

    assert api.get(f"{URL}vigente/", data="2026-01-01").status_code == 400
    assert _vigente(api, "01/01/2026").status_code == 400


def test_permissoes_do_servico(api_de, empresa_a):
    consulta = api_de(empresa_a, Perfil.CONSULTA)

    assert consulta.get(URL).status_code == 200
    assert consulta.post(URL, servico_json()).status_code == 403


def test_servicos_da_empresa_a_nao_aparecem_na_b(api_do_master, empresa_a, empresa_b):
    api_a, api_b = api_do_master(empresa_a), api_do_master(empresa_b)
    api_a.post(URL, servico_json())

    assert api_b.get(URL).json() == []
    assert _vigente(api_b, "2026-05-01").status_code == 404
    # A mesma versão pode existir na outra empresa: a vigência é por empresa.
    assert api_b.post(URL, servico_json()).status_code == 201
    with schema_context(empresa_a.schema_name):
        assert Servico.objects.count() == 1


def test_gravacao_usa_lock_por_servico(api_de, empresa_a, monkeypatch):
    """A checagem de sobreposição roda sob advisory lock (corrida de duas gravações)."""
    from django.db import connection

    comandos = []
    original = connection.cursor

    def espiar():
        cursor = original()
        executar = cursor.execute

        def execute(sql, params=None):
            comandos.append(sql)
            return executar(sql, params)

        cursor.execute = execute
        return cursor

    monkeypatch.setattr(connection, "cursor", espiar)

    api_de(empresa_a).post(URL, servico_json())

    assert any("pg_advisory_xact_lock" in sql for sql in comandos)


def test_oficiais_disponiveis_lista_apenas_vinculados_ativos(api_de, empresa_a, empresa_b):
    oficial_a = garantir_servico_oficial(empresa_a, codigo_tributacao_nacional="010101")
    garantir_servico_oficial(empresa_b, codigo_tributacao_nacional="170101")
    inativo = ServicoOficial(
        codigo_tributacao_nacional="170101",
        nbs="110014000",
        cst_ibs_cbs="000",
        c_class_trib="000001",
        codigo_indicador_operacao="100301",
        ativo=False,
    )
    inativo.full_clean()
    inativo.save()
    empresa_a.servicos_oficiais.add(inativo)

    resposta = api_de(empresa_a, Perfil.CONSULTA).get(f"{URL}oficiais-disponiveis/")

    assert resposta.status_code == 200
    assert [item["id"] for item in resposta.json()] == [oficial_a.pk]


def test_servico_exige_oficial_vinculado_ativo_e_trava_campos_fiscais(api_de, empresa_a, empresa_b):
    api = api_de(empresa_a)
    sem_vinculo = api.post(URL, servico_json(servico_oficial_id=None))
    assert sem_vinculo.status_code == 400
    assert "servico_oficial_id" in sem_vinculo.json()

    oficial_b = garantir_servico_oficial(empresa_b, codigo_tributacao_nacional="010101")
    de_outra = api.post(URL, servico_json(servico_oficial_id=oficial_b.pk))
    assert de_outra.status_code == 400
    assert "servico_oficial_id" in de_outra.json()

    oficial_a = garantir_servico_oficial(empresa_a, codigo_tributacao_nacional="170101")
    criado = api.post(
        URL,
        {
            "nome": "Consultoria vinculada",
            "descricao": "Serviço vinculado a registro oficial.",
            "servico_oficial_id": oficial_a.pk,
            "aliquota_iss": "3.00",
            "vigencia_inicio": "2026-01-01",
        },
    )
    assert criado.status_code == 201, criado.json()
    assert criado.json()["codigo_tributacao_nacional"] == "170101"
    assert criado.json()["nbs"] == "106084000"

    for campo, valor in (
        ("codigo_tributacao_nacional", "999999"),
        ("nbs", "999999999"),
        ("cst_ibs_cbs", "200"),
        ("c_class_trib", "410001"),
        ("codigo_indicador_operacao", "050101"),
    ):
        tentativa = api.patch(f"{URL}{criado.json()['id']}/", {campo: valor})
        assert tentativa.status_code == 400
        assert campo in tentativa.json()
