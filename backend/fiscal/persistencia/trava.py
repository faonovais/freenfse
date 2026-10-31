"""Trava de exclusão mútua da emissão (contrato `Trava` da freedfe) sobre a trava de sessão.

Por que de sessão e numa conexão própria: a trava de emissão dura todo o `POST` à Sefin, que
pode levar dezenas de segundos. Uma trava de transação obrigaria a manter uma transação aberta
durante a chamada HTTP, e o `ENVIADA` gravado antes do `POST` não ficaria confirmado. A
implementação (conexão dedicada, chave por schema, liberação ao morrer a sessão) está em
`core.travas`; aqui só se adapta a exceção ao contrato da biblioteca.
"""

import time

from freedfe.distribuicao.trava import Trava
from freedfe.excecoes import SincronizacaoEmAndamentoErro

from core.travas import INTERVALO_DA_TENTATIVA, TravaDeSessao, TravaOcupada, chave_da_trava

__all__ = ["INTERVALO_DA_TENTATIVA", "TravaPostgres", "chave_da_trava"]


class TravaPostgres(Trava):
    """Trava exclusiva por recurso e por empresa, com a exceção da freedfe.

    Args:
        recurso: nome do recurso (`emissao_nfse`, `nsu_nfse`…).
        espera_segundos: quanto tempo esperar a trava ficar livre. Com 0, falha de imediato.
        pausa: espera entre as tentativas (substituível nos testes).
        relogio: relógio monotônico (substituível nos testes).

    """

    def __init__(self, recurso, *, espera_segundos=0.0, pausa=time.sleep, relogio=time.monotonic):
        """Cria a trava de sessão do recurso para a empresa ativa."""
        self.recurso = recurso
        self._trava = TravaDeSessao(
            recurso,
            espera_segundos=espera_segundos,
            pausa=pausa,
            relogio=relogio,
            ajuste_de_transacao="FREENFSE_EMISSAO_EM_TRANSACAO_PERMITIDA",
        )
        self.schema = self._trava.schema

    @property
    def _conexao(self):
        return self._trava._conexao

    def _fechar(self):
        self._trava._fechar()

    def __enter__(self):
        try:
            self._trava.__enter__()
        except TravaOcupada:
            raise SincronizacaoEmAndamentoErro(
                f"Há outra operação fiscal em andamento nesta empresa ({self.recurso}). "
                "Aguarde alguns instantes."
            ) from None
        except RuntimeError:
            raise RuntimeError(
                "A emissão não pode rodar dentro de uma transação: o estado 'enviada' "
                "precisa estar confirmado antes do envio à Sefin."
            ) from None
        return self

    def __exit__(self, *excecao):
        self._trava.__exit__(*excecao)
