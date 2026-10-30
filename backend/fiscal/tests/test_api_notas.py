"""API das notas: permissões por operação, isolamento entre empresas, emissão e eventos."""

import datetime as dt

import pytest
from django_tenants.utils import schema_context

from core.models import LogAuditoria
from core.permissoes import Perfil
from fiscal import tasks
from fiscal.models import Nfse
from fiscal.services import emissao
from fiscal.tests.apoio import (
    criar_cadastros_de_teste,
    criar_rascunho_de_teste,
    preparar_empresa_para_emitir,
)

pytestmark = pytest.mark.django_db
NOTAS = "/api/fiscal/notas/"
S = Nfse.Situacao
JUSTIFICATIVA = "Nota emitida com o valor errado."


def _preparar(empresa):
    with schema_context(empresa.schema_name):
        preparar_empresa_para_emitir(empresa)


def _rascunho(empresa, **extra):
    with schema_context(empresa.schema_name):
        return criar_rascunho_de_teste(**extra)


def _corpo(empresa, **extra):
    """Corpo de criação de nota com os cadastros de teste da empresa."""
    with schema_context(empresa.schema_name):
        tomador, servico = criar_cadastros_de_teste()
    corpo = {
        "tomador": tomador.pk,
        "servico": servico.pk,
        "competencia": "2026-10-01",
        "valores": {"servico": "1500.00"},
    }
    corpo.update(extra)
    return corpo


@pytest.fixture
def fila(monkeypatch):
    """Substitui o `delay` do Celery: registra o que seria enfileirado, sem broker."""
    from types import SimpleNamespace

    from fiscal.api import notas

    enfileiradas = []
    monkeypatch.setattr(tasks.emitir_nfse, "delay", lambda *a: enfileiradas.append(a))
    # O teste roda dentro de uma transação que nunca confirma: o `on_commit` roda na hora.
    monkeypatch.setattr(notas, "transaction", SimpleNamespace(on_commit=lambda f: f()))
    return enfileiradas


@pytest.fixture
def emissor(api_de, empresa_a):
    _preparar(empresa_a)
    return api_de(empresa_a, Perfil.EMISSOR)


def _emitir_pela_api(api, empresa, fila, nota_id):
    resposta = api.post(f"{NOTAS}{nota_id}/emitir/")
    assert resposta.status_code == 202, resposta.content
    schema, id_enfileirado = fila[-1]
    with schema_context(schema):
        emissao.executar_emissao(empresa, id_enfileirado)
    return api.get(f"{NOTAS}{nota_id}/").json()


# -- permissões --------------------------------------------------------------------------


def test_consulta_le_mas_nao_cria_emite_cancela_nem_substitui(api_de, empresa_a, sefin, fila):
    _preparar(empresa_a)
    nota = _rascunho(empresa_a)
    consulta = api_de(empresa_a, Perfil.CONSULTA)

    assert consulta.get(NOTAS).status_code == 200
    assert consulta.get(f"{NOTAS}{nota.pk}/").status_code == 200
    assert consulta.get(f"{NOTAS}prontidao/").status_code == 200
    assert consulta.post(NOTAS, _corpo(empresa_a)).status_code == 403
    assert consulta.post(f"{NOTAS}previa/", _corpo(empresa_a)).status_code == 403
    assert consulta.patch(f"{NOTAS}{nota.pk}/", _corpo(empresa_a)).status_code == 403
    assert consulta.post(f"{NOTAS}{nota.pk}/emitir/").status_code == 403
    assert consulta.post(f"{NOTAS}{nota.pk}/cancelar/", {"codigo_motivo": 1}).status_code == 403
    assert (
        consulta.post(f"{NOTAS}{nota.pk}/substituir/", {"codigo_motivo": "01"}).status_code == 403
    )
    assert fila == []


