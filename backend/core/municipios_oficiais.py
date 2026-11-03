"""Conferência do arquivo de municípios com a tabela oficial do IBGE (DTB, Divisão Territorial).

A fonte oficial é o `DTB_<ano>.zip` publicado pelo IBGE em
`geoftp.ibge.gov.br/organizacao_do_territorio/estrutura_territorial/divisao_territorial/<ano>/`,
que traz a planilha `RELATORIO_DTB_BRASIL_<ano>_MUNICIPIOS.ods`. Este módulo **não acessa a rede**:
lê o arquivo já baixado (o procedimento está em `core/dados/LEIAME.md`), compara com o arquivo
versionado e, se pedido, regrava o CSV a partir da fonte oficial.

O XML da planilha é lido sem resolver entidades nem acessar a rede.
"""

import csv
import hashlib
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

from core.municipios import UF_POR_CODIGO, ErroNoArquivoDeMunicipios, ler_arquivo

ESPACO_TABELA = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"
ESPACO_TEXTO = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"
PLANILHA_DE_MUNICIPIOS = "_MUNICIPIOS.ods"
COLUNAS_NECESSARIAS = ("UF", "Código Município Completo", "Nome_Município")
LIMITE_DE_COLUNAS = 64  # as colunas vazias repetidas da planilha não são expandidas além disto


@dataclass
class TabelaOficial:
    """O que se leu da planilha oficial: os municípios, a data-base e o arquivo de origem."""

    municipios: list
    data_base: str
    nome_do_arquivo: str
    sha256_do_arquivo: str
    sha256_da_planilha: str


@dataclass
class Relatorio:
    """Resultado da comparação do arquivo versionado com a tabela oficial."""

    iguais: int = 0
    diferentes: list = field(default_factory=list)  # (codigo, (nome, uf) versionado, oficial)
    faltantes: list = field(default_factory=list)  # só na tabela oficial: (codigo, nome, uf)
    a_mais: list = field(default_factory=list)  # só no arquivo versionado: (codigo, nome, uf)

    @property
    def conferido(self):
        """Verdadeiro quando o arquivo versionado é idêntico à tabela oficial."""
        return not (self.diferentes or self.faltantes or self.a_mais)


def _texto_da_celula(celula):
    return "".join("".join(paragrafo.itertext()) for paragrafo in celula.iter(ESPACO_TEXTO + "p"))


def _linhas_da_planilha(conteudo_xml):
    """Linhas (listas de textos) da primeira planilha do `content.xml` de um `.ods`."""
    leitor = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False)
    raiz = etree.fromstring(conteudo_xml, leitor)
    for linha in raiz.iter(ESPACO_TABELA + "table-row"):
        celulas = []
        for celula in linha:
            if celula.tag not in (
                ESPACO_TABELA + "table-cell",
                ESPACO_TABELA + "covered-table-cell",
            ):
                continue
            repeticoes = int(celula.get(ESPACO_TABELA + "number-columns-repeated", "1"))
            celulas.extend([_texto_da_celula(celula)] * min(repeticoes, LIMITE_DE_COLUNAS))
        yield celulas[:LIMITE_DE_COLUNAS]


