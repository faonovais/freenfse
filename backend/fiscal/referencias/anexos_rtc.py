"""Extrai, dos anexos técnicos oficiais da NFS-e (NT 009), as tabelas usadas pelo sistema.

- **Anexo VI**, aba `MUN.INCID_INFO.SERV.`: onde incide o ISSQN de cada código de tributação
  nacional (estabelecimento do prestador, local da prestação ou estabelecimento do tomador).
- **Anexo VIII**: item da LC 116 + NBS → indicador da operação (`cIndOp`) → `cClassTrib`.

Funções puras: recebem uma `Planilha` e devolvem dicionários prontos para gravar em JSON. Se a
planilha tiver uma forma inesperada, levantam `ErroDePlanilha`: é melhor recusar a carga do que
gravar uma regra fiscal adivinhada.
"""

import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

from fiscal.referencias.xlsx import ErroDePlanilha

ABA_LOCALIDADE = "MUN.INCID_INFO.SERV."
ABA_CORRELACAO = "tabela geral"
ABA_REGRA_EXTERIOR = "REGRA OP NÃO ONE_EXT"
INDOP = re.compile(r"\d{6}")


def sha256_do_arquivo(caminho):
    """SHA-256 (hex) do arquivo, como registrado no `LEIAME.md`."""
    resumo = hashlib.sha256()
    with Path(caminho).open("rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
            resumo.update(bloco)
    return resumo.hexdigest()


def gravar_json(dados, caminho):
    """Grava o JSON de forma estável (chaves ordenadas) e devolve o SHA-256 do arquivo."""
    texto = json.dumps(dados, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    Path(caminho).write_text(texto, encoding="utf-8")
    return sha256_do_arquivo(caminho)


def so_digitos(texto):
    """Mantém apenas os dígitos."""
    return "".join(c for c in str(texto) if c.isdigit())


def chaves_do_item(codigo_tributacao_nacional):
    """Chaves do Anexo VIII para um código de tributação nacional, da mais específica à geral.

    O anexo lista a maioria dos serviços pelo item da LC 116 (`AA.BB`), mas os códigos especiais
    do grupo 99 (ex.: `99.03.01`) pelo código completo (`AA.BB.CC`).
    """
    codigo = so_digitos(codigo_tributacao_nacional)
    if len(codigo) != 6:
        return []
    return [f"{codigo[:2]}.{codigo[2:4]}.{codigo[4:6]}", f"{codigo[:2]}.{codigo[2:4]}"]


# -- Anexo VI: localidade de incidência do ISSQN -------------------------------------------------


def extrair_localidade_incidencia(planilha):
    """`{cTribNac: regra}`, com a regra `EP`, `LP`, `ET` ou `SEM_INCIDENCIA`.

    As colunas da aba são: código, descrição, estabelecimento do prestador (EP), local da
    prestação (LP), estabelecimento do tomador (ET) e emitente na importação. Cada linha de dados
    precisa marcar **exatamente uma** entre EP, LP e ET, ou nenhuma (serviço sem incidência).
    """
    regras = {}
    for linha in planilha.linhas(ABA_LOCALIDADE):
        codigo = linha[0].strip() if linha else ""
        if not re.fullmatch(r"\d{5,6}", codigo):
            continue
        codigo = codigo.zfill(6)
        marcas = [(sigla, "X" in (linha[i] if len(linha) > i else "").upper())
                  for sigla, i in (("EP", 2), ("LP", 3), ("ET", 4))]  # fmt: skip
        marcadas = [sigla for sigla, marcada in marcas if marcada]
        if len(marcadas) > 1:
            raise ErroDePlanilha(f"O serviço {codigo} marca mais de uma localidade: {marcadas}.")
        if codigo in regras:
            raise ErroDePlanilha(f"O serviço {codigo} aparece duas vezes na aba de incidência.")
        regras[codigo] = marcadas[0] if marcadas else "SEM_INCIDENCIA"
    if len(regras) < 300:
        raise ErroDePlanilha(
            f"A aba de incidência trouxe só {len(regras)} serviços; o esperado são mais de 300."
        )
    return dict(sorted(regras.items()))


# -- Anexo VIII: item + NBS → INDOP → cClassTrib --------------------------------------------------


def extrair_correlacao_indop(planilha):
    """Associações do Anexo VIII, com as mesclagens expandidas.

    Devolve `{"itens": {item: {nbs: {indop: [cClassTrib…]}}}, "locais": {indop: texto},
    "exterior": {indop: indop_exterior}, "nao_onerosa": {indop: indop_nao_onerosa}}`.
    """
    grade = planilha.grade(ABA_CORRELACAO, expandir_mesclagens=True)
    ultima = max(linha for linha, _ in grade)
    itens = defaultdict(lambda: defaultdict(lambda: defaultdict(set)))
    locais = {}
    for linha in range(2, ultima + 1):
        item, nbs, indop, local, classe = (
            grade.get((linha, coluna), "") for coluna in (0, 2, 6, 7, 8)
        )
        if not (item and nbs and indop and classe):
            continue
        if not INDOP.fullmatch(indop) or not re.fullmatch(r"\d{6}", classe):
            raise ErroDePlanilha(
                f"Linha {linha}: INDOP {indop!r} ou cClassTrib {classe!r} inválido."
            )
        if not re.fullmatch(r"\d{2}\.\d{2}(\.\d{2})?", item):
            raise ErroDePlanilha(
                f"Linha {linha}: item da LC 116 {item!r} fora do formato AA.BB ou AA.BB.CC."
            )
        itens[item][so_digitos(nbs)][indop].add(classe)
        if local:
            locais.setdefault(indop, local)
    if len(itens) < 150:
        raise ErroDePlanilha(f"O Anexo VIII trouxe só {len(itens)} itens da LC 116.")
    return {
        "itens": {
            item: {
                nbs: {indop: sorted(classes) for indop, classes in sorted(por_indop.items())}
                for nbs, por_indop in sorted(por_nbs.items())
            }
            for item, por_nbs in sorted(itens.items())
        },
        "locais": dict(sorted(locais.items())),
        **_extrair_regra_exterior(planilha),
    }


def _extrair_regra_exterior(planilha):
    """Aba `REGRA OP NÃO ONE_EXT`: o INDOP muda para adquirente no exterior e para não onerosa."""
    exterior, nao_onerosa = {}, {}
    for linha in planilha.linhas(ABA_REGRA_EXTERIOR):
        celulas = [c.strip() for c in linha] + [""] * 6
        base, no_exterior, base_nao_onerosa = celulas[1], celulas[2], celulas[4]
        if INDOP.fullmatch(base) and INDOP.fullmatch(no_exterior):
            exterior[base] = no_exterior
        if INDOP.fullmatch(base) and INDOP.fullmatch(base_nao_onerosa):
            nao_onerosa[base] = base_nao_onerosa
    if not exterior:
        raise ErroDePlanilha("A aba de regras de INDOP (exterior / não onerosa) veio sem códigos.")
    return {
        "exterior": dict(sorted(exterior.items())),
        "nao_onerosa": dict(sorted(nao_onerosa.items())),
    }
