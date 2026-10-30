"""Emissões simultâneas da mesma empresa e série: threads reais, conexões reais ao PostgreSQL.

O que se exige: números distintos e sem lacuna, nenhuma DPS enviada em duplicidade e **um
envio por vez** por empresa (a trava dura todo o POST à Sefin). Há uma mutação para cada
proteção (sem a trava, o teste de "um por vez" falha; sem o `FOR UPDATE`, o de numeração falha).
"""

import pytest
from django_tenants.utils import schema_context

from fiscal.models import Nfse
from fiscal.persistencia.modelos import EmissaoDps
from fiscal.services import emissao
from fiscal.tests.apoio import (
    RelogioControlavel,
    criar_rascunho_de_teste,
    preparar_empresa_para_emitir,
)
from fiscal.tests.persistencia.apoio_threads import executar_em_paralelo
from fiscal.tests.sefin_simulada import SefinSimulada

pytestmark = pytest.mark.django_db(transaction=True)
PARALELAS = 6


@pytest.fixture
def sefin_lenta(monkeypatch):
    """Sefin que demora 50 ms por emissão: se duas passarem juntas, `max_simultaneas` sobe."""
    simulada = SefinSimulada()
    simulada.latencia = 0.05
    relogio = RelogioControlavel()
    monkeypatch.setattr(
        emissao,
        "opcoes_de_execucao",
        lambda: {"transporte": simulada, "pausa": lambda _s: None, "relogio": relogio},
    )
    return simulada


def _preparar(empresa, quantidade):
    """Deixa a empresa pronta e solicita a emissão de `quantidade` notas; devolve os ids."""
    with schema_context(empresa.schema_name):
        preparar_empresa_para_emitir(empresa)
        ids = []
        for i in range(quantidade):
            nota = criar_rascunho_de_teste(valor=f"{100 + i}.00")
            emissao.solicitar_emissao(nota, usuario=None, empresa=empresa)
            ids.append(nota.pk)
        return ids


def test_emissoes_paralelas_da_mesma_serie_geram_numeros_distintos_um_envio_por_vez(
    empresas_confirmadas, sefin_lenta
):
    alfa, _ = empresas_confirmadas
    ids = _preparar(alfa, PARALELAS)

    resultados, erros = executar_em_paralelo(
        [(alfa.schema_name, lambda i=i: emissao.executar_emissao(alfa, i)) for i in ids]
    )

    assert erros == [None] * PARALELAS
    assert resultados == ["autorizada"] * PARALELAS
    with schema_context(alfa.schema_name):
        numeros = sorted(Nfse.objects.values_list("numero_dps", flat=True))
        assert numeros == list(range(1, PARALELAS + 1))  # distintos e sem lacuna
        assert EmissaoDps.objects.count() == PARALELAS
        assert set(EmissaoDps.objects.values_list("situacao", flat=True)) == {"autorizada"}
    assert sefin_lenta.total_de_posts == PARALELAS
    assert len(set(sefin_lenta.posts_de_emissao)) == PARALELAS  # nenhuma DPS enviada duas vezes
    assert sefin_lenta.max_simultaneas == 1  # a trava manteve um envio por vez


def test_empresas_diferentes_emitem_ao_mesmo_tempo_com_numeracao_independente(
    empresas_confirmadas, sefin_lenta
):
    alfa, beta = empresas_confirmadas
    ids_alfa = _preparar(alfa, 3)
    ids_beta = _preparar(beta, 3)

    tarefas = [(alfa.schema_name, lambda i=i: emissao.executar_emissao(alfa, i)) for i in ids_alfa]
    tarefas += [(beta.schema_name, lambda i=i: emissao.executar_emissao(beta, i)) for i in ids_beta]
    resultados, erros = executar_em_paralelo(tarefas)

    assert erros == [None] * 6 and resultados == ["autorizada"] * 6
    for empresa in (alfa, beta):
        with schema_context(empresa.schema_name):
            assert sorted(Nfse.objects.values_list("numero_dps", flat=True)) == [1, 2, 3]
            assert {n.id_dps[11:25] for n in Nfse.objects.all()} == {empresa.cnpj}
