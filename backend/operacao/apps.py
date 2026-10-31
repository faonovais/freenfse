"""App de operação: backup, saúde, retenção, alertas e views para BI (Fase 6)."""

from django.apps import AppConfig


class OperacaoConfig(AppConfig):
    """Não tem tabelas próprias: só serviços, comandos e tarefas agendadas."""

    name = "operacao"
    verbose_name = "operação"
