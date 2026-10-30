"""Configuração do app core."""

from django.apps import AppConfig


class CoreConfig(AppConfig):
    """App core (schema público)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
