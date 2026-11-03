"""Compara o arquivo de municípios versionado com a tabela oficial do IBGE (DTB) já baixada."""

from django.core.management.base import BaseCommand, CommandError

from core.municipios import ARQUIVO_PADRAO, ErroNoArquivoDeMunicipios
from core.municipios_oficiais import (
    comparar_com_o_arquivo_versionado,
    gravar_csv,
    ler_tabela_oficial,
)


class Command(BaseCommand):
    """Relatório de iguais, diferentes, faltantes e a mais; com `--gravar`, corrige o CSV."""

    help = (
        "Compara core/dados/municipios_ibge.csv com o DTB_<ano>.zip oficial do IBGE (sem rede: "
        "baixe o arquivo antes; ver core/dados/LEIAME.md)."
    )

    def add_arguments(self, parser):
        """Recebe o arquivo oficial e, opcionalmente, pede para regravar o CSV."""
        parser.add_argument("arquivo", help="Caminho do DTB_<ano>.zip (ou da planilha .ods).")
        parser.add_argument(
            "--gravar",
            action="store_true",
            help="Regrava o CSV versionado com os dados oficiais (corrige e inclui o que faltar).",
        )
        parser.add_argument("--destino", help="CSV de saída do --gravar (padrão: o versionado).")
        parser.add_argument("--max", type=int, default=50, help="Quantas diferenças listar.")

    def handle(self, *args, **opcoes):
        """Lê a tabela oficial, imprime o relatório e, com `--gravar`, atualiza o CSV."""
        try:
            oficial = ler_tabela_oficial(opcoes["arquivo"])
            relatorio = comparar_com_o_arquivo_versionado(oficial)
        except (ErroNoArquivoDeMunicipios, OSError) as erro:
            raise CommandError(str(erro)) from erro
        escrever = self.stdout.write
        escrever(f"Origem: {oficial.nome_do_arquivo} (data-base {oficial.data_base or '?'})")
        escrever(f"SHA-256 do arquivo: {oficial.sha256_do_arquivo}")
        escrever(f"SHA-256 da planilha: {oficial.sha256_da_planilha}")
        escrever(f"Municípios na tabela oficial: {len(oficial.municipios)}")
        escrever(f"Iguais: {relatorio.iguais}")
        escrever(f"Diferentes (nome ou UF): {len(relatorio.diferentes)}")
        escrever(f"Faltantes no arquivo versionado: {len(relatorio.faltantes)}")
        escrever(f"A mais no arquivo versionado: {len(relatorio.a_mais)}")
        for codigo, atual, certo in relatorio.diferentes[: opcoes["max"]]:
            escrever(f"  DIFERENTE {codigo}: {atual[0]}/{atual[1]} -> {certo[0]}/{certo[1]}")
        for codigo, nome, uf in relatorio.faltantes[: opcoes["max"]]:
            escrever(f"  FALTA {codigo}: {nome}/{uf}")
        for codigo, nome, uf in relatorio.a_mais[: opcoes["max"]]:
            escrever(f"  A MAIS {codigo}: {nome}/{uf}")
        if relatorio.conferido:
            escrever("O arquivo versionado confere com a tabela oficial.")
        if opcoes["gravar"]:
            destino = opcoes["destino"] or ARQUIVO_PADRAO
            sha = gravar_csv(oficial.municipios, destino)
            escrever(f"CSV gravado em {destino}. SHA-256: {sha}")
