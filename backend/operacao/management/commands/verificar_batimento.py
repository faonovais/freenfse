"""Sonda do agendador (beat): sai com erro se o batimento do beat está velho ou ausente."""

from django.core.management.base import BaseCommand, CommandError

from operacao import saude


class Command(BaseCommand):
    """Usada no `healthcheck` do contêiner do beat (pendência da issue #10)."""

    help = "Falha (código 1) se o agendador não bateu nos últimos N segundos."

    def add_arguments(self, parser):
        """Idade máxima aceita."""
        parser.add_argument(
            "--max-idade",
            type=int,
            default=saude.IDADE_MAXIMA_DO_BATIMENTO,
            help="Segundos desde o último batimento (padrão: %(default)s).",
        )

    def handle(self, *args, max_idade, **opcoes):
        """Confere o batimento gravado no Redis."""
        try:
            idade = saude.idade_do_batimento()
        except Exception:
            raise CommandError("Não foi possível ler o batimento (Redis fora do ar?).") from None
        if idade is None:
            raise CommandError("O agendador ainda não bateu (ou parou há mais de 10 minutos).")
        if idade > max_idade:
            raise CommandError(f"O último batimento do agendador foi há {int(idade)} s.")
        self.stdout.write(f"Agendador ok (último batimento há {int(idade)} s).")
