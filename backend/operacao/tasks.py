"""Tarefas agendadas de operação (Celery beat)."""

import logging

from celery import shared_task

from operacao import backup

logger = logging.getLogger(__name__)


@shared_task
def fazer_backup():
    """Backup cifrado diário. Em falha, registra como crítico e deixa a tarefa falhar."""
    try:
        manifesto = backup.fazer_backup(backup.config_do_ambiente())
    except backup.ErroDeBackup:
        logger.critical("Backup do banco falhou.", exc_info=True)
        raise
    logger.info("Backup feito: %s (%s bytes).", manifesto["arquivo"], manifesto["tamanho"])
    return manifesto["arquivo"]
