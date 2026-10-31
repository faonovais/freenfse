"""Dispatcher com várias instâncias ao mesmo tempo (threads e conexões reais) e vários schemas.

Duas instâncias do beat, ou a tarefa entregue duas vezes, não podem gerar dois rascunhos para a
mesma data. As conexões são de verdade (`transactional_db`): só enxergam o que foi confirmado.
"""

import threading

import pytest
from django.db import connections
from django_tenants.utils import schema_context

from agendamentos import tasks
from agendamentos.models import ExecucaoAgendamento
from agendamentos.services import agenda, modelos
from agendamentos.tests.apoio import criar_agendamento, criar_modelo, criar_usuario, utc
from fiscal.models import Nfse
from fiscal.tests.persistencia.apoio_threads import executar_em_paralelo

pytestmark = pytest.mark.django_db(transaction=True)
CRIACAO = utc("2026-11-01T12:00")
AGORA = utc("2026-11-05T11:01")  # depois das 08:00 de Brasília de 05/11


def preparar(empresa, email="resp@exemplo.test"):
    """Modelo, responsável e um agendamento mensal vencido em `AGORA`; devolve o id dele."""
    with schema_context(empresa.schema_name):
        responsavel = criar_usuario(email, empresa)
        return criar_agendamento(criar_modelo(), responsavel, agora=CRIACAO).pk


def totais_do_schema(empresa):
    with schema_context(empresa.schema_name):
        return {
            "notas": Nfse.objects.count(),
            "execucoes": ExecucaoAgendamento.objects.count(),
            "agendamentos": list(
                ExecucaoAgendamento.objects.values_list(
                    "agendamento__execucoes_realizadas", flat=True
                )
            ),
        }


def test_varias_instancias_ao_mesmo_tempo_geram_um_unico_rascunho(empresas_confirmadas):
    alfa, _beta = empresas_confirmadas
    preparar(alfa)

    resultados, erros = executar_em_paralelo(
        [(alfa.schema_name, lambda: agenda.despachar(AGORA, empresa=alfa))] * 5
    )

    assert erros == [None] * 5
    assert sum(r[agenda.GERADA] for r in resultados) == 1  # só uma instância gerou
    assert totais_do_schema(alfa) == {"notas": 1, "execucoes": 1, "agendamentos": [1]}


def test_a_segunda_instancia_pula_em_vez_de_esperar_a_primeira(empresas_confirmadas, monkeypatch):
    alfa, _beta = empresas_confirmadas
    agendamento_id = preparar(alfa)
    dentro, liberar = threading.Event(), threading.Event()
    original = modelos.gerar_rascunho

    def lenta(*args, **kwargs):  # a primeira instância fica "no meio" da geração
        dentro.set()
        assert liberar.wait(30), "o teste não liberou a primeira instância"
        return original(*args, **kwargs)

    monkeypatch.setattr(modelos, "gerar_rascunho", lenta)
    saidas = {}

    def instancia(nome):
        try:
            with schema_context(alfa.schema_name):
                saidas[nome] = agenda.processar(agendamento_id, agora=AGORA, empresa=alfa)
        except BaseException as erro:  # noqa: BLE001 - o teste confere o que aconteceu
            saidas[nome] = erro
        finally:
            connections.close_all()

    primeira = threading.Thread(target=instancia, args=("primeira",), daemon=True)
    segunda = threading.Thread(target=instancia, args=("segunda",), daemon=True)
    primeira.start()
    assert dentro.wait(30)
    segunda.start()
    segunda.join(10)
    try:
        assert not segunda.is_alive(), "a segunda instância esperou a primeira: falta a trava"
        assert saidas["segunda"] is None  # pulou: já há alguém executando esta data
    finally:
        liberar.set()
        primeira.join(30)
        segunda.join(30)

    assert saidas["primeira"] == agenda.GERADA
    assert totais_do_schema(alfa) == {"notas": 1, "execucoes": 1, "agendamentos": [1]}


def test_o_beat_varre_cada_empresa_no_seu_schema_sem_misturar(empresas_confirmadas, monkeypatch):
    alfa, beta = empresas_confirmadas
    preparar(alfa, "resp-alfa@exemplo.test")
    preparar(beta, "resp-beta@exemplo.test")
    with schema_context(beta.schema_name):  # um tomador diferente em cada empresa
        from cadastros.models import Pessoa

        Pessoa.objects.update(nome="TOMADOR DA BETA LTDA")
    monkeypatch.setattr(tasks.timezone, "now", lambda: AGORA)

    totais = tasks.despachar_agendamentos()

    assert totais[alfa.schema_name][agenda.GERADA] == 1
    assert totais[beta.schema_name][agenda.GERADA] == 1
    for empresa, tomador, responsavel in (
        (alfa, "TOMADOR FICTICIO LTDA", "resp-alfa@exemplo.test"),
        (beta, "TOMADOR DA BETA LTDA", "resp-beta@exemplo.test"),
    ):
        with schema_context(empresa.schema_name):
            nota = Nfse.objects.get()
            assert (nota.tomador_nome, nota.criado_por_email) == (tomador, responsavel)
            assert ExecucaoAgendamento.objects.get().nfse == nota


def test_falha_numa_empresa_nao_para_as_outras(empresas_confirmadas, monkeypatch):
    alfa, beta = empresas_confirmadas
    preparar(alfa, "resp-alfa@exemplo.test")
    preparar(beta, "resp-beta@exemplo.test")
    monkeypatch.setattr(tasks.timezone, "now", lambda: AGORA)
    original = agenda.despachar

    def quebra_na_alfa(agora, *, empresa):
        if empresa.pk == alfa.pk:
            raise RuntimeError("falha simulada na empresa alfa")
        return original(agora, empresa=empresa)

    monkeypatch.setattr(agenda, "despachar", quebra_na_alfa)

    totais = tasks.despachar_agendamentos()

    assert alfa.schema_name not in totais
    assert totais[beta.schema_name][agenda.GERADA] == 1
    assert totais_do_schema(alfa)["notas"] == 0 and totais_do_schema(beta)["notas"] == 1
