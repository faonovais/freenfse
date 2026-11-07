"""Leitor mínimo de planilhas `.xlsx` (só a biblioteca padrão), com expansão de células mescladas.

Os anexos técnicos da NFS-e (Anexos VI, VII e VIII da NT 009) são publicados em `.xlsx`, e o
Anexo VIII guarda as associações (item × NBS × INDOP × cClassTrib) em **células mescladas**:
o valor está só na célula do canto e vale para todo o intervalo. Ler linha a linha perderia essas
associações, por isso `grade(..., expandir_mesclagens=True)` repete o valor em cada célula coberta.

O arquivo vem da internet: o tamanho é limitado e o XML é lido sem resolver entidades externas
(o `xml.etree` da biblioteca padrão não as resolve).
"""

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
NS_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
TAMANHO_MAXIMO_DO_ARQUIVO = 20 * 1024 * 1024
TAMANHO_MAXIMO_DESCOMPACTADO = 200 * 1024 * 1024


class ErroDePlanilha(Exception):
    """Planilha ilegível, grande demais ou fora do formato esperado."""


def _indice_da_coluna(referencia):
    """Índice da coluna de uma referência (`AB12`): `A` é 0, `B` é 1, `AA` é 26."""
    letras = re.match(r"[A-Z]+", referencia).group(0)
    numero = 0
    for letra in letras:
        numero = numero * 26 + (ord(letra) - 64)
    return numero - 1


def _numero_da_linha(referencia):
    return int(re.search(r"\d+", referencia).group(0))


class Planilha:
    """Um `.xlsx` aberto: nomes das abas e o conteúdo de cada uma."""

    def __init__(self, caminho):
        """Abre e valida o arquivo; levanta `ErroDePlanilha` se não for um `.xlsx` aceitável."""
        caminho = Path(caminho)
        try:
            if caminho.stat().st_size > TAMANHO_MAXIMO_DO_ARQUIVO:
                raise ErroDePlanilha("A planilha é grande demais para ser um anexo oficial.")
            self._zip = zipfile.ZipFile(caminho)
        except (OSError, zipfile.BadZipFile) as erro:
            raise ErroDePlanilha(f"Não foi possível abrir {caminho.name}: {erro}") from None
        descompactado = sum(item.file_size for item in self._zip.infolist())
        if descompactado > TAMANHO_MAXIMO_DESCOMPACTADO:
            raise ErroDePlanilha("O conteúdo descompactado da planilha é grande demais.")
        try:
            self._textos = self._ler_textos_compartilhados()
            self._abas = self._ler_abas()
        except (KeyError, ET.ParseError) as erro:
            raise ErroDePlanilha(f"{caminho.name} não parece um .xlsx válido: {erro}") from None

    def _ler_textos_compartilhados(self):
        if "xl/sharedStrings.xml" not in self._zip.namelist():
            return []
        raiz = ET.fromstring(self._zip.read("xl/sharedStrings.xml"))
        return ["".join(t.text or "" for t in si.iter(NS + "t")) for si in raiz.findall(NS + "si")]

    def _ler_abas(self):
        pasta = ET.fromstring(self._zip.read("xl/workbook.xml"))
        relacoes = ET.fromstring(self._zip.read("xl/_rels/workbook.xml.rels"))
        destino = {r.get("Id"): r.get("Target") for r in relacoes}
        abas = {}
        for aba in pasta.find(NS + "sheets"):
            alvo = destino[aba.get(NS_REL)].lstrip("/")
            abas[aba.get("name")] = alvo if alvo.startswith("xl/") else "xl/" + alvo
        return abas

    @property
    def nomes_das_abas(self):
        """Nomes das abas, na ordem do arquivo."""
        return list(self._abas)

    def grade(self, aba, *, expandir_mesclagens=False):
        """Conteúdo da aba como `{(linha, coluna): texto}` (linha a partir de 1, coluna de 0).

        Com `expandir_mesclagens`, o valor da célula do canto é repetido em todo o intervalo
        mesclado. Células vazias não aparecem.
        """
        if aba not in self._abas:
            raise ErroDePlanilha(f"A aba {aba!r} não existe (abas: {', '.join(self._abas)}).")
        raiz = ET.fromstring(self._zip.read(self._abas[aba]))
        celulas = {}
        for celula in raiz.iter(NS + "c"):
            valor = celula.find(NS + "v")
            if celula.get("t") == "inlineStr":  # texto dentro da própria célula, sem `<v>`
                texto = "".join(t.text or "" for t in celula.iter(NS + "t"))
            elif valor is None or valor.text is None:
                continue
            elif celula.get("t") == "s":
                texto = self._textos[int(valor.text)]
            else:
                texto = valor.text
            celulas[(_numero_da_linha(celula.get("r")), _indice_da_coluna(celula.get("r")))] = (
                texto.strip()
            )
        if expandir_mesclagens:
            mesclagens = raiz.find(NS + "mergeCells")
            for mesclagem in mesclagens if mesclagens is not None else []:
                inicio, fim = mesclagem.get("ref").split(":")
                valor = celulas.get((_numero_da_linha(inicio), _indice_da_coluna(inicio)), "")
                if not valor:
                    continue
                for linha in range(_numero_da_linha(inicio), _numero_da_linha(fim) + 1):
                    for coluna in range(_indice_da_coluna(inicio), _indice_da_coluna(fim) + 1):
                        celulas[(linha, coluna)] = valor
        return celulas

    def linhas(self, aba, *, expandir_mesclagens=False):
        """Devolve a aba como lista de linhas (listas de textos; vazio onde não há célula)."""
        grade = self.grade(aba, expandir_mesclagens=expandir_mesclagens)
        if not grade:
            return []
        ultima_linha = max(linha for linha, _ in grade)
        largura = max(coluna for _, coluna in grade) + 1
        return [
            [grade.get((linha, coluna), "") for coluna in range(largura)]
            for linha in range(1, ultima_linha + 1)
        ]

    def fechar(self):
        """Libera o arquivo."""
        self._zip.close()
