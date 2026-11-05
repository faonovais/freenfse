"""Onde incide o ISSQN de cada serviço, conforme o Anexo VI da NT 009 (LC 116/2003, art. 3º).

A aba oficial `MUN.INCID_INFO.SERV.` diz, para cada código de tributação nacional, se o imposto é
devido no **estabelecimento do prestador** (`EP`, a regra geral do caput do art. 3º), no **local da
prestação** (`LP`, as exceções dos incisos do art. 3º e o §3º do serviço portuário 20.01.01), no
**estabelecimento do tomador** (`ET`, fornecimento de mão de obra, 17.05.01) ou se **não há
incidência** (`SEM_INCIDENCIA`, 99.01.01). A tabela é regravada por `importar_anexos_rtc`.
"""

import json
from functools import lru_cache
from pathlib import Path

ARQUIVO = Path(__file__).resolve().parent / "dados" / "localidade_incidencia.json"
EP, LP, ET, SEM_INCIDENCIA = "EP", "LP", "ET", "SEM_INCIDENCIA"
DESCRICAO = {
    EP: "estabelecimento do prestador",
    LP: "local da prestação",
    ET: "estabelecimento do tomador",
    SEM_INCIDENCIA: "sem incidência de ISSQN",
}


@lru_cache(maxsize=1)
def _tabela():
    return json.loads(ARQUIVO.read_text(encoding="utf-8"))


def origem():
    """Proveniência da tabela (documento, arquivo, SHA-256, data da obtenção)."""
    return _tabela()["origem"]


def regra_de_incidencia(codigo_tributacao_nacional):
    """`EP`, `LP`, `ET` ou `SEM_INCIDENCIA`; `None` se o código não consta do anexo."""
    return _tabela()["regras"].get(str(codigo_tributacao_nacional or "").strip())


def todas_as_regras():
    """O mapa completo `{cTribNac: regra}` (somente leitura)."""
    return dict(_tabela()["regras"])
