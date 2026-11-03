"""Trava de exclusão mútua em PostgreSQL (*advisory lock* de sessão, em conexão dedicada).

Por que de sessão e numa conexão própria: a trava de emissão dura todo o `POST` à Sefin, que
pode levar dezenas de segundos. Uma trava de transação (`pg_advisory_xact_lock`) obrigaria a
manter uma transação aberta durante a chamada HTTP, e o `ENVIADA` gravado antes do `POST` não
ficaria confirmado. Com uma conexão dedicada em autocommit, as gravações de estado seguem
confirmadas pela conexão normal e a trava vive à parte.

Se o processo morrer, o PostgreSQL encerra a sessão e libera a trava na hora (não há trava
"abandonada" para expirar, ao contrário da trava em arquivo).

A chave inclui o schema da empresa: empresas diferentes nunca disputam a mesma trava.
"""

import hashlib
import time

from django.conf import settings
from django.db import connection
from freedfe.distribuicao.trava import Trava
from freedfe.excecoes import SincronizacaoEmAndamentoErro

INTERVALO_DA_TENTATIVA = 0.1


def chave_da_trava(schema, recurso):
    """Inteiro de 64 bits (com sinal) derivado de `schema` e `recurso`, estável entre processos."""
    resumo = hashlib.blake2b(f"freenfse:{schema}:{recurso}".encode(), digest_size=8).digest()
    return int.from_bytes(resumo, "big", signed=True)


class TravaPostgres(Trava):
    """Trava exclusiva por recurso e por empresa.

    Args:
        recurso: nome do recurso (`emissao_nfse`, `nsu_nfse`…).
        espera_segundos: quanto tempo esperar a trava ficar livre. Com 0, falha de imediato.
        pausa: espera entre as tentativas (substituível nos testes).
        relogio: relógio monotônico (substituível nos testes).

    """

    def __init__(
        self,
        recurso,
        *,
        espera_segundos=0.0,
        pausa=time.sleep,
        relogio=time.monotonic,
    ):
        """Fixa o schema da empresa ativa no momento da criação da trava."""
        self.recurso = recurso
        self.schema = connection.schema_name
        self._chave = chave_da_trava(self.schema, recurso)
        self._espera = espera_segundos
        self._pausa = pausa
        self._relogio = relogio
        self._conexao = None

    def __enter__(self):
        if connection.in_atomic_block and not getattr(
            settings, "FREENFSE_EMISSAO_EM_TRANSACAO_PERMITIDA", False
        ):
            raise RuntimeError(
                "A emissão não pode rodar dentro de uma transação: o estado 'enviada' "
                "precisa estar confirmado antes do envio à Sefin."
            )
        self._conexao = connection.copy()
        try:
            self._conexao.ensure_connection()
            self._conexao.set_autocommit(True)
            self._adquirir()
        except BaseException:
            self._fechar()
            raise
        return self

    def _adquirir(self):
        prazo = self._relogio() + self._espera
        while True:
            with self._conexao.cursor() as cursor:
                cursor.execute("SELECT pg_try_advisory_lock(%s)", [self._chave])
                if cursor.fetchone()[0]:
                    return
            if self._relogio() >= prazo:
                raise SincronizacaoEmAndamentoErro(
                    f"Há outra operação fiscal em andamento nesta empresa ({self.recurso}). "
                    "Aguarde alguns instantes."
                )
            self._pausa(INTERVALO_DA_TENTATIVA)

    def __exit__(self, *_excecao):
        try:
            if self._conexao is not None and self._conexao.connection is not None:
                with self._conexao.cursor() as cursor:
                    cursor.execute("SELECT pg_advisory_unlock(%s)", [self._chave])
        finally:
            self._fechar()

    def _fechar(self):
        conexao, self._conexao = self._conexao, None
        if conexao is not None:
            conexao.close()  # encerrar a sessão também libera a trava
