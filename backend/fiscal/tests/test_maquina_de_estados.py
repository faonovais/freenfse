"""Máquina de estados da nota: só as transições da tabela, só pelo serviço."""

import pytest

from fiscal.models import Nfse, TransicaoInvalida
from fiscal.services.nfse_estados import TRANSICOES, pode_transicionar, transicionar
from fiscal.tests.persistencia.fabricas import criar_nfse

pytestmark = pytest.mark.django_db
S = Nfse.Situacao


@pytest.fixture
def nota(empresa_ativa_fiscal):
    return criar_nfse()


@pytest.fixture
def empresa_ativa_fiscal(empresa_a):
    from django_tenants.utils import schema_context

    with schema_context(empresa_a.schema_name):
        yield empresa_a


def test_fluxo_feliz_ate_cancelada(nota):
    for destino in (S.ENVIANDO, S.AUTORIZADA, S.CANCELADA):
        transicionar(nota, destino, motivo=f"vai para {destino}")

    assert nota.situacao == S.CANCELADA
    assert [(t.de, t.para) for t in nota.transicoes.all()] == [
        ("rascunho", "enviando"),
        ("enviando", "autorizada"),
        ("autorizada", "cancelada"),
    ]


@pytest.mark.parametrize(
    ("origem", "destino"),
    [(origem, destino) for origem in S for destino in S if destino not in TRANSICOES[origem]],
)
def test_toda_transicao_fora_da_tabela_e_recusada(nota, origem, destino):
    Nfse.objects.filter(pk=nota.pk).update(situacao=origem)
    nota.refresh_from_db()

    with pytest.raises(TransicaoInvalida):
        transicionar(nota, destino)

    nota.refresh_from_db()
    assert nota.situacao == origem
    assert not nota.transicoes.exists()


@pytest.mark.parametrize("terminal", [S.CANCELADA, S.SUBSTITUIDA])
def test_cancelada_e_substituida_sao_finais(nota, terminal):
    assert TRANSICOES[terminal] == set()
    assert not pode_transicionar(terminal, S.AUTORIZADA)


def test_nao_se_muda_a_situacao_por_atribuicao_direta(nota):
    nota.situacao = S.AUTORIZADA

    with pytest.raises(TransicaoInvalida, match="não pode ser alterada diretamente"):
        nota.save()

    nota.refresh_from_db()
    assert nota.situacao == S.RASCUNHO


def test_a_transicao_vale_para_o_banco_e_nao_para_a_instancia_velha(nota):
    velha = Nfse.objects.get(pk=nota.pk)
    transicionar(nota, S.ENVIANDO)

    with pytest.raises(TransicaoInvalida):
        transicionar(velha, S.ENVIANDO)  # o banco já está em "enviando"

    velha.refresh_from_db()
    assert velha.situacao == S.ENVIANDO


def test_a_mensagem_da_recusa_e_clara(nota):
    with pytest.raises(TransicaoInvalida, match="Rascunho.*não pode passar para 'Cancelada'"):
        transicionar(nota, S.CANCELADA)


def test_rejeitada_e_incerta_podem_ser_reenviadas_mas_nao_viram_autorizadas_do_nada(nota):
    assert pode_transicionar(S.REJEITADA, S.ENVIANDO)
    assert pode_transicionar(S.INCERTA, S.ENVIANDO)
    assert not pode_transicionar(S.REJEITADA, S.AUTORIZADA)
    assert pode_transicionar(S.INCERTA, S.AUTORIZADA)  # só a conferência com a Sefin