def test_sem_a_permissao_de_cancelar_nao_cancela(api_de, empresa_a, sefin, fila):
    _preparar(empresa_a)
    api = api_de(empresa_a, Perfil.EMISSOR, permissoes_removidas=["nfse.cancelar"])
    nota = api.post(NOTAS, _corpo(empresa_a)).json()
    _emitir_pela_api(api, empresa_a, fila, nota["id"])

    resposta = api.post(
        f"{NOTAS}{nota['id']}/cancelar/", {"codigo_motivo": 1, "justificativa": JUSTIFICATIVA}
    )

    assert resposta.status_code == 403
    assert api.get(f"{NOTAS}{nota['id']}/").json()["situacao"] == "autorizada"
    assert [c for c in sefin.chamadas if c[1].endswith("/eventos") and c[0] == "POST"] == []


def test_sem_a_permissao_de_substituir_nao_cria_nota_substituta(api_de, empresa_a, sefin, fila):
    _preparar(empresa_a)
    api = api_de(empresa_a, Perfil.EMISSOR, permissoes_removidas=["nfse.substituir"])
    nota = api.post(NOTAS, _corpo(empresa_a)).json()
    _emitir_pela_api(api, empresa_a, fila, nota["id"])

    resposta = api.post(f"{NOTAS}{nota['id']}/substituir/", {"codigo_motivo": "01"})

    assert resposta.status_code == 403
    assert api.get(NOTAS).json()["count"] == 1


def test_substituta_exige_a_permissao_de_substituir_tambem_para_emitir(
    api_de, empresa_a, sefin, fila
):
    _preparar(empresa_a)
    api = api_de(empresa_a, Perfil.EMISSOR)
    original = api.post(NOTAS, _corpo(empresa_a)).json()
    _emitir_pela_api(api, empresa_a, fila, original["id"])
    substituta = api.post(f"{NOTAS}{original['id']}/substituir/", {"codigo_motivo": "01"}).json()
    # Tira a permissão de substituir antes de emitir a substituta.
    from core.models import VinculoUsuarioEmpresa

    vinculo = VinculoUsuarioEmpresa.objects.get()
    vinculo.permissoes_removidas = ["nfse.substituir"]
    vinculo.save()

    resposta = api.post(f"{NOTAS}{substituta['id']}/emitir/")

    assert resposta.status_code == 403 and resposta.json()["codigo"] == "permissao_negada"


def test_sem_empresa_ou_sem_vinculo_nao_ha_acesso(
    cliente_de, usuario, empresa_a, empresa_b, vincular
):
    vincular(usuario, empresa_a, Perfil.EMISSOR)
    cliente = cliente_de(usuario)

    assert cliente.get(NOTAS).status_code in (400, 403)  # sem X-Empresa
    assert cliente.get(NOTAS, HTTP_X_EMPRESA=str(empresa_b.pk)).status_code == 403
    assert cliente_de().get(NOTAS, HTTP_X_EMPRESA=str(empresa_a.pk)).status_code in (401, 403)


# -- isolamento --------------------------------------------------------------------------


def test_notas_de_uma_empresa_nunca_aparecem_na_outra(
    api_de, empresa_a, empresa_b, usuario, vincular, cliente_de
):
    from cadastros.tests.conftest import Api

    _preparar(empresa_a)
    _preparar(empresa_b)
    nota_a = _rascunho(empresa_a, valor="111.00")
    nota_b = _rascunho(empresa_b, valor="222.00")
    vincular(usuario, empresa_a, Perfil.EMISSOR)
    vincular(usuario, empresa_b, Perfil.EMISSOR)
    cliente = cliente_de(usuario)
    na_a, na_b = Api(cliente, empresa_a), Api(cliente, empresa_b)

    assert [n["valor_servico"] for n in na_a.get(NOTAS).json()["results"]] == ["111.00"]
    assert [n["valor_servico"] for n in na_b.get(NOTAS).json()["results"]] == ["222.00"]
    assert na_b.get(f"{NOTAS}{nota_a.pk}/").status_code in (404, 200) and (
        nota_a.pk == nota_b.pk or na_b.get(f"{NOTAS}{nota_a.pk}/").status_code == 404
    )
    # Mesmo que os ids coincidam (cada schema tem a sua sequência), o conteúdo é o da empresa.
    assert na_a.get(f"{NOTAS}{nota_a.pk}/").json()["valor_servico"] == "111.00"
    assert na_b.get(f"{NOTAS}{nota_b.pk}/").json()["valor_servico"] == "222.00"