def ler_tabela_oficial(caminho):
    """Lê o `DTB_<ano>.zip` (ou a planilha `.ods` solta) e devolve a `TabelaOficial`.

    Levanta `ErroNoArquivoDeMunicipios` se o arquivo não for a planilha de municípios do IBGE ou
    se alguma linha for inconsistente (código fora de 7 dígitos, UF que não bate com o código).
    """
    caminho = Path(caminho)
    bruto = caminho.read_bytes()
    if caminho.suffix.lower() == ".zip":
        with zipfile.ZipFile(caminho) as pacote:
            nomes = [
                n for n in pacote.namelist() if n.upper().endswith(PLANILHA_DE_MUNICIPIOS.upper())
            ]
            if len(nomes) != 1:
                raise ErroNoArquivoDeMunicipios(
                    f"Esperava uma planilha *{PLANILHA_DE_MUNICIPIOS} em {caminho.name}, "
                    f"achei {len(nomes)}."
                )
            planilha = pacote.read(nomes[0])
    else:
        planilha = bruto
    try:
        with zipfile.ZipFile(_em_memoria(planilha)) as ods:
            linhas = list(_linhas_da_planilha(ods.read("content.xml")))
    except (zipfile.BadZipFile, KeyError, etree.XMLSyntaxError) as erro:
        raise ErroNoArquivoDeMunicipios(f"{caminho.name} não é uma planilha .ods válida.") from erro

    cabecalho = next(
        (i for i, linha in enumerate(linhas) if all(c in linha for c in COLUNAS_NECESSARIAS)), None
    )
    if cabecalho is None:
        raise ErroNoArquivoDeMunicipios(
            f"Não achei o cabeçalho {COLUNAS_NECESSARIAS} na planilha de {caminho.name}."
        )
    posicao = {nome: linhas[cabecalho].index(nome) for nome in COLUNAS_NECESSARIAS}
    data_base = next(
        (c.split(":", 1)[1].strip() for linha in linhas[:cabecalho] for c in linha[:1]
         if c.upper().startswith("DATA BASE")),
        "",
    )  # fmt: skip
    municipios, vistos = [], set()
    for numero, linha in enumerate(linhas[cabecalho + 1 :], start=cabecalho + 2):
        if len(linha) <= max(posicao.values()) or not linha[posicao["Código Município Completo"]]:
            continue
        codigo = linha[posicao["Código Município Completo"]].strip()
        nome = linha[posicao["Nome_Município"]].strip()
        codigo_uf = linha[posicao["UF"]].strip()
        if len(codigo) != 7 or not codigo.isdigit() or not nome:
            raise ErroNoArquivoDeMunicipios(f"Linha {numero} da planilha: {codigo!r}/{nome!r}.")
        if codigo[:2] != codigo_uf or codigo_uf not in UF_POR_CODIGO:
            raise ErroNoArquivoDeMunicipios(
                f"Linha {numero} da planilha: a UF {codigo_uf!r} não bate com o código {codigo}."
            )
        if codigo in vistos:
            raise ErroNoArquivoDeMunicipios(
                f"Linha {numero} da planilha: código repetido {codigo}."
            )
        vistos.add(codigo)
        municipios.append((codigo, nome, UF_POR_CODIGO[codigo_uf]))
    municipios.sort()
    return TabelaOficial(
        municipios=municipios,
        data_base=data_base,
        nome_do_arquivo=caminho.name,
        sha256_do_arquivo=hashlib.sha256(bruto).hexdigest(),
        sha256_da_planilha=hashlib.sha256(planilha).hexdigest(),
    )


def _em_memoria(conteudo):
    from io import BytesIO

    return BytesIO(conteudo)


def comparar(versionado, oficial):
    """Compara duas listas de `(codigo, nome, uf)` e devolve o `Relatorio`.

    "Igual" exige código, nome e UF idênticos; o mesmo código com nome ou UF diferente é
    "diferente"; o que só existe de um lado é "faltante" (só no oficial) ou "a mais".
    """
    relatorio = Relatorio()
    a_mao = {codigo: (nome, uf) for codigo, nome, uf in versionado}
    oficiais = {codigo: (nome, uf) for codigo, nome, uf in oficial}
    for codigo in sorted(set(a_mao) | set(oficiais)):
        if codigo in a_mao and codigo in oficiais:
            if a_mao[codigo] == oficiais[codigo]:
                relatorio.iguais += 1
            else:
                relatorio.diferentes.append((codigo, a_mao[codigo], oficiais[codigo]))
        elif codigo in oficiais:
            relatorio.faltantes.append((codigo, *oficiais[codigo]))
        else:
            relatorio.a_mais.append((codigo, *a_mao[codigo]))
    return relatorio


def comparar_com_o_arquivo_versionado(oficial, caminho=None):
    """Compara a tabela oficial com o CSV versionado (ou com o `caminho` informado)."""
    return comparar(ler_arquivo(caminho), oficial.municipios)


def gravar_csv(municipios, destino):
    """Grava `codigo_ibge,nome,uf` (UTF-8, LF), em ordem de código, como o arquivo versionado."""
    with Path(destino).open("w", encoding="utf-8", newline="") as saida:
        escritor = csv.writer(saida, lineterminator="\n")
        escritor.writerow(["codigo_ibge", "nome", "uf"])
        escritor.writerows(sorted(municipios))
    return hashlib.sha256(Path(destino).read_bytes()).hexdigest()
