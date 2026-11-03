"""Cria ou atualiza o schema `bi` (views consolidadas de todas as empresas)."""

from django.core.management.base import BaseCommand

from operacao import bi


class Command(BaseCommand):
    """Idempotente. Rode depois de `migrate_schemas` (o entrypoint do Compose já faz isso)."""

    help = "Cria/atualiza as views do schema bi (notas, serviços, retenções, eventos)."

    def add_arguments(self, parser):
        """Opções."""
        parser.add_argument(
            "--se-existir",
            action="store_true",
            help="Só atualiza se o schema bi já foi criado (não cria nada em instalações sem BI).",
        )

    def handle(self, *args, se_existir, **opcoes):
        """Recria as views."""
        if se_existir and not bi.esquema_existe():
            self.stdout.write("Schema bi não existe: nada a atualizar.")
            return
        quantas = bi.atualizar_views()
        self.stdout.write(self.style.SUCCESS(f"Views de BI atualizadas ({quantas} empresa(s))."))
