"""Municípios: constantes e leitura do arquivo versionado do IBGE (ver `core/dados/LEIAME.md`)."""

import csv
from pathlib import Path

ARQUIVO_PADRAO = Path(__file__).resolve().parent / "dados" / "municipios_ibge.csv"

# Código IBGE da UF (2 primeiros dígitos do município) → sigla.
UF_POR_CODIGO = {
    "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP", "17": "TO",
    "21": "MA", "22": "PI", "23": "CE", "24": "RN", "25": "PB", "26": "PE", "27": "AL",
    "28": "SE", "29": "BA", "31": "MG", "32": "ES", "33": "RJ", "35": "SP", "41": "PR",
    "42": "SC", "43": "RS", "50": "MS", "51": "MT", "52": "GO", "53": "DF",
}  # fmt: skip


class ErroNoArquivoDeMunicipios(ValueError):
    """O arquivo de municípios está malformado ou inconsistente."""


def ler_arquivo(caminho=None):
    """Lê e valida o arquivo; devolve uma lista de `(codigo, nome, uf)` em ordem de código.

    Não exige o dígito verificador do código IBGE: o próprio IBGE atribuiu 9 códigos fora da
    regra (ver o LEIAME), então rejeitá-los excluiria municípios reais.
    """
    caminho = Path(caminho) if caminho else ARQUIVO_PADRAO
    with caminho.open(encoding="utf-8", newline="") as entrada:
        leitor = csv.DictReader(entrada)
        if leitor.fieldnames != ["codigo_ibge", "nome", "uf"]:
            raise ErroNoArquivoDeMunicipios(
                f"Cabeçalho inesperado em {caminho.name}: {leitor.fieldnames}."
            )
        linhas, vistos = [], set()
        for numero, linha in enumerate(leitor, start=2):
            codigo, nome, uf = linha["codigo_ibge"], linha["nome"].strip(), linha["uf"]
            if len(codigo) != 7 or not codigo.isdigit():
                raise ErroNoArquivoDeMunicipios(
                    f"Linha {numero}: código IBGE inválido: {codigo!r}."
                )
            if codigo in vistos:
                raise ErroNoArquivoDeMunicipios(f"Linha {numero}: código repetido: {codigo}.")
            if UF_POR_CODIGO.get(codigo[:2]) != uf:
                raise ErroNoArquivoDeMunicipios(
                    f"Linha {numero}: a UF {uf!r} não corresponde ao código {codigo}."
                )
            if not nome:
                raise ErroNoArquivoDeMunicipios(f"Linha {numero}: nome vazio.")
            vistos.add(codigo)
            linhas.append((codigo, nome, uf))
    return linhas
