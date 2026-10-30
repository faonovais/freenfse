"""Configuração do app agendamentos."""

from django.apps import AppConfig


class AgendamentosConfig(AppConfig):
    """App agendamentos (executa no schema de cada empresa)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "agendamentos"
