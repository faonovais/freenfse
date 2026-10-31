"""A migração do IBS/CBS por empresa (0004) não perde nenhum dado existente (issue #20).

O teste volta o schema da empresa ao estado anterior (0003), grava dados como eles eram — a
configuração fiscal, uma nota com o IBS/CBS informado **na própria nota** (Fase 3) e um serviço
com classificação — aplica a 0004 e confere que tudo continua igual, com o padrão da empresa
nascendo desligado e vazio (nenhuma inferência a partir das notas antigas).
"""

import datetime as dt
import importlib
from decimal import Decimal

import pytest
from django.db import connection, migrations
from django.db.migrations.executor import MigrationExecutor
from django_tenants.utils import schema_context

ANTES = [("fiscal", "0003_situacao_descartada")]
DEPOIS = [("fiscal", "0004_ibs_cbs_por_empresa")]
GRUPO_DA_NOTA = {"codigo_indicador_operacao": "010101", "indicador_destinatario": 0}

pytestmark = pytest.mark.django_db


def _migrar(alvo):
    executor = MigrationExecutor(connection)
    executor.migrate(alvo)
    return MigrationExecutor(connection).loader.project_state(alvo).apps


def test_a_migracao_so_acrescenta_campos_com_padrao_nos_parametros():
    migracao = importlib.import_module("fiscal.migrations.0004_ibs_cbs_por_empresa").Migration

    assert [type(op) for op in migracao.operations] == [migrations.AddField, migrations.AddField]
    assert {op.model_name for op in migracao.operations} == {"parametrosfiscais"}
    assert {op.name for op in migracao.operations} == {
        "ibs_cbs_informar",
        "ibs_cbs_indicador_operacao",
    }
    # Nenhuma operação apaga, renomeia ou converte coluna existente: nada se perde.
    assert not any(
        isinstance(op, migrations.RemoveField | migrations.RenameField | migrations.RunPython)
        for op in migracao.operations
    )


def test_dados_de_antes_da_migracao_continuam_iguais_e_o_padrao_nasce_desligado(empresa_a):
    with schema_context(empresa_a.schema_name):
        antigo = _migrar(ANTES)
        Parametros = antigo.get_model("fiscal", "ParametrosFiscais")
        Nota = antigo.get_model("fiscal", "Nfse")
        Servico = antigo.get_model("cadastros", "Servico")
        assert not hasattr(Parametros, "ibs_cbs_informar")  # o estado "antes" é de verdade

        Parametros.objects.create(
            pk=1,
            serie_dps=7,
            ambiente="producao",
            codigo_municipio_emissor="2101400",
            convenio_resultado={"aderente": True},
            convenio_ambiente="producao",
        )
        servico = Servico.objects.create(
            nome="Consultoria com IBS/CBS",
            descricao="Consultoria.",
            codigo_tributacao_nacional="170101",
            nbs="113011000",
            cst_ibs_cbs="000",
            c_class_trib="000001",
            aliquota_iss=Decimal("2.00"),
            vigencia_inicio=dt.date(2026, 1, 1),
        )
        nota = Nota.objects.create(
            ambiente="producao",
            serie=7,
            competencia=dt.date(2026, 10, 1),
            valor_servico=Decimal("1000.00"),
            complementos={"informacoes_complementares": "texto", "ibs_cbs": GRUPO_DA_NOTA},
            servico={"nome": "Consultoria com IBS/CBS", "cst_ibs_cbs": "000"},
        )

        atual = _migrar(DEPOIS)

        Parametros = atual.get_model("fiscal", "ParametrosFiscais")
        parametros = Parametros.objects.get(pk=1)
        assert (parametros.serie_dps, parametros.ambiente) == (7, "producao")
        assert parametros.codigo_municipio_emissor == "2101400"
        assert parametros.convenio_resultado == {"aderente": True}
        assert parametros.convenio_ambiente == "producao"
        # O padrão da empresa nasce desligado e vazio: nada é inferido das notas antigas.
        assert parametros.ibs_cbs_informar is False
        assert parametros.ibs_cbs_indicador_operacao == ""
        # A nota antiga continua com o grupo que ela mesma levava (é o snapshot dela).
        nota_depois = atual.get_model("fiscal", "Nfse").objects.get(pk=nota.pk)
        assert nota_depois.complementos == {
            "informacoes_complementares": "texto",
            "ibs_cbs": GRUPO_DA_NOTA,
        }
        # O serviço, com a classificação, não foi tocado.
        servico_depois = atual.get_model("cadastros", "Servico").objects.get(pk=servico.pk)
        assert (servico_depois.nbs, servico_depois.cst_ibs_cbs, servico_depois.c_class_trib) == (
            "113011000",
            "000",
            "000001",
        )


def test_voltar_a_migracao_tambem_preserva_o_que_ja_existia(empresa_a):
    with schema_context(empresa_a.schema_name):
        atual = _migrar(DEPOIS)
        Parametros = atual.get_model("fiscal", "ParametrosFiscais")
        Parametros.objects.create(
            pk=1, serie_dps=9, ibs_cbs_informar=True, ibs_cbs_indicador_operacao="010101"
        )

        antigo = _migrar(ANTES)

        parametros = antigo.get_model("fiscal", "ParametrosFiscais").objects.get(pk=1)
        assert parametros.serie_dps == 9  # só as duas colunas novas saem
        _migrar(DEPOIS)  # e o schema fica no estado final para os demais testes
