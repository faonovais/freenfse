"""Configuração do app documentos."""

from django.apps import AppConfig


class DocumentosConfig(AppConfig):
    """App documentos (executa no schema de cada empresa)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "documentos"
