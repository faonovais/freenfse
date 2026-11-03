"""A migração 0005 cifra os XMLs que já estavam em claro, sem perder nenhum (ADR 0008, issue #9).

O teste volta o schema da empresa ao estado anterior (0004), grava XMLs em claro como a Fase 3
gravava, aplica a 0005 e confere, **na coluna bruta**, que viraram tokens e que o conteúdo é o
mesmo. Também confere a idempotência, a reversão e a recusa de rodar sem as chaves.
"""

import datetime as dt
import hashlib
import importlib
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django_tenants.utils import schema_context

from core import crypto

ANTES = [("fiscal", "0004_ibs_cbs_por_empresa")]
DEPOIS = [("fiscal", "0005_xml_cifrado")]
XML_NFSE = b'<?xml version="1.0"?><NFSe><infNFSe Id="NFS123">tomador 12345678909</infNFSe></NFSe>'
XML_DPS = b'<?xml version="1.0"?><DPS><infDPS Id="DPS123">tomador 12345678909</infDPS></DPS>'
XML_EVENTO = b'<?xml version="1.0"?><evento>cancelamento 12345678909</evento>'
RESPOSTA = b'{"mensagem": "resposta bruta da Sefin"}'

pytestmark = pytest.mark.django_db


def _migrar(alvo):
    executor = MigrationExecutor(connection)
    executor.migrate(alvo)
    return MigrationExecutor(connection).loader.project_state(alvo).apps


def _bruto(tabela, coluna, pk):
    with connection.cursor() as cursor:
        cursor.execute(f'SELECT "{coluna}" FROM "{tabela}" WHERE id = %s', [pk])  # noqa: S608
        return bytes(cursor.fetchone()[0])


def _gravar_em_claro(apps):
    Nfse = apps.get_model("fiscal", "Nfse")
    nota = Nfse.objects.create(
        ambiente="producao",
        serie=7,
        competencia=dt.date(2026, 10, 1),
        valor_servico=Decimal("1000.00"),
        xml_dps=XML_DPS,
        xml_nfse=XML_NFSE,
        hash_xml_nfse=hashlib.sha256(XML_NFSE).hexdigest(),
    )
    sem_xml = Nfse.objects.create(
        ambiente="producao",
        serie=7,
        competencia=dt.date(2026, 10, 1),
        valor_servico=Decimal("10.00"),
    )
    evento = apps.get_model("fiscal", "EventoNfse").objects.create(
        nfse=nota, tipo_evento="101101", identificador="1", xml=XML_EVENTO
    )
    evidencia = apps.get_model("fiscal", "EvidenciaFiscal").objects.create(
        referencia="dps/x/1/resposta.json",
        tipo="dps",
        mes="2026-10",
        sufixo="resposta.json",
        conteudo=RESPOSTA,
        sha256=hashlib.sha256(RESPOSTA).hexdigest(),
    )
    documento = apps.get_model("fiscal", "DocumentoFiscal").objects.create(
        modelo="nfse",
        chave="1" * 50,
        tipo_xml="nfse",
        resumo={},
        xml=XML_NFSE,
        sha256=hashlib.sha256(XML_NFSE).hexdigest(),
    )
    return nota, sem_xml, evento, evidencia, documento


def test_os_xmls_em_claro_viram_tokens_sem_perder_o_conteudo(empresa_a):
    with schema_context(empresa_a.schema_name):
        antigo = _migrar(ANTES)
        nota, sem_xml, evento, evidencia, documento = _gravar_em_claro(antigo)
        assert _bruto("fiscal_nfse", "xml_nfse", nota.pk) == XML_NFSE  # o "antes" é de verdade

        _migrar(DEPOIS)

        for tabela, coluna, pk, original in (
            ("fiscal_nfse", "xml_nfse", nota.pk, XML_NFSE),
            ("fiscal_nfse", "xml_dps", nota.pk, XML_DPS),
            ("fiscal_eventonfse", "xml", evento.pk, XML_EVENTO),
            ("fiscal_evidenciafiscal", "conteudo", evidencia.pk, RESPOSTA),
            ("fiscal_documentofiscal", "xml", documento.pk, XML_NFSE),
        ):
            bruto = _bruto(tabela, coluna, pk)
            assert bruto.startswith(b"v1:")
            assert b"12345678909" not in bruto and original not in bruto
            assert crypto.decifrar_bytes(bruto) == original
        # A linha sem XML continua sem XML (nulo não vira texto cifrado).
        with connection.cursor() as cursor:
            cursor.execute("SELECT xml_nfse, xml_dps FROM fiscal_nfse WHERE id = %s", [sem_xml.pk])
            assert cursor.fetchone() == (None, None)
        # O hash gravado antes continua sendo o do XML em claro.
        with connection.cursor() as cursor:
            cursor.execute("SELECT hash_xml_nfse FROM fiscal_nfse WHERE id = %s", [nota.pk])
            assert cursor.fetchone()[0] == hashlib.sha256(XML_NFSE).hexdigest()


def test_rodar_a_conversao_de_novo_nao_cifra_duas_vezes(empresa_a):
    """Quem já é token fica como está (a conversão roda sobre o estado "antes", campo cru)."""
    with schema_context(empresa_a.schema_name):
        antigo = _migrar(ANTES)
        nota, *_ = _gravar_em_claro(antigo)
        _migrar(DEPOIS)
        primeiro = _bruto("fiscal_nfse", "xml_nfse", nota.pk)
        modulo = importlib.import_module("fiscal.migrations.0005_xml_cifrado")
        estado_antes = MigrationExecutor(connection).loader.project_state(ANTES).apps

        modulo.cifrar(estado_antes, SimpleNamespace(connection=connection))

        assert _bruto("fiscal_nfse", "xml_nfse", nota.pk) == primeiro
        assert crypto.decifrar_bytes(primeiro) == XML_NFSE


def test_reverter_a_migracao_devolve_o_xml_em_claro(empresa_a):
    with schema_context(empresa_a.schema_name):
        antigo = _migrar(ANTES)
        nota, *_ = _gravar_em_claro(antigo)
        _migrar(DEPOIS)
        assert _bruto("fiscal_nfse", "xml_nfse", nota.pk).startswith(b"v1:")

        _migrar(ANTES)

        assert _bruto("fiscal_nfse", "xml_nfse", nota.pk) == XML_NFSE
        assert _bruto("fiscal_nfse", "xml_dps", nota.pk) == XML_DPS
        _migrar(DEPOIS)  # e o schema fica no estado final para os demais testes


def test_sem_as_chaves_a_migracao_falha_em_vez_de_deixar_o_xml_em_claro(empresa_a, settings):
    with schema_context(empresa_a.schema_name):
        antigo = _migrar(ANTES)
        nota, *_ = _gravar_em_claro(antigo)
        settings.FREENFSE_CHAVES = []

        with pytest.raises(crypto.ErroDeConfiguracaoDeChaves):
            _migrar(DEPOIS)

        assert _bruto("fiscal_nfse", "xml_nfse", nota.pk) == XML_NFSE  # nada foi perdido
