"""Restaura um backup cifrado num banco NOVO e confere o resultado."""

from django.core.management.base import BaseCommand, CommandError

from operacao import backup


class Command(BaseCommand):
    """Nunca sobrescreve um banco: cria `--destino`, restaura, confere e comenta o resultado."""

    help = (
        "Restaura um backup (.dump.age) num banco novo, com a chave privada age informada, e "
        "confere linhas por tabela e a leitura dos campos cifrados com a FREENFSE_CHAVES atual."
    )

    def add_arguments(self, parser):
        """Argumentos do comando."""
        parser.add_argument("arquivo", help="Caminho do arquivo .dump.age (o .json fica ao lado).")
        parser.add_argument(
            "--identidade", required=True, help="Arquivo da chave privada age (fora do servidor)."
        )
        parser.add_argument(
            "--destino", required=True, help="Nome do banco NOVO que será criado e preenchido."
        )

    def handle(self, *args, arquivo, identidade, destino, **opcoes):
        """Restaura, confere e resume o resultado."""
        config = backup.config_do_ambiente()
        try:
            resumo = backup.restaurar_backup(
                config, arquivo, identidade=identidade, destino=destino
            )
        except backup.ErroDeRestauracao as erro:
            raise CommandError(str(erro)) from None
        self.stdout.write(
            self.style.SUCCESS(
                f"Restauração verificada no banco '{resumo['banco']}': "
                f"{resumo['tabelas']} tabelas, {resumo['linhas']} linhas, "
                f"{resumo['campos_cifrados_conferidos']} valores cifrados abertos com a "
                "FREENFSE_CHAVES atual."
            )
        )
