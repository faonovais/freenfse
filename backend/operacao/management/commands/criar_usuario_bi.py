"""Cria o usuário de banco SOMENTE LEITURA para BI e libera só o schema `bi`."""

import os
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from operacao import bi


class Command(BaseCommand):
    """A senha vem da variável `FREENFSE_BI_SENHA` ou de `--senha-arquivo`; nunca é impressa."""

    help = "Cria/atualiza o usuário de leitura do BI (senha por FREENFSE_BI_SENHA ou arquivo)."

    def add_arguments(self, parser):
        """Opções."""
        parser.add_argument("--senha-arquivo", help="Arquivo com a senha (uma linha).")

    def handle(self, *args, senha_arquivo, **opcoes):
        """Cria o usuário e atualiza as views."""
        if senha_arquivo:
            try:
                senha = Path(senha_arquivo).read_text(encoding="utf-8").strip()
            except OSError:
                raise CommandError("Não foi possível ler o arquivo da senha.") from None
        else:
            senha = os.environ.get("FREENFSE_BI_SENHA", "")
        if not senha:
            raise CommandError(
                "Informe a senha por --senha-arquivo ou pela variável FREENFSE_BI_SENHA "
                "(mínimo de 16 caracteres)."
            )
        try:
            usuario = bi.criar_usuario_de_leitura(senha)
        except ValueError as erro:
            raise CommandError(str(erro)) from None
        self.stdout.write(
            self.style.SUCCESS(
                f"Usuário '{usuario}' pronto (somente leitura, só o schema bi). "
                "A senha não é exibida."
            )
        )
