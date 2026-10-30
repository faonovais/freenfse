"""Gera uma chave de criptografia nova."""

from django.core.management.base import BaseCommand

from core import crypto


class Command(BaseCommand):
    """Imprime uma chave AES-256 aleatória para usar em `FREENFSE_CHAVES`."""

    help = "Gera uma chave de criptografia (32 bytes em base64 URL-safe) para FREENFSE_CHAVES."

    def handle(self, *args, **opcoes):
        """Imprime só a chave, para ser usada em scripts."""
        self.stdout.write(crypto.gerar_chave())
