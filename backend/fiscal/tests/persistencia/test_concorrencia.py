"""Concorrência real: threads com conexões distintas ao PostgreSQL, sem simulação.

Estes testes são a prova de que a numeração nunca repete e de que a trava exclui de fato. Cada
um tem uma mutação correspondente (documentada na verificação da fase): sem o `FOR UPDATE`, o
primeiro falha; sem a trava, o segundo falha.
"""

import threading
import time

import pytest
from django.db import connection
from freedfe.excecoes import SincronizacaoEmAndamentoErro

from fiscal.persistencia.estado_emissao import EstadoEmissaoPostgres
from fiscal.persistencia.modelos import EmissaoDps
from fiscal.persistencia.trava import TravaPostgres
from fiscal.tests.persistencia.apoio_threads import executar_em_paralelo
from fiscal.tests.persistencia.contrato_estado_emissao import SERIE, montar_id

pytestmark = pytest.mark.django_db(transaction=True)

PARALELAS = 12


def _montar_devagar(numero):
    """Alarga a janela entre escolher o número e gravá-lo: sem o cadeado, todos colidem."""
    time.sleep(0.05)
    return montar_id(numero)


def test_reservas_paralelas_na_mesma_serie_geram_numeros_distintos_e_sem_lacuna(
    empresas_confirmadas,
):
    alfa, _ = empresas_confirmadas

    def reservar():
        return EstadoEmissaoPostgres().reservar_proximo(SERIE, _montar_devagar).numero

    numeros, erros = executar_em_paralelo([(alfa.schema_name, reservar)] * PARALELAS)

    assert erros == [None] * PARALELAS
    assert sorted(numeros) == list(range(1, PARALELAS + 1))
    assert EmissaoDps.objects.none().count() == 0  # a conexão do teste está no schema público


def test_as_empresas_numeram_em_paralelo_sem_interferir(empresas_confirmadas):
    alfa, beta = empresas_confirmadas

    def reservar():
        return EstadoEmissaoPostgres().reservar_proximo(SERIE, _montar_devagar).numero

    tarefas = [(alfa.schema_name, reservar)] * 6 + [(beta.schema_name, reservar)] * 6
    numeros, erros = executar_em_paralelo(tarefas)

    assert erros == [None] * 12
    assert sorted(numeros[:6]) == [1, 2, 3, 4, 5, 6]
    assert sorted(numeros[6:]) == [1, 2, 3, 4, 5, 6]


def test_a_trava_exclui_de_fato_duas_operacoes_da_mesma_empresa(empresas_confirmadas):
    alfa, _ = empresas_confirmadas
    dentro = []
    simultaneas = []
    cadeado = threading.Lock()

    def operacao():
        with TravaPostgres("emissao_nfse", espera_segundos=30):
            with cadeado:
                dentro.append(1)
                simultaneas.append(len(dentro))
            time.sleep(0.15)
            with cadeado:
                dentro.pop()

    _, erros = executar_em_paralelo([(alfa.schema_name, operacao)] * 5)

    assert erros == [None] * 5
    assert max(simultaneas) == 1  # nunca duas operações ao mesmo tempo dentro da trava


def test_travas_de_empresas_diferentes_nao_se_bloqueiam(empresas_confirmadas):
    alfa, beta = empresas_confirmadas
    juntas = threading.Barrier(2, timeout=10)

    def operacao():
        with TravaPostgres("emissao_nfse", espera_segundos=0):
            juntas.wait()  # só passa se as duas estiverem dentro da trava ao mesmo tempo

    _, erros = executar_em_paralelo([(alfa.schema_name, operacao), (beta.schema_name, operacao)])

    assert erros == [None, None]


def test_quem_nao_espera_falha_de_imediato_com_a_mensagem_da_biblioteca(empresas_confirmadas):
    alfa, _ = empresas_confirmadas
    ocupada = threading.Event()
    liberar = threading.Event()

    def segurar():
        with TravaPostgres("emissao_nfse"):
            ocupada.set()
            liberar.wait(timeout=20)

    def tentar():
        ocupada.wait(timeout=20)
        try:
            with TravaPostgres("emissao_nfse", espera_segundos=0):
                pass
        finally:
            liberar.set()

    _, erros = executar_em_paralelo([(alfa.schema_name, segurar), (alfa.schema_name, tentar)])

    assert erros[0] is None
    assert isinstance(erros[1], SincronizacaoEmAndamentoErro)
    assert "outra operação fiscal" in str(erros[1])


def test_a_trava_e_liberada_quando_a_sessao_morre(empresas_confirmadas):
    """Processo que cai não deixa trava abandonada: o PostgreSQL derruba a sessão."""
    alfa, _ = empresas_confirmadas
    from django_tenants.utils import schema_context

    with schema_context(alfa.schema_name):
        trava = TravaPostgres("emissao_nfse")
        trava.__enter__()
        pid = trava._conexao.connection.info.backend_pid
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_terminate_backend(%s)", [pid])
        # A sessão caiu sem liberar: outra operação já consegue a trava.
        with TravaPostgres("emissao_nfse", espera_segundos=0):
            pass
        trava._fechar()
