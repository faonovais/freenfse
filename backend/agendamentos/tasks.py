"""Tarefas Celery dos agendamentos: o dispatcher único e o alerta diário (todas as empresas)."""

import logging

from celery import shared_task
from django.utils import timezone
from django_tenants.utils import schema_context

logger = logging.getLogger(__name__)


def _por_empresa(funcao, agora):
    """Rode `funcao(agora, empresa)` no schema de cada empresa ativa; falha não para as outras."""
    from core.models import Empresa

    resultados = {}
    for empresa in Empresa.objects.filter(ativo=True):
        try:
            with schema_context(empresa.schema_name):
                resultados[empresa.schema_name] = funcao(agora, empresa=empresa)
        except Exception:
            logger.exception("Agendamentos: falha na empresa %s.", empresa.schema_name)
    return resultados


@shared_task
def despachar_agendamentos():
    """Gera os rascunhos das datas vencidas de todas as empresas (a cada minuto, pelo beat).

    É seguro rodar duas vezes ao mesmo tempo (duas instâncias do beat, reentrega da tarefa): cada
    data gera no máximo um rascunho. Devolve os totais por empresa.
    """
    from agendamentos.services import agenda

    return _por_empresa(agenda.despachar, timezone.now())


@shared_task
def alertar_rascunhos_pendentes():
    """Manda a cada responsável o alerta diário dos rascunhos agendados que esperam aprovação."""
    from agendamentos.services import agenda

    return _por_empresa(agenda.alertar_rascunhos_pendentes, timezone.now())