def test_numeracao_independente_por_empresa_pela_api(
    api_de, empresa_a, empresa_b, usuario, vincular, cliente_de, sefin, fila
):
    from cadastros.tests.conftest import Api

    _preparar(empresa_a)
    _preparar(empresa_b)
    vincular(usuario, empresa_a, Perfil.EMISSOR)
    vincular(usuario, empresa_b, Perfil.EMISSOR)
    cliente = cliente_de(usuario)
    resultados = {}
    for empresa in (empresa_a, empresa_b):
        api = Api(cliente, empresa)
        nota = api.post(NOTAS, _corpo(empresa)).json()
        resultados[empresa.cnpj] = _emitir_pela_api(api, empresa, fila, nota["id"])

    assert {r["numero_dps"] for r in resultados.values()} == {1}
    assert {r["id_dps"][11:25] for r in resultados.values()} == {empresa_a.cnpj, empresa_b.cnpj}


# -- prontidão e bloqueios ---------------------------------------------------------------


def test_prontidao_aponta_o_que_falta_com_a_tela_para_resolver(api_de, empresa_a):
    api = api_de(empresa_a, Perfil.EMISSOR)

    dados = api.get(f"{NOTAS}prontidao/").json()

    assert dados["pronta"] is False
    assert {b["codigo"] for b in dados["bloqueios"]} == {"sem_certificado", "sem_municipio"}
    telas = {b["tela"] for b in dados["bloqueios"]}
    assert telas == {"/fiscal/certificado", "/fiscal/parametros"}
    assert dados["ambiente"] == "producao_restrita" and dados["leiaute"] == "nt009_v101"


def test_prontidao_com_a_empresa_pronta_e_as_opcoes_de_motivo(emissor):
    dados = emissor.get(f"{NOTAS}prontidao/").json()

    assert dados["pronta"] is True and dados["bloqueios"] == []
    assert {m["codigo"] for m in dados["motivos_de_cancelamento"]} == {1, 2, 9}
    assert "99" in {m["codigo"] for m in dados["motivos_de_substituicao"]}


def test_emitir_com_a_empresa_nao_pronta_responde_409_com_os_motivos(api_de, empresa_a, fila):
    with schema_context(empresa_a.schema_name):
        nota = criar_rascunho_de_teste()
    api = api_de(empresa_a, Perfil.EMISSOR)

    resposta = api.post(f"{NOTAS}{nota.pk}/emitir/")

    assert resposta.status_code == 409
    assert resposta.json()["codigo"] == "empresa_nao_pronta"
    assert resposta.json()["bloqueios"]
    assert fila == []


# -- rascunho, prévia e validação --------------------------------------------------------


def test_previa_calcula_sem_gravar_nada(emissor, empresa_a):
    antes = emissor.get(NOTAS).json()["count"]

    resposta = emissor.post(f"{NOTAS}previa/", _corpo(empresa_a))

    assert resposta.status_code == 200
    dados = resposta.json()
    assert dados["totais"]["valor_iss"] == "30.00"  # 2% de 1500,00
    assert dados["tomador"]["nome"] == "TOMADOR FICTICIO LTDA"
    assert dados["servico"]["codigo_tributacao_nacional"] == "170101"
    assert emissor.get(NOTAS).json()["count"] == antes


