import base64

import pytest

from core import crypto

CHAVE_1 = base64.urlsafe_b64encode(bytes(range(32))).decode()
CHAVE_2 = base64.urlsafe_b64encode(bytes(range(32, 64))).decode()
SEGREDO = "senha-fictícia-do-certificado-ç"


def test_gerar_chave_tem_32_bytes_em_base64():
    chave = crypto.gerar_chave()

    assert len(base64.urlsafe_b64decode(chave)) == 32
    assert crypto.gerar_chave() != chave


def test_token_de_texto_tem_versao_nonce_e_cifra(settings):
    settings.FREENFSE_CHAVES = [f"3:{CHAVE_1}"]

    token = crypto.cifrar_texto(SEGREDO)

    assert token.startswith("v3:")
    corpo = base64.urlsafe_b64decode(token[3:])
    assert len(corpo) == 12 + len(SEGREDO.encode()) + 16  # nonce + texto + tag GCM
    assert SEGREDO not in token
    assert crypto.versao_do_token(token) == 3
    assert crypto.decifrar_texto(token) == SEGREDO


def test_token_binario_tem_prefixo_nonce_e_cifra(settings):
    settings.FREENFSE_CHAVES = [f"2:{CHAVE_1}"]
    dados = bytes(range(256)) * 3

    token = crypto.cifrar_bytes(dados)

    assert token.startswith(b"v2:")
    assert len(token) == 3 + 12 + len(dados) + 16
    assert dados not in token
    assert crypto.versao_do_token(token) == 2
    assert crypto.decifrar_bytes(token) == dados


def test_cada_cifragem_usa_nonce_novo(settings):
    settings.FREENFSE_CHAVES = [f"1:{CHAVE_1}"]

    assert crypto.cifrar_texto("igual") != crypto.cifrar_texto("igual")


def test_valor_cifrado_com_chave_antiga_e_lido_apos_a_rotacao(settings):
    settings.FREENFSE_CHAVES = [f"1:{CHAVE_1}"]
    antigo = crypto.cifrar_texto(SEGREDO)

    settings.FREENFSE_CHAVES = [f"2:{CHAVE_2}", f"1:{CHAVE_1}"]

    assert crypto.versao_atual() == 2
    assert crypto.decifrar_texto(antigo) == SEGREDO
    assert crypto.versao_do_token(crypto.cifrar_texto(SEGREDO)) == 2


def test_chave_removida_da_configuracao_nao_decifra_e_nao_vaza(settings):
    settings.FREENFSE_CHAVES = [f"1:{CHAVE_1}"]
    antigo = crypto.cifrar_texto(SEGREDO)
    settings.FREENFSE_CHAVES = [f"2:{CHAVE_2}"]

    with pytest.raises(crypto.ErroDeCriptografia) as erro:
        crypto.decifrar_texto(antigo)

    assert "v1" in str(erro.value)
    assert SEGREDO not in str(erro.value)
    assert antigo not in str(erro.value)


def test_dado_adulterado_e_recusado_sem_vazar_conteudo(settings):
    settings.FREENFSE_CHAVES = [f"1:{CHAVE_1}"]
    token = crypto.cifrar_texto(SEGREDO)
    corpo = bytearray(base64.urlsafe_b64decode(token[3:]))
    corpo[-1] ^= 0x01
    adulterado = "v1:" + base64.urlsafe_b64encode(bytes(corpo)).decode()

    with pytest.raises(crypto.ErroDeCriptografia) as erro:
        crypto.decifrar_texto(adulterado)

    assert SEGREDO not in str(erro.value)
    assert adulterado not in str(erro.value)


@pytest.mark.parametrize("token", ["", "sem-prefixo", "v1:", "v1:@@@", "vx:abc", "v1:YQ=="])
def test_token_invalido_e_recusado(settings, token):
    settings.FREENFSE_CHAVES = [f"1:{CHAVE_1}"]

    with pytest.raises(crypto.ErroDeCriptografia):
        crypto.decifrar_texto(token)


def test_token_binario_invalido_e_recusado(settings):
    settings.FREENFSE_CHAVES = [f"1:{CHAVE_1}"]

    for token in (b"", b"semprefixo", b"v1:curto"):
        with pytest.raises(crypto.ErroDeCriptografia):
            crypto.decifrar_bytes(token)


@pytest.mark.parametrize(
    "configuracao",
    [
        [],
        ["sem-versao"],
        ["0:" + CHAVE_1],
        ["x:" + CHAVE_1],
        ["1:" + CHAVE_1, "1:" + CHAVE_2],
        ["1:nao-e-base64!!"],
        ["1:" + base64.urlsafe_b64encode(b"curta").decode()],
    ],
)
def test_configuracao_de_chaves_invalida_e_recusada(settings, configuracao):
    settings.FREENFSE_CHAVES = configuracao

    with pytest.raises(crypto.ErroDeConfiguracaoDeChaves) as erro:
        crypto.cifrar_texto("x")

    assert CHAVE_1 not in str(erro.value)


def test_tipos_errados_sao_recusados(settings):
    settings.FREENFSE_CHAVES = [f"1:{CHAVE_1}"]

    with pytest.raises(crypto.ErroDeCriptografia):
        crypto.cifrar_texto(b"bytes")
    with pytest.raises(crypto.ErroDeCriptografia):
        crypto.cifrar_bytes("texto")
