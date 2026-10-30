"""Carrega (ou atualiza) a tabela de municípios a partir do arquivo versionado do IBGE."""

from django.core.management.base import BaseCommand, CommandError

from core.models import Municipio
from core.municipios import ErroNoArquivoDeMunicipios, ler_arquivo


class Command(BaseCommand):
    """Importa `core/dados/municipios_ibge.csv` de forma idempotente."""

    help = "Carrega os municípios do IBGE (arquivo versionado em core/dados) no schema público."

    def add_arguments(self, parser):
        """Permite apontar para outro arquivo (mesmo formato) e só validar."""
        parser.add_argument(
            "--arquivo", help="Caminho de um CSV alternativo (codigo_ibge,nome,uf)."
        )
        parser.add_argument(
            "--verificar", action="store_true", help="Só valida o arquivo, sem gravar no banco."
        )

    def handle(self, *args, **opcoes):
        """Valida o arquivo e faz o upsert dos municípios."""
        try:
            linhas = ler_arquivo(opcoes["arquivo"])
        except (ErroNoArquivoDeMunicipios, OSError) as erro:
            raise CommandError(str(erro)) from erro
        if opcoes["verificar"]:
            self.stdout.write(f"Arquivo válido: {len(linhas)} municípios.")
            return
        antes = Municipio.objects.count()
        Municipio.objects.bulk_create(
            [Municipio(codigo=codigo, nome=nome, uf=uf) for codigo, nome, uf in linhas],
            update_conflicts=True,
            unique_fields=["codigo"],
            update_fields=["nome", "uf"],
            batch_size=1000,
        )
        depois = Municipio.objects.count()
        self.stdout.write(
            f"Municípios: {depois} no banco ({depois - antes} novos, {len(linhas)} no arquivo)."
        )