def test_criar_rascunho_guarda_o_snapshot_e_editar_cadastro_nao_altera_a_nota(emissor, empresa_a):
    nota = emissor.post(NOTAS, _corpo(empresa_a)).json()
    assert nota["situacao"] == "rascunho" and nota["tomador"]["nome"] == "TOMADOR FICTICIO LTDA"
    with schema_context(empresa_a.schema_name):
        from cadastros.models import Pessoa, Servico

        Pessoa.objects.update(nome="NOME NOVO DEPOIS DA NOTA")
        Servico.objects.update(descricao="Descrição nova", aliquota_iss="5.00")

    detalhe = emissor.get(f"{NOTAS}{nota['id']}/").json()

    assert detalhe["tomador"]["nome"] == "TOMADOR FICTICIO LTDA"
    assert detalhe["servico"]["descricao"] == "Consultoria em gestão agrícola."
    assert detalhe["totais"]["valor_iss"] == "30.00"
    assert detalhe["tomador_nome"] == "TOMADOR FICTICIO LTDA"


@pytest.mark.parametrize(
    ("ajuste", "campo"),
    [
        ({"competencia": "2025-01-01"}, "servico"),  # serviço sem vigência nessa data
        ({"tomador": 999999}, "tomador"),
        ({"valores": {"servico": "-1"}}, "valores.servico"),
        ({"valores": {"servico": ""}}, "valores.servico"),
        ({"competencia": (dt.date.today() + dt.timedelta(days=40)).isoformat()}, "competencia"),
    ],
)
def test_dados_invalidos_voltam_400_apontando_o_campo(emissor, empresa_a, ajuste, campo):
    resposta = emissor.post(NOTAS, _corpo(empresa_a, **ajuste))

    assert resposta.status_code == 400
    assert campo in resposta.json()


def test_servico_com_retencao_de_pis_cofins_e_bloqueado_com_explicacao(emissor, empresa_a):
    corpo = _corpo(empresa_a)
    with schema_context(empresa_a.schema_name):
        from cadastros.models import Servico

        Servico.objects.update(retencao_pis="0.65")

    resposta = emissor.post(NOTAS, corpo)

    assert resposta.status_code == 400
    assert "PIS/COFINS" in str(resposta.json()["servico"])


def test_nota_rejeitada_pode_ser_corrigida_mas_a_autorizada_nao(emissor, empresa_a, sefin, fila):
    sefin.proximas(("rejeitar", [("E0188", "CNPJ inválido.")]))
    nota = emissor.post(NOTAS, _corpo(empresa_a)).json()
    rejeitada = _emitir_pela_api(emissor, empresa_a, fila, nota["id"])
    assert rejeitada["situacao"] == "rejeitada" and rejeitada["acoes"]["editar"]

    corrigida = emissor.patch(
        f"{NOTAS}{nota['id']}/", _corpo(empresa_a, valores={"servico": "1600.00"})
    )
    assert corrigida.status_code == 200 and corrigida.json()["valor_servico"] == "1600.00"

    autorizada = _emitir_pela_api(emissor, empresa_a, fila, nota["id"])
    assert autorizada["situacao"] == "autorizada" and autorizada["numero_dps"] == 1
    assert emissor.patch(f"{NOTAS}{nota['id']}/", _corpo(empresa_a)).status_code == 400


# -- emissão, cancelamento e substituição pela API ---------------------------------------


def test_emitir_responde_202_e_a_tarefa_conclui(emissor, empresa_a, sefin, fila):
    nota = emissor.post(NOTAS, _corpo(empresa_a)).json()

    resposta = emissor.post(f"{NOTAS}{nota['id']}/emitir/")

    assert resposta.status_code == 202 and resposta.json()["situacao"] == "enviando"
    assert fila == [(empresa_a.schema_name, nota["id"])]
    with schema_context(empresa_a.schema_name):
        emissao.executar_emissao(empresa_a, nota["id"])
    final = emissor.get(f"{NOTAS}{nota['id']}/").json()
    assert final["situacao"] == "autorizada"
    assert final["leiaute"] == "nt009_v101" and final["leiaute_descricao"] == "NT 009 v1.01"
    assert final["acoes"]["cancelar"] and final["acoes"]["substituir"] and final["acoes"]["danfse"]
    assert [h["para"] for h in final["historico"]] == ["enviando", "autorizada"]


