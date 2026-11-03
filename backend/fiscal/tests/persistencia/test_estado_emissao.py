"""`EstadoEmissaoPostgres` contra o contrato da freedfe e as regras próprias da aplicação."""

import pytest
from django.db import IntegrityError, transaction
from django_tenants.utils import schema_context
from freedfe.excecoes import ValidacaoErro
from freedfe.nfse.estado_emissao import SituacaoEmissao

from fiscal.persistencia.estado_emissao import EstadoEmissaoPostgres
from fiscal.persistencia.modelos import EmissaoDps
from fiscal.tests.persistencia.contrato_estado_emissao import (
    EMITENTE,
    SERIE,
    ContratoEstadoEmissao,
    montar_id,
)

pytestmark = pytest.mark.django_db


class TestContratoDaFreedfe(ContratoEstadoEmissao):
    """Passa por inteiro na suíte de contrato da biblioteca."""

    @pytest.fixture
    def criar_estado(self, empresa_ativa, relogio):
        return lambda: EstadoEmissaoPostgres(relogio)


def test_o_banco_recusa_numero_repetido_para_o_mesmo_emitente(empresa_ativa, relogio):
    """Defesa em profundidade: mesmo sem o cadeado, a numeração não duplica."""
    estado = EstadoEmissaoPostgres(relogio)
    estado.reservar(montar_id(1), SERIE, 1)

    # Outro Id (outro município) para o mesmo emitente, série e número.
    id_de_outro_municipio = montar_id(1).replace("DPS2927408", "DPS3550308")
    with pytest.raises(ValidacaoErro, match="já está reservada"):
        estado.reservar(id_de_outro_municipio, SERIE, 1)

    assert EmissaoDps.objects.count() == 1


def test_a_restricao_unica_existe_no_banco(empresa_ativa, relogio):
    EmissaoDps.objects.create(id_dps=montar_id(1), emitente=EMITENTE, serie=SERIE, numero=1)
    with pytest.raises(IntegrityError), transaction.atomic():
        EmissaoDps.objects.create(
            id_dps=montar_id(1).replace("DPS2927408", "DPS3550308"),
            emitente=EMITENTE,
            serie=SERIE,
            numero=1,
        )


def test_id_malformado_e_recusado(empresa_ativa, relogio):
    with pytest.raises(ValidacaoErro, match="Id da DPS inválido"):
        EstadoEmissaoPostgres(relogio).reservar("DPS123", 1, 1)


def test_a_reserva_grava_a_nota_dona_da_dps(empresa_ativa, relogio):
    from fiscal.tests.persistencia.fabricas import criar_nfse

    nfse = criar_nfse()
    estado = EstadoEmissaoPostgres(relogio, nfse_id=nfse.pk)

    reservada = estado.reservar_proximo(SERIE, montar_id)

    assert EmissaoDps.objects.get(id_dps=reservada.id_dps).nfse_id == nfse.pk
    assert list(nfse.emissoes.values_list("numero", flat=True)) == [1]


def test_empresas_tem_numeracao_e_estado_independentes(empresa_a, empresa_b, relogio):
    with schema_context(empresa_a.schema_name):
        a = EstadoEmissaoPostgres(relogio)
        assert [a.reservar_proximo(SERIE, montar_id).numero for _ in range(3)] == [1, 2, 3]
        a.marcar(montar_id(2), SituacaoEmissao.ENVIADA)

    with schema_context(empresa_b.schema_name):
        b = EstadoEmissaoPostgres(relogio)
        assert b.listar() == []
        assert b.reservar_proximo(SERIE, montar_id).numero == 1
        assert b.obter(montar_id(2)) is None

    with schema_context(empresa_a.schema_name):
        assert [r.numero for r in EstadoEmissaoPostgres(relogio).listar()] == [1, 2, 3]
