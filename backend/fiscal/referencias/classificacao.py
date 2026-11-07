"""Classificação tributária do IBS/CBS (cClassTrib) com vigência, dos dados abertos da calculadora.

Regras do Anexo VI que dependem desta tabela: **E0859/E0860/E0960/E0961** (o grupo de IBS/CBS e o
`cIndOp` são obrigatórios quando `ind_gIBSCBS = 1` e proibidos quando `= 0`) e **E0958** (a
classificação precisa valer para NFS-e). A tabela é regravada por
`atualizar_classificacao_tributaria`; o primeiro dia pesquisado está em `origem()`.
"""

import datetime as dt
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

ARQUIVO = Path(__file__).resolve().parent / "dados" / "classificacao_tributaria.json"


@dataclass(frozen=True)
class Classificacao:
    """Uma classificação tributária e a janela em que vigora."""

    codigo: str
    descricao: str
    vigencia_inicio: dt.date
    vigencia_fim: dt.date | None
    aceita_nfse: bool
    exige_grupo_ibs_cbs: bool | None

    def vigente_em(self, data):
        """Vale na data (início e fim inclusivos)."""
        return self.vigencia_inicio <= data and (
            self.vigencia_fim is None or data <= self.vigencia_fim
        )


@lru_cache(maxsize=1)
def _carregar():
    bruto = json.loads(ARQUIVO.read_text(encoding="utf-8"))
    tabela = {}
    for item in bruto["classificacoes"]:
        tabela[item["codigo"]] = Classificacao(
            codigo=item["codigo"],
            descricao=item["descricao"],
            vigencia_inicio=dt.date.fromisoformat(item["vigencia_inicio"]),
            vigencia_fim=dt.date.fromisoformat(item["vigencia_fim"])
            if item["vigencia_fim"]
            else None,
            aceita_nfse=item["aceita_nfse"],
            exige_grupo_ibs_cbs=item["exige_grupo_ibs_cbs"],
        )
    return bruto["origem"], tabela


def origem():
    """Proveniência da tabela (fonte, versão da calculadora, SHA-256 das listas, período)."""
    return _carregar()[0]


def primeiro_dia_pesquisado():
    """Antes desta data a tabela não informa vigência."""
    return dt.date.fromisoformat(origem()["periodo_pesquisado"][0])


def existe(c_class_trib):
    """Diz se a classificação consta da tabela, em qualquer data."""
    return str(c_class_trib or "").strip() in _carregar()[1]


def consultar(c_class_trib, data):
    """Devolve a classificação vigente na data, ou `None` se não consta ou não vigora."""
    classificacao = _carregar()[1].get(str(c_class_trib or "").strip())
    if classificacao is not None and classificacao.vigente_em(data):
        return classificacao
    return None


def todas():
    """Todas as classificações da tabela, por código."""
    return dict(_carregar()[1])
