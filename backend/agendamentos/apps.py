"""Configuração do app agendamentos."""

from django.apps import AppConfig


class AgendamentosConfig(AppConfig):
    """App agendamentos (executa no schema de cada empresa)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "agendamentos"

    def ready(self):
        """Registra as permissões e a sobreposição de e-mail por modelo de NFS-e (D21)."""
        from agendamentos import permissoes  # noqa: F401
        from agendamentos.services import modelos
        from documentos.services import envio_email

        envio_email.registrar_sobreposicao(modelos.sobreposicao_de_email)
