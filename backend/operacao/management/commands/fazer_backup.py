"""Faz o backup cifrado do banco inteiro (todos os schemas) agora."""

import dataclasses
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from operacao import backup


class Command(BaseCommand):
    """O mesmo código da tarefa agendada, para uso manual ou por cron/systemd timer."""

    help = "Faz um backup cifrado (age) do banco inteiro e aplica a retenção."

    def add_arguments(self, parser):
        """Opções que sobrescrevem a configuração do ambiente."""
        parser.add_argument("--pasta", help="Pasta dos backups (padrão: FREENFSE_BACKUP_DIR).")
        parser.add_argument(
            "--retencao-dias",
            type=int,
            help="Dias de retenção (padrão: FREENFSE_BACKUP_RETENCAO_DIAS).",
        )

    def handle(self, *args, pasta, retencao_dias, **opcoes):
        """Executa o backup e resume o resultado, sem imprimir nenhum segredo."""
        config = backup.config_do_ambiente()
        if pasta:
            config = dataclasses.replace(config, pasta=Path(pasta))
        if retencao_dias:
            config = dataclasses.replace(config, retencao_dias=retencao_dias)
        try:
            manifesto = backup.fazer_backup(config)
        except backup.ErroDeBackup as erro:
            raise CommandError(str(erro)) from None
        self.stdout.write(
            self.style.SUCCESS(
                f"Backup feito: {manifesto['arquivo']} ({manifesto['tamanho']} bytes, "
                f"{len(manifesto['tabelas'])} tabelas em {len(manifesto['esquemas'])} schemas)."
            )
        )
