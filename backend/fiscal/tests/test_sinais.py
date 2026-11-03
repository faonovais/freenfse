"""Sinais fiscais: quem os ouve nunca interfere no resultado da emissão."""

import logging

import pytest

from fiscal import signals
from fiscal.models import Nfse
from fiscal.services import emissao

pytestmark = pytest.mark.django_db
S = Nfse.Situacao


def _emitir(empresa, nota):
    emissao.solicitar_emissao(nota, usuario=None, empresa=empresa)
    emissao.executar_emissao(empresa, nota.pk)
    nota.refresh_from_db()
    return nota


@pytest.fixture
def ouvinte():
    """Registra um receptor temporário de `nfse_autorizada` e o remove ao final."""
    recebidos = []

    def receptor(sender, nfse, **_):
        recebidos.append((nfse.pk, nfse.situacao))

    signals.nfse_autorizada.connect(receptor, weak=False, dispatch_uid="teste.ouvinte")
    yield recebidos
    signals.nfse_autorizada.disconnect(dispatch_uid="teste.ouvinte")


def test_a_autorizacao_avisa_uma_vez_com_a_nota_ja_autorizada(
    empresa_pronta, nova_nota, sefin, ouvinte
):
    nota = _emitir(empresa_pronta, nova_nota())

    assert nota.situacao == S.AUTORIZADA
    assert ouvinte == [(nota.pk, S.AUTORIZADA)]


def test_receptor_que_falha_nao_muda_o_resultado_fiscal_e_fica_no_log(
    empresa_pronta, nova_nota, sefin, caplog
):
    def quebrado(sender, **_):
        raise RuntimeError("falha do receptor")

    signals.nfse_autorizada.connect(quebrado, weak=False, dispatch_uid="teste.quebrado")
    try:
        with caplog.at_level(logging.ERROR, logger="fiscal.signals"):
            nota = _emitir(empresa_pronta, nova_nota())
    finally:
        signals.nfse_autorizada.disconnect(dispatch_uid="teste.quebrado")

    assert nota.situacao == S.AUTORIZADA
    assert nota.chave and nota.xml_nfse
    assert sefin.total_de_posts == 1
    assert any("falha do receptor" in r.getMessage() for r in caplog.records)
