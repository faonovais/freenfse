"""Trilha técnica das chamadas da freedfe à Sefin, em PostgreSQL.

A biblioteca promete nunca entregar XML a esta trilha; mesmo assim, o que chega aqui é
filtrado: conteúdo binário é descartado e textos longos são cortados. Quem fez a ação (usuário,
IP) fica em `core.LogAuditoria`; esta tabela responde "o que o sistema disse à Sefin e o que ela
respondeu".
"""

from freedfe.auditoria import Auditoria

from fiscal.persistencia.modelos import AuditoriaFiscal

TAMANHO_MAXIMO_DE_TEXTO = 500
_CAMPOS_PROPRIOS = ("servico", "operacao", "id_dps", "chave", "situacao")


def _limpar(valor):
    if isinstance(valor, bytes | bytearray):
        return None
    if isinstance(valor, str):
        return valor[:TAMANHO_MAXIMO_DE_TEXTO]
    if isinstance(valor, dict):
        return {str(k): _limpar(v) for k, v in valor.items() if _limpar(v) is not None}
    if isinstance(valor, list | tuple | set | frozenset):
        return [_limpar(v) for v in valor if _limpar(v) is not None]
    if valor is None or isinstance(valor, bool | int | float):
        return valor
    return str(valor)[:TAMANHO_MAXIMO_DE_TEXTO]


class AuditoriaPostgres(Auditoria):
    """Grava cada chamada como uma linha de `AuditoriaFiscal`."""

    def registrar(self, **dados):
        """Registra a chamada; as chaves conhecidas viram colunas e o resto vai em `dados`."""
        proprios = {c: str(dados.pop(c) or "") for c in _CAMPOS_PROPRIOS if c in dados}
        AuditoriaFiscal.objects.create(
            **{c: v[:60] for c, v in proprios.items() if c not in ("id_dps", "chave")},
            id_dps=proprios.get("id_dps", "")[:45],
            chave=proprios.get("chave", "")[:50],
            dados=_limpar(dados) or {},
        )