def test_emitir_duas_vezes_a_mesma_nota_nao_enfileira_de_novo(emissor, empresa_a, sefin, fila):
    nota = emissor.post(NOTAS, _corpo(empresa_a)).json()
    primeira = emissor.post(f"{NOTAS}{nota['id']}/emitir/")
    segunda = emissor.post(f"{NOTAS}{nota['id']}/emitir/")

    assert primeira.status_code == 202
    assert segunda.status_code == 409 and segunda.json()["codigo"] == "operacao_recusada"


def test_cancelar_pela_api_confirmado_e_recusado(emissor, empresa_a, sefin, fila):
    nota = emissor.post(NOTAS, _corpo(empresa_a)).json()
    _emitir_pela_api(emissor, empresa_a, fila, nota["id"])
    url = f"{NOTAS}{nota['id']}/cancelar/"

    curta = emissor.post(url, {"codigo_motivo": 1, "justificativa": "curta"})
    assert curta.status_code == 400 and "justificativa" in curta.json()

    sefin.cancelamento_recusado = ("E0824", "Prazo expirado.")
    recusada = emissor.post(url, {"codigo_motivo": 1, "justificativa": JUSTIFICATIVA})
    assert recusada.status_code == 422
    corpo = recusada.json()
    assert corpo["codigo"] == "cancelamento_recusado" and corpo["erros"][0]["codigo"] == "E0824"
    assert "prefeitura" in corpo["detalhe"]
    assert emissor.get(f"{NOTAS}{nota['id']}/").json()["situacao"] == "autorizada"

    sefin.cancelamento_recusado = None
    cancelada = emissor.post(url, {"codigo_motivo": 1, "justificativa": JUSTIFICATIVA})
    assert cancelada.status_code == 200 and cancelada.json()["situacao"] == "cancelada"
    assert [e["tipo_evento"] for e in cancelada.json()["eventos"]] == ["101101"]
    acoes = set(LogAuditoria.objects.values_list("acao", flat=True))
    assert {"nfse_cancelada", "nfse_cancelamento_recusado"} <= acoes


def test_substituir_pela_api_cria_o_rascunho_e_a_original_so_muda_com_a_sefin(
    emissor, empresa_a, sefin, fila
):
    original = emissor.post(NOTAS, _corpo(empresa_a)).json()
    _emitir_pela_api(emissor, empresa_a, fila, original["id"])

    criada = emissor.post(
        f"{NOTAS}{original['id']}/substituir/",
        {"codigo_motivo": "99", "motivo": "Valor do serviço corrigido."},
    )
    assert criada.status_code == 201
    substituta = criada.json()
    assert substituta["situacao"] == "rascunho" and substituta["substitui"] == original["id"]
    assert emissor.get(f"{NOTAS}{original['id']}/").json()["situacao"] == "autorizada"

    final = _emitir_pela_api(emissor, empresa_a, fila, substituta["id"])

    assert final["situacao"] == "autorizada"
    depois = emissor.get(f"{NOTAS}{original['id']}/").json()
    assert depois["situacao"] == "substituida" and depois["substituta"] == substituta["id"]
    assert "nfse_substituicao_criada" in set(LogAuditoria.objects.values_list("acao", flat=True))


def test_consultar_pela_api_atualiza_a_nota(emissor, empresa_a, sefin, fila):
    nota = emissor.post(NOTAS, _corpo(empresa_a)).json()
    autorizada = _emitir_pela_api(emissor, empresa_a, fila, nota["id"])
    sefin.eventos[autorizada["chave"]] = [sefin._evento(autorizada["chave"], "101101", "Por fora")]

    resposta = emissor.post(f"{NOTAS}{nota['id']}/consultar/")

    assert resposta.status_code == 200 and resposta.json()["situacao"] == "cancelada"


