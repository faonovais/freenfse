"""Criptografia simétrica autenticada (AES-256-GCM) com chaves versionadas.

Objetivo (§4.4 dos requisitos): um *dump* do banco não expõe certificados,
senhas nem tokens. As chaves ficam **fora do banco**, na variável de ambiente
`FREENFSE_CHAVES`, em pares `versão:chave` separados por vírgula. A primeira é a
atual (usada para cifrar); as demais são antigas, mantidas só para decifrar
valores ainda não recriptografados:

    FREENFSE_CHAVES=2:<chave-nova>,1:<chave-antiga>

Cada chave é 32 bytes aleatórios em base64 URL-safe (`gerar_chave()`).

Formato do token: `v<n>:` + nonce (12 bytes) + texto cifrado com o tag GCM.
Na forma textual, o que vem depois de `v<n>:` é base64 URL-safe.

Nenhuma mensagem de erro contém valor em claro, texto cifrado ou chave.
"""

import base64
import binascii
import os
import re
from functools import lru_cache

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings

TAMANHO_CHAVE = 32
TAMANHO_NONCE = 12
_PREFIXO_BINARIO = re.compile(rb"v(\d+):")
_PREFIXO_TEXTO = re.compile(r"v(\d+):")


class ErroDeCriptografia(Exception):
    """Falha ao cifrar ou decifrar. A mensagem nunca traz o conteúdo envolvido."""


class ErroDeConfiguracaoDeChaves(ErroDeCriptografia):
    """`FREENFSE_CHAVES` ausente ou malformada."""


def gerar_chave():
    """Gera uma chave nova (32 bytes aleatórios em base64 URL-safe)."""
    return base64.urlsafe_b64encode(os.urandom(TAMANHO_CHAVE)).decode("ascii")


@lru_cache(maxsize=8)
def _interpretar(brutas):
    if not brutas:
        raise ErroDeConfiguracaoDeChaves("FREENFSE_CHAVES não está configurada.")
    chaves = {}
    atual = None
    for posicao, item in enumerate(brutas, start=1):
        versao_txt, separador, chave_b64 = item.strip().partition(":")
        if not separador or not versao_txt.isdigit() or int(versao_txt) < 1:
            raise ErroDeConfiguracaoDeChaves(
                f"FREENFSE_CHAVES, item {posicao}: use o formato versão:chave (versão inteira ≥ 1)."
            )
        versao = int(versao_txt)
        if versao in chaves:
            raise ErroDeConfiguracaoDeChaves(f"FREENFSE_CHAVES: versão {versao} repetida.")
        try:
            chave = base64.urlsafe_b64decode(chave_b64.encode("ascii"))
        except binascii.Error, ValueError, UnicodeEncodeError:
            raise ErroDeConfiguracaoDeChaves(
                f"FREENFSE_CHAVES, versão {versao}: a chave não é base64 válido."
            ) from None
        if len(chave) != TAMANHO_CHAVE:
            raise ErroDeConfiguracaoDeChaves(
                f"FREENFSE_CHAVES, versão {versao}: a chave deve ter {TAMANHO_CHAVE} bytes."
            )
        chaves[versao] = chave
        if atual is None:
            atual = versao
    return atual, chaves


def _chaves():
    return _interpretar(tuple(getattr(settings, "FREENFSE_CHAVES", None) or ()))


def versao_atual():
    """Versão da chave usada para cifrar."""
    return _chaves()[0]


def _cifrar(dados):
    versao, chaves = _chaves()
    nonce = os.urandom(TAMANHO_NONCE)
    return versao, nonce + AESGCM(chaves[versao]).encrypt(nonce, dados, None)


def _decifrar(versao, corpo):
    chave = _chaves()[1].get(versao)
    if chave is None:
        raise ErroDeCriptografia(f"Chave de criptografia v{versao} não está configurada.")
    if len(corpo) <= TAMANHO_NONCE:
        raise ErroDeCriptografia("Token criptografado inválido.")
    try:
        return AESGCM(chave).decrypt(corpo[:TAMANHO_NONCE], corpo[TAMANHO_NONCE:], None)
    except InvalidTag:
        raise ErroDeCriptografia(
            "Não foi possível decifrar o valor (chave incorreta ou dado adulterado)."
        ) from None


def cifrar_bytes(dados):
    """Cifra bytes e devolve `b"v<n>:" + nonce + cifra`."""
    if not isinstance(dados, bytes | bytearray | memoryview):
        raise ErroDeCriptografia("Esperados bytes para cifrar.")
    versao, corpo = _cifrar(bytes(dados))
    return b"v%d:" % versao + corpo


def decifrar_bytes(token):
    """Decifra um token binário gerado por `cifrar_bytes`."""
    token = bytes(token)
    achado = _PREFIXO_BINARIO.match(token)
    if not achado:
        raise ErroDeCriptografia("Token criptografado inválido.")
    return _decifrar(int(achado.group(1)), token[achado.end() :])


def cifrar_texto(texto):
    """Cifra texto e devolve `v<n>:` + base64 URL-safe de (nonce + cifra)."""
    if not isinstance(texto, str):
        raise ErroDeCriptografia("Esperado texto para cifrar.")
    versao, corpo = _cifrar(texto.encode("utf-8"))
    return f"v{versao}:" + base64.urlsafe_b64encode(corpo).decode("ascii")


def decifrar_texto(token):
    """Decifra um token textual gerado por `cifrar_texto`."""
    achado = _PREFIXO_TEXTO.match(token or "")
    if not achado:
        raise ErroDeCriptografia("Token criptografado inválido.")
    try:
        corpo = base64.urlsafe_b64decode(token[achado.end() :].encode("ascii"))
    except binascii.Error, ValueError, UnicodeEncodeError:
        raise ErroDeCriptografia("Token criptografado inválido.") from None
    try:
        return _decifrar(int(achado.group(1)), corpo).decode("utf-8")
    except UnicodeDecodeError:
        raise ErroDeCriptografia("Token criptografado inválido.") from None


def versao_do_token(token):
    """Versão da chave com que o token foi cifrado (texto ou binário)."""
    if isinstance(token, str):
        achado = _PREFIXO_TEXTO.match(token)
    else:
        achado = _PREFIXO_BINARIO.match(bytes(token))
    if not achado:
        raise ErroDeCriptografia("Token criptografado inválido.")
    return int(achado.group(1))
