"""Configuração do app cadastros."""

from django.apps import AppConfig


class CadastrosConfig(AppConfig):
    """App cadastros (executa no schema de cada empresa)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "cadastros"
