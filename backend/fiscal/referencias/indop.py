"""Indicador da operação (`cIndOp`) segundo o Anexo VIII da NT 009 e a regra E0902.

O Anexo VIII correlaciona o item da LC 116 (ou o código completo, nos códigos especiais do grupo
99) e a NBS do serviço ao `INDOP` e às classificações tributárias (`cClassTrib`) possíveis.
"""

import json
import re
from functools import lru_cache
from pathlib import Path

from fiscal.referencias.anexos_rtc import chaves_do_item, so_digitos

ARQUIVO = Path(__file__).resolve().parent / "dados" / "correlacao_indop.json"
FORMATO_DO_INDOP = re.compile(r"\d{6}")
CODIGO_E0902 = "E0902"
INDOP_DA_LOCACAO = re.compile(r"02\d{4}")
PREFIXO_DO_GRUPO_99_03 = "9903"


@lru_cache(maxsize=1)
def _tabela():
    return json.loads(ARQUIVO.read_text(encoding="utf-8"))


def origem():
    """Proveniência da tabela (documento, arquivo, SHA-256, data da obtenção)."""
    return _tabela()["origem"]


@lru_cache(maxsize=1)
def indicadores_do_anexo_viii():
    """Todo `cIndOp` que o Anexo VIII cita para algum serviço (incluindo os equivalentes)."""
    tabela = _tabela()
    achados = set()
    for por_nbs in tabela["itens"].values():
        for por_indop in por_nbs.values():
            achados.update(por_indop)
    for equivalentes in (tabela["exterior"], tabela["nao_onerosa"]):
        achados.update(equivalentes)
        achados.update(equivalentes.values())
    return frozenset(achados)


def _por_nbs(codigo_tributacao_nacional):
    itens = _tabela()["itens"]
    for chave in chaves_do_item(codigo_tributacao_nacional):
        if chave in itens:
            return chave, itens[chave]
    return None, {}


def correlacao(codigo_tributacao_nacional, nbs):
    """`(item, {indop: [cClassTrib…]})` do Anexo VIII para o serviço; vazio se não consta."""
    item, por_nbs = _por_nbs(codigo_tributacao_nacional)
    return item, dict(por_nbs.get(so_digitos(nbs), {}))


def sugerir(codigo_tributacao_nacional, nbs):
    """Sugere o `cIndOp` a partir do item e da NBS do serviço.

    Devolve `{"sugestao": str|None, "opcoes": [str…], "item": str|None, "encontrado": bool}`.
    Só há `sugestao` quando o anexo indica **um único** INDOP; com mais de um, as `opcoes` são
    mostradas ao usuário e ele escolhe. Item/NBS que não constam do anexo: `encontrado=False`.
    """
    item, por_indop = correlacao(codigo_tributacao_nacional, nbs)
    opcoes = sorted(por_indop)
    return {
        "sugestao": opcoes[0] if len(opcoes) == 1 else None,
        "opcoes": opcoes,
        "item": item,
        "encontrado": bool(opcoes),
    }


def classes_possiveis(codigo_tributacao_nacional, nbs, indop=None):
    """`cClassTrib` que o anexo associa ao serviço (e ao INDOP, se informado)."""
    _, por_indop = correlacao(codigo_tributacao_nacional, nbs)
    if indop is not None:
        return list(por_indop.get(indop, []))
    return sorted({c for classes in por_indop.values() for c in classes})


def local_de_incidencia_do_ibs(indop):
    """Texto do anexo para o local de incidência do IBS desse INDOP; `None` se não consta."""
    return _tabela()["locais"].get(indop)


def indop_para_exterior(indop):
    """INDOP equivalente para adquirente no exterior (aba de regras do anexo); `None` se não há."""
    return _tabela()["exterior"].get(indop)


def violacoes_do_indicador(codigo_tributacao_nacional, indop):
    """Erros de formato do `cIndOp` e a regra **E0902** (99.03 exige o grupo 02XXXX).

    Devolve uma lista de `(codigo_da_regra, mensagem)`; vazia se está tudo certo.
    """
    indop = str(indop or "").strip()
    if not FORMATO_DO_INDOP.fullmatch(indop):
        return [("formato", "O indicador da operação (cIndOp) tem 6 dígitos.")]
    codigo = so_digitos(codigo_tributacao_nacional)
    if codigo.startswith(PREFIXO_DO_GRUPO_99_03) and not INDOP_DA_LOCACAO.fullmatch(indop):
        return [
            (
                CODIGO_E0902,
                "Para o código de tributação nacional 99.03 o indicador da operação (cIndOp) deve "
                "ser do grupo 02XXXX. Regra E0902 da Sefin.",
            )
        ]
    return []
