"""Modelos de caminho do Google Drive: variáveis, normalização, validação e pré-visualização.

Dois modelos com as mesmas variáveis: um para as **subpastas** (cada `/` cria um nível) e outro
para o **nome do arquivo** (sem `/`; `.xml`/`.pdf` é acrescentado pelo sistema). A data de
referência é a **data de emissão** da NFS-e (não a competência), no fuso de Brasília.
"""

import re
import zoneinfo

from django.utils import timezone

from documentos.services import modelos_texto

FUSO = zoneinfo.ZoneInfo("America/Sao_Paulo")
MAXIMO_DO_NOME = 100
PADRAO_DO_ARQUIVO = "{chave}"
_CONTROLE = re.compile(r"[\x00-\x1f\x7f]")
_ESPACOS = re.compile(r"\s+")

VARIAVEIS = {
    "ano": "Ano da data de emissão (2026)",
    "mes": "Mês da data de emissão (01 a 12)",
    "dia": "Dia da data de emissão (01 a 31)",
    "numero_nfse": "Número da NFS-e, sem zeros à esquerda",
    "nome_emitente": "Razão social do prestador (emitente)",
    "cnpj_emitente": "CNPJ (ou CPF) do prestador, só dígitos",
    "chave": "Chave de acesso (50 dígitos): garante nome único",
}


def normalizar(valor):
    """Texto seguro para nome de pasta ou arquivo: sem barras, controle e repetição de espaços."""
    texto = _CONTROLE.sub("", str(valor)).replace("/", "").replace("\\", "")
    texto = _ESPACOS.sub(" ", texto).strip()
    return texto[:MAXIMO_DO_NOME].strip()


def valores_da_nota(nfse, empresa):
    """Valor (já normalizado) de cada variável para a nota."""
    emissao = timezone.localtime(nfse.emitida_em, FUSO) if nfse.emitida_em else None
    bruto = {
        "ano": f"{emissao:%Y}" if emissao else "",
        "mes": f"{emissao:%m}" if emissao else "",
        "dia": f"{emissao:%d}" if emissao else "",
        "numero_nfse": (nfse.numero_nfse or "").lstrip("0") or (nfse.numero_nfse or ""),
        "nome_emitente": empresa.razao_social,
        "cnpj_emitente": "".join(c for c in empresa.cnpj if c.isalnum()),
        "chave": nfse.chave or "",
    }
    return {nome: normalizar(valor) for nome, valor in bruto.items()}


def validar(modelo_subpastas, modelo_arquivo):
    """Todos os erros dos dois modelos, por campo (lista vazia = válido)."""
    erros = {}
    usadas = set()
    subpastas = (modelo_subpastas or "").strip()
    arquivo = (modelo_arquivo or "").strip() or PADRAO_DO_ARQUIVO

    problemas, achadas = modelos_texto.analisar(subpastas, set(VARIAVEIS))
    usadas |= set(achadas)
    if "\\" in subpastas:
        problemas.append("Use '/' para separar as subpastas, não '\\'.")
    if subpastas and any(not nivel.strip() for nivel in subpastas.split("/")):
        problemas.append(
            "Há um nível de pasta vazio (por exemplo '//' ou '/' no início ou no fim)."
        )
    if problemas:
        erros["modelo_subpastas"] = problemas

    problemas, achadas = modelos_texto.analisar(arquivo, set(VARIAVEIS))
    usadas |= set(achadas)
    if "/" in arquivo or "\\" in arquivo:
        problemas.append("O nome do arquivo não pode ter '/' nem '\\'.")
    if problemas:
        erros["modelo_arquivo"] = problemas

    if "modelo_subpastas" not in erros and "modelo_arquivo" not in erros:
        if not ("chave" in usadas or {"numero_nfse", "cnpj_emitente"} <= usadas):
            erros["unicidade"] = [
                "O caminho completo precisa identificar uma única nota: use {chave} ou "
                "{numero_nfse} junto com {cnpj_emitente}. Sem isso, uma nota sobrescreveria outra."
            ]
    return erros


def caminho_da_nota(configuracao, nfse, empresa):
    """`(níveis, nome_base)`: as subpastas e o nome do arquivo (sem extensão) para a nota."""
    valores = valores_da_nota(nfse, empresa)

    def montar(modelo):
        return modelos_texto.renderizar(modelo, valores)

    niveis = []
    if (configuracao.modelo_subpastas or "").strip():
        for nivel in configuracao.modelo_subpastas.strip().split("/"):
            texto = montar(nivel).strip()
            niveis.append(normalizar(texto) or "_")
    modelo_arquivo = (configuracao.modelo_arquivo or "").strip() or PADRAO_DO_ARQUIVO
    nome = normalizar(montar(modelo_arquivo)) or normalizar(nfse.chave or "") or f"nota-{nfse.pk}"
    return niveis, nome


def pre_visualizar(configuracao, nfse, empresa):
    """Como a nota ficaria no Drive: caminho completo dos arquivos XML, PDF e de um evento."""
    niveis, nome = caminho_da_nota(configuracao, nfse, empresa)
    pasta = "/".join(niveis)
    prefixo = f"{pasta}/" if pasta else ""
    return {
        "pasta": pasta or "(pasta raiz)",
        "arquivos": [f"{prefixo}{nome}.xml", f"{prefixo}{nome}.pdf"],
        "evento": f"{prefixo}{nome}_cancelamento.xml",
    }
