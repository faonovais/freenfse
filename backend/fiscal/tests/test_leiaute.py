"""Leiaute da DPS: NT 004 até 30/11/2026 (produção) e NT 009 depois; produção restrita é NT 009."""

import datetime as dt

import pytest
from lxml import etree

from fiscal import gateway
from fiscal.models import Nfse
from fiscal.services import emissao
from fiscal.tests.apoio import RelogioControlavel, preparar_empresa_para_emitir

NS = "{http://www.sped.fazenda.gov.br/nfse}"
S = Nfse.Situacao


@pytest.mark.parametrize(
    ("instante_utc", "esperado"),
    [
        (dt.datetime(2026, 10, 30, 12, 0, tzinfo=dt.UTC), "nt004_v2"),
        (dt.datetime(2026, 11, 30, 12, 0, tzinfo=dt.UTC), "nt004_v2"),
        # 23:59:59 de 30/11 em Brasília ainda é NT 004; vale a data de Brasília, não a UTC.
        (dt.datetime(2026, 12, 1, 2, 59, 59, tzinfo=dt.UTC), "nt004_v2"),
        (dt.datetime(2026, 12, 1, 3, 0, 0, tzinfo=dt.UTC), "nt009_v101"),
        (dt.datetime(2027, 3, 1, 12, 0, tzinfo=dt.UTC), "nt009_v101"),
    ],
)
def test_producao_troca_de_leiaute_em_1_de_dezembro_de_2026(instante_utc, esperado):
    assert gateway.leiaute_em_vigor(True, lambda: instante_utc) == esperado


@pytest.mark.parametrize(
    "instante_utc",
    [dt.datetime(2026, 10, 30, tzinfo=dt.UTC), dt.datetime(2026, 11, 30, tzinfo=dt.UTC)],
)
def test_producao_restrita_usa_sempre_a_nt_009(instante_utc):
    assert gateway.leiaute_em_vigor(False, lambda: instante_utc) == "nt009_v101"


def test_descricao_legivel_dos_leiautes():
    assert gateway.descricao_do_leiaute("nt004_v2") == "NT 004 v2.0"
    assert gateway.descricao_do_leiaute("nt009_v101") == "NT 009 v1.01"
    assert gateway.descricao_do_leiaute("") == ""


# -- ponta a ponta: o leiaute usado fica gravado e muda o XML enviado --------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("ambiente", "instante", "leiaute"),
    [
        ("producao", dt.datetime(2026, 11, 2, 15, 0, tzinfo=dt.UTC), "nt004_v2"),
        ("producao", dt.datetime(2026, 12, 1, 15, 0, tzinfo=dt.UTC), "nt009_v101"),
        ("producao_restrita", dt.datetime(2026, 11, 2, 15, 0, tzinfo=dt.UTC), "nt009_v101"),
    ],
)
def test_cada_nota_grava_o_leiaute_usado_e_o_xml_acompanha(
    empresa_pronta, monkeypatch, ambiente, instante, leiaute
):
    from cadastros.models import Servico
    from fiscal.tests.apoio import criar_rascunho_de_teste
    from fiscal.tests.sefin_simulada import SefinSimulada

    simulada = SefinSimulada()
    relogio = RelogioControlavel(instante)
    monkeypatch.setattr(
        emissao,
        "opcoes_de_execucao",
        lambda: {"transporte": simulada, "pausa": lambda _s: None, "relogio": relogio},
    )
    preparar_empresa_para_emitir(empresa_pronta, ambiente=ambiente)
    nota = criar_rascunho_de_teste(
        valores={"servico": "1000.00", "deducao_valor": "100.00"},
    )
    Servico.objects.filter(pk=nota.servico["id"]).update(nbs="123456789")
    nota.servico = {**nota.servico, "nbs": "123456789"}
    nota.save()
    emissao.solicitar_emissao(nota, usuario=None, empresa=empresa_pronta)
    emissao.executar_emissao(empresa_pronta, nota.pk)
    nota.refresh_from_db()

    assert nota.situacao == S.AUTORIZADA
    assert nota.leiaute == leiaute
    dps = etree.fromstring(bytes(nota.xml_dps))
    servico = dps.find(f".//{NS}cServ")
    ordem = [etree.QName(filho).localname for filho in servico]
    if leiaute == "nt004_v2":
        assert ordem.index("xDescServ") < ordem.index("cNBS")
        assert dps.find(f".//{NS}vDedRed") is not None and dps.find(f".//{NS}vAjusteBC") is None
    else:
        assert ordem.index("cNBS") < ordem.index("xDescServ")
        assert dps.find(f".//{NS}vAjusteBC") is not None and dps.find(f".//{NS}vDedRed") is None