def test_baixar_xml_e_danfse(emissor, empresa_a, sefin, fila):
    nota = emissor.post(NOTAS, _corpo(empresa_a)).json()
    assert emissor.get(f"{NOTAS}{nota['id']}/xml/").status_code == 409
    autorizada = _emitir_pela_api(emissor, empresa_a, fila, nota["id"])

    xml = emissor.get(f"{NOTAS}{nota['id']}/xml/")
    pdf = emissor.get(f"{NOTAS}{nota['id']}/danfse/")

    assert xml.status_code == 200 and xml["Content-Type"].startswith("application/xml")
    assert f"nfse-{autorizada['chave']}.xml" in xml["Content-Disposition"]
    assert xml.content == sefin.nfses[autorizada["chave"]]
    assert pdf.status_code == 200 and pdf["Content-Type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")


# -- filtros e listagem ------------------------------------------------------------------


def test_filtros_da_lista(emissor, empresa_a):
    with schema_context(empresa_a.schema_name):
        outubro = criar_rascunho_de_teste(competencia=dt.date(2026, 10, 1))
        setembro = criar_rascunho_de_teste(competencia=dt.date(2026, 9, 1), valor="500.00")
        Nfse.objects.filter(pk=setembro.pk).update(
            situacao=S.AUTORIZADA,
            numero_nfse="77",
            numero_dps=77,
            tomador_nome="OUTRA EMPRESA SA",
            tomador_documento="99888777000166",
        )

    def ids(**filtros):
        return {n["id"] for n in emissor.get(NOTAS, **filtros).json()["results"]}

    assert ids() == {outubro.pk, setembro.pk}
    assert ids(periodo_inicio="2026-10-01") == {outubro.pk}
    assert ids(periodo_fim="2026-09-30") == {setembro.pk}
    assert ids(situacao="autorizada") == {setembro.pk}
    assert ids(tomador="outra empresa") == {setembro.pk}
    assert ids(tomador="99.888.777") == {setembro.pk}
    assert ids(numero="77") == {setembro.pk}
    assert ids(situacao="cancelada") == set()
    assert emissor.get(NOTAS, periodo_inicio="ontem").status_code == 400


def test_lista_e_paginada(emissor, empresa_a):
    with schema_context(empresa_a.schema_name):
        for _ in range(3):
            criar_rascunho_de_teste()

    pagina = emissor.get(NOTAS, tamanho=2).json()

    assert pagina["count"] == 3 and len(pagina["results"]) == 2 and pagina["next"]


def test_conferir_nota_incerta_pela_api_nao_reenvia(emissor, empresa_a, sefin, fila):
    sefin.proximas("cai_depois_de_processar")
    nota = emissor.post(NOTAS, _corpo(empresa_a)).json()
    incerta = _emitir_pela_api(emissor, empresa_a, fila, nota["id"])
    assert incerta["situacao"] == "incerta" and incerta["acoes"]["conferir"]
    sefin.fora_do_ar = False

    conferida = emissor.post(f"{NOTAS}{nota['id']}/conferir/")

    assert conferida.status_code == 200 and conferida.json()["situacao"] == "autorizada"
    assert sefin.total_de_posts == 1
    assert emissor.post(f"{NOTAS}{nota['id']}/conferir/").status_code == 409  # já autorizada


def test_consulta_pode_conferir_mas_nao_emitir(api_de, empresa_a, sefin, fila):
    _preparar(empresa_a)
    emissor = api_de(empresa_a, Perfil.EMISSOR)
    sefin.proximas("timeout")
    nota = emissor.post(NOTAS, _corpo(empresa_a)).json()
    _emitir_pela_api(emissor, empresa_a, fila, nota["id"])
    from rest_framework.test import APIClient

    from cadastros.tests.conftest import Api
    from core.models import Usuario, VinculoUsuarioEmpresa

    leitor = Usuario.objects.create_user(email="leitor@exemplo.test", password="x" * 12, nome="L")
    VinculoUsuarioEmpresa.objects.create(usuario=leitor, empresa=empresa_a, perfil=Perfil.CONSULTA)
    cliente = APIClient()
    cliente.force_login(leitor)
    api_leitor = Api(cliente, empresa_a)

    assert api_leitor.post(f"{NOTAS}{nota['id']}/emitir/").status_code == 403
    assert api_leitor.post(f"{NOTAS}{nota['id']}/conferir/").status_code == 200
