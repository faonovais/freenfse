"""Configuração do app fiscal."""

from django.apps import AppConfig


class FiscalConfig(AppConfig):
    """App fiscal (executa no schema de cada empresa)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "fiscal"
