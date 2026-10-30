"""Configuração do app de apoio aos testes."""

from django.apps import AppConfig


class ApoioTestesConfig(AppConfig):
    """App de apoio aos testes (executa no schema de cada empresa)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apoio_testes"
