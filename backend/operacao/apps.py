"""App de operação: backup, saúde, retenção, alertas e views para BI (Fase 6)."""

from django.apps import AppConfig


class OperacaoConfig(AppConfig):
    """Não tem tabelas próprias: só serviços, comandos e tarefas agendadas."""

    name = "operacao"
    verbose_name = "operação"

    def ready(self):
        """Mantém as views de BI em dia quando nasce uma empresa (só se o schema `bi` existe)."""
        from django_tenants.signals import post_schema_sync

        post_schema_sync.connect(
            _ao_criar_empresa, dispatch_uid="operacao.atualizar_views_de_bi_ao_criar_empresa"
        )


def _ao_criar_empresa(sender, tenant=None, **_):
    from operacao import bi

    bi.atualizar_views_se_existirem()
