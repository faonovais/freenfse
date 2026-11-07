"""Local do fornecimento de cada indicador da operação (`cIndOp`), pelo Anexo VII da NT 009.

As regras E0239, E0243 e E0919 do Anexo VI dependem de o `cIndOp` indicar que o município de
incidência é o do endereço do **tomador/adquirente** ou o do **destinatário**. O Anexo VII traz
isso na coluna estruturada `NFSeLocIncidIBS`; é dela, e só dela, que sai a classificação
(`adquirente`, `destinatario` ou `outro`). Quando o texto livre do anexo cita o adquirente e a
coluna estruturada não, o caso é **avisado, nunca bloqueado**. ADR 0011.

A tabela é gravada por `importar_anexos_rtc --anexo-vii` (origem, URL, data e SHA-256 no próprio
JSON e no `LEIAME.md`). Nada aqui consulta a rede.
"""

import json
from functools import lru_cache
from pathlib import Path

from fiscal.referencias import indop
from fiscal.referencias.anexos_rtc import ADQUIRENTE, DESTINATARIO, OUTRO

ARQUIVO = Path(__file__).resolve().parent / "dados" / "indop_local_fornecimento.json"

AVISO_DO_TEXTO_DO_ADQUIRENTE = (
    "O texto do Anexo VII indica o endereço do adquirente para este indicador; confira se o "
    "tomador tem CPF/CNPJ e endereço nacional, para evitar a rejeição E0239."
)

__all__ = [
    "ADQUIRENTE",
    "DESTINATARIO",
    "OUTRO",
    "aviso_do_texto",
    "descricao",
    "existe",
    "local_do_fornecimento",
    "origem",
]


@lru_cache(maxsize=1)
def _tabela():
    return json.loads(ARQUIVO.read_text(encoding="utf-8"))


def origem():
    """Proveniência da tabela (documento, arquivo, URL, SHA-256, data da obtenção)."""
    return _tabela()["origem"]


def existe(codigo_indicador):
    """Diz se o indicador consta da tabela oficial (os 40 do Anexo VII)."""
    return str(codigo_indicador or "") in _tabela()["indicadores"]


def local_do_fornecimento(codigo_indicador):
    """Onde fica o local do fornecimento do indicador: `adquirente`, `destinatario` ou `outro`.

    Devolve `None` quando o indicador **não consta da tabela**: quem chama bloqueia a emissão.
    Indicador que consta e não tem endereço de tomador nem de destinatário é `outro`.
    """
    registro = _tabela()["indicadores"].get(str(codigo_indicador or ""))
    return None if registro is None else registro["classe"]


def descricao(codigo_indicador):
    """O tipo de operação do indicador, em texto oficial (para as mensagens); `""` se não consta."""
    registro = _tabela()["indicadores"].get(str(codigo_indicador or ""))
    return "" if registro is None else registro["tipo"]


def aviso_do_texto(codigo_indicador):
    """Aviso (não bloqueante) para o indicador cujo texto cita o adquirente e a coluna não.

    Vale só para indicador que o próprio Anexo VIII sugere a algum serviço: é o caso do 130201
    (transporte dutoviário de gás natural), que o Anexo VII descreve como "estabelecimento
    principal do adquirente" mas classifica sem local de incidência para a NFS-e.
    """
    registro = _tabela()["indicadores"].get(str(codigo_indicador or ""))
    if (
        registro is not None
        and registro["classe"] == OUTRO
        and ADQUIRENTE in registro["texto_cita"]
        and str(codigo_indicador) in indop.indicadores_do_anexo_viii()
    ):
        return AVISO_DO_TEXTO_DO_ADQUIRENTE
    return None
