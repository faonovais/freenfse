"""Tarefas agendadas de operação (Celery beat)."""

import logging

from celery import shared_task

from operacao import alertas, backup, saude

logger = logging.getLogger(__name__)


@shared_task
def fazer_backup():
    """Backup cifrado diário. Em falha, registra como crítico e deixa a tarefa falhar."""
    try:
        manifesto = backup.fazer_backup(backup.config_do_ambiente())
    except backup.ErroDeBackup as erro:
        logger.critical("Backup do banco falhou.", exc_info=True)
        alertas.alertar_backup_falhou(erro)
        raise
    logger.info("Backup feito: %s (%s bytes).", manifesto["arquivo"], manifesto["tamanho"])
    return manifesto["arquivo"]


@shared_task
def batimento():
    """Marca no Redis que o agendador (beat) e o worker estão vivos (todo minuto)."""
    saude.registrar_batimento()


@shared_task
def verificar_alertas():
    """Alertas operacionais (emissão incerta, falhas, backup atrasado), de hora em hora."""
    return alertas.verificar_alertas()
