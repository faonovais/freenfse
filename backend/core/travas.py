"""Trava de exclusão mútua por empresa em PostgreSQL (*advisory lock* de sessão).

Serve a toda operação que não pode rodar em duas ao mesmo tempo para a mesma empresa e dura mais
que uma transação (chamada HTTP a um serviço externo). É uma trava **de sessão numa conexão
dedicada**: não prende nenhuma transação, é liberada na hora se o processo morrer (o PostgreSQL
encerra a sessão) e a chave inclui o schema, então empresas diferentes nunca disputam a mesma.

`fiscal.persistencia.trava.TravaPostgres` (contrato da freedfe) e as travas do Drive usam esta
mesma implementação.
"""

import hashlib
import time

from django.conf import settings
from django.db import connection

INTERVALO_DA_TENTATIVA = 0.1


class TravaOcupada(Exception):
    """Outra operação segura a trava e o prazo de espera acabou."""


def chave_da_trava(schema, recurso):
    """Inteiro de 64 bits (com sinal) derivado de `schema` e `recurso`, estável entre processos."""
    resumo = hashlib.blake2b(f"freenfse:{schema}:{recurso}".encode(), digest_size=8).digest()
    return int.from_bytes(resumo, "big", signed=True)


class TravaDeSessao:
    """Trava exclusiva por recurso e por empresa, usada como gerenciador de contexto.

    Args:
        recurso: nome do recurso (`emissao_nfse`, `drive_pastas`…).
        espera_segundos: quanto tempo esperar a trava ficar livre. Com 0, falha de imediato.
        pausa: espera entre as tentativas (substituível nos testes).
        relogio: relógio monotônico (substituível nos testes).
        ajuste_de_transacao: nome do ajuste que, ligado, permite usar a trava dentro de uma
            transação (só os testes ligam, porque o pytest-django envolve cada teste em uma).

    """

    def __init__(
        self,
        recurso,
        *,
        espera_segundos=0.0,
        pausa=time.sleep,
        relogio=time.monotonic,
        ajuste_de_transacao="FREENFSE_TRAVA_EM_TRANSACAO_PERMITIDA",
    ):
        """Fixa o schema da empresa ativa no momento da criação da trava."""
        self._ajuste_de_transacao = ajuste_de_transacao
        self.recurso = recurso
        self.schema = connection.schema_name
        self._chave = chave_da_trava(self.schema, recurso)
        self._espera = espera_segundos
        self._pausa = pausa
        self._relogio = relogio
        self._conexao = None

    def __enter__(self):
        if connection.in_atomic_block and not getattr(settings, self._ajuste_de_transacao, False):
            raise RuntimeError(
                "Esta operação não pode rodar dentro de uma transação: a trava de sessão "
                "precisa viver fora dela."
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
                raise TravaOcupada(self.recurso)
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
