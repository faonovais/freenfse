"""Tarefas agendadas do app fiscal."""

from celery import shared_task

from fiscal.services import vencimento


@shared_task
def verificar_vencimento_certificados():
    """Gera os alertas de vencimento (30/15/7 dias e vencido) de todas as empresas.

    Roda uma vez por dia (ver `CELERY_BEAT_SCHEDULE`). Devolve quantos alertas novos criou.
    """
    return len(vencimento.verificar_certificados())
