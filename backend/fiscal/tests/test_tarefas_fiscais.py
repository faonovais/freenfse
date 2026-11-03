"""Tarefas Celery da emissão: reagendamento quando a trava está ocupada e rotina periódica."""

import pytest
from django.conf import settings

from fiscal import gateway, tasks
from fiscal.models import Nfse
from fiscal.services import emissao

pytestmark = pytest.mark.django_db
S = Nfse.Situacao


class Reagendada(Exception):
    """Marca que a tarefa pediu para ser executada de novo."""


def test_a_tarefa_envia_a_nota_e_e_idempotente(empresa_pronta, nova_nota, sefin):
    nota = nova_nota()
    emissao.solicitar_emissao(nota, usuario=None, empresa=empresa_pronta)

    primeiro = tasks.emitir_nfse.run(empresa_pronta.schema_name, nota.pk)
    segundo = tasks.emitir_nfse.run(empresa_pronta.schema_name, nota.pk)  # reentrega do Celery

    assert primeiro == segundo == S.AUTORIZADA
    assert sefin.total_de_posts == 1


def test_trava_ocupada_reagenda_a_tarefa_sem_consumir_a_nota(empresa_a, monkeypatch):
    pedidos = []

    def trava_ocupada(empresa, nfse_id):
        raise gateway.TravaOcupadaErro("há outra emissão em andamento")

    def reagendar(exc=None, countdown=None, **_):
        pedidos.append(countdown)
        raise Reagendada

    monkeypatch.setattr(emissao, "executar_emissao", trava_ocupada)
    monkeypatch.setattr(tasks.emitir_nfse, "retry", reagendar)

    with pytest.raises(Reagendada):
        tasks.emitir_nfse.run(empresa_a.schema_name, 123)

    assert pedidos == [tasks.TEMPO_ENTRE_TENTATIVAS_DA_TRAVA]


def test_a_tarefa_de_emissao_confirma_so_depois_de_terminar():
    assert tasks.emitir_nfse.acks_late is True  # queda do worker = a tarefa volta para a fila
    assert tasks.emitir_nfse.max_retries == tasks.TENTATIVAS_DA_TRAVA


def test_a_rotina_periodica_esta_agendada_e_so_consulta(empresa_pronta, nova_nota, sefin):
    agendamento = settings.CELERY_BEAT_SCHEDULE["reconciliar-notas-incertas"]
    assert agendamento["task"] == "fiscal.tasks.reconciliar_notas_incertas"

    sefin.proximas("cai_depois_de_processar")
    nota = nova_nota()
    emissao.solicitar_emissao(nota, usuario=None, empresa=empresa_pronta)
    emissao.executar_emissao(empresa_pronta, nota.pk)
    sefin.fora_do_ar = False

    resumo = tasks.reconciliar_notas_incertas.run()

    assert resumo["autorizadas"] == 1 and resumo["empresas"] >= 1
    assert sefin.total_de_posts == 1
