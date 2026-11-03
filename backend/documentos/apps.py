"""Configuração do app documentos."""

from django.apps import AppConfig


class DocumentosConfig(AppConfig):
    """App documentos (executa no schema de cada empresa)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "documentos"

    def ready(self):
        """Registra as permissões e liga os receptores dos sinais fiscais."""
        from documentos import permissoes, receptores  # noqa: F401
