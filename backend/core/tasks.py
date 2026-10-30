"""Tarefas Celery do app core."""

from celery import shared_task


@shared_task
def ping():
    """Tarefa mínima para verificar que o worker consome a fila."""
    return "pong"
