"""Configuração do app core."""

from django.apps import AppConfig


class CoreConfig(AppConfig):
    """App core (schema público)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self):
        """Registra os receptores de sinais e as verificações do sistema."""
        from . import checks  # noqa: F401
        from .auth import signals  # noqa: F401
