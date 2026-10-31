"""`.env`: geração, permissão 600, idempotência e segredos que nunca mudam."""

import base64
import os
import stat

from freenfse_instalador import segredos

SEGREDOS_DO_ENV = ("SECRET_KEY", "POSTGRES_PASSWORD", "FREENFSE_CHAVES")


def _modo(caminho):
    return stat.S_IMODE(os.stat(caminho).st_mode)


def test_cria_o_env_com_segredos_fortes_e_permissao_600(tmp_path):
    caminho = tmp_path / "pasta" / ".env"
    valores, gerados = segredos.montar_valores({}, {"ALLOWED_HOSTS": "x.test"})

    segredos.escrever_env(caminho, valores)

    assert _modo(caminho) == 0o600
    lido = segredos.ler_env(caminho)
    assert set(gerados) == {
        "SECRET_KEY",
        "POSTGRES_PASSWORD",
        "FREENFSE_CHAVES",
        "FREENFSE_BI_SENHA",
    }
    assert len(lido["SECRET_KEY"]) >= 64 and len(lido["POSTGRES_PASSWORD"]) >= 24
    versao, _, chave = lido["FREENFSE_CHAVES"].partition(":")
    assert versao == "1" and len(base64.urlsafe_b64decode(chave)) == 32
    assert lido["ALLOWED_HOSTS"] == "x.test"


def test_os_segredos_sao_diferentes_a_cada_instalacao():
    um, _ = segredos.montar_valores({}, {})
    outro, _ = segredos.montar_valores({}, {})

    for nome in SEGREDOS_DO_ENV:
        assert um[nome] != outro[nome]


def test_segredo_existente_nunca_e_trocado(tmp_path):
    caminho = tmp_path / ".env"
    primeiro, _ = segredos.montar_valores({}, {"HTTP_PORT": "80"})
    segredos.escrever_env(caminho, primeiro)
    antes = segredos.ler_env(caminho)

    segundo, gerados = segredos.montar_valores(
        antes, {"HTTP_PORT": "8080", "SECRET_KEY": "forcado"}
    )
    segredos.escrever_env(caminho, segundo)

    depois = segredos.ler_env(caminho)
    assert gerados == []
    for nome in SEGREDOS_DO_ENV:
        assert depois[nome] == antes[nome]  # nem o 'forcado' vence um segredo já gravado
    assert depois["HTTP_PORT"] == "8080"  # o que não é segredo acompanha o pedido


def test_chaves_com_rotacao_em_andamento_sao_preservadas(tmp_path):
    caminho = tmp_path / ".env"
    caminho.write_text("FREENFSE_CHAVES=2:novachave,1:antigachave\nSECRET_KEY=abc\n")
    existente = segredos.ler_env(caminho)

    valores, gerados = segredos.montar_valores(existente, {})
    segredos.escrever_env(caminho, valores)

    assert segredos.ler_env(caminho)["FREENFSE_CHAVES"] == "2:novachave,1:antigachave"
    assert "FREENFSE_CHAVES" not in gerados


def test_preserva_comentarios_e_chaves_que_o_instalador_nao_conhece(tmp_path):
    caminho = tmp_path / ".env"
    caminho.write_text("# meu comentario\nCHAVE_MINHA=1\nHTTP_PORT=9\n# HTTPS_PORT=1\n")

    segredos.escrever_env(caminho, {"HTTP_PORT": "80", "HTTPS_PORT": "443", "NOVA": "x"})

    texto = caminho.read_text()
    assert "# meu comentario" in texto and "CHAVE_MINHA=1" in texto
    assert segredos.ler_env(caminho) == {
        "CHAVE_MINHA": "1",
        "HTTP_PORT": "80",
        "HTTPS_PORT": "443",
        "NOVA": "x",
    }
    for nome in ("HTTP_PORT=", "HTTPS_PORT=", "NOVA="):
        assert texto.count(nome) == 1  # nenhuma chave duplicada


def test_a_linha_ativa_vence_o_exemplo_comentado_sem_duplicar_a_chave(tmp_path):
    caminho = tmp_path / ".env"
    caminho.write_text("# COOKIES_SEGUROS=true\nCOOKIES_SEGUROS=false\n")

    segredos.escrever_env(caminho, {"COOKIES_SEGUROS": "true"})

    linhas = [linha for linha in caminho.read_text().splitlines() if "COOKIES_SEGUROS" in linha]
    assert linhas == ["# COOKIES_SEGUROS=true", "COOKIES_SEGUROS=true"]
    assert segredos.ler_env(caminho)["COOKIES_SEGUROS"] == "true"


def test_apertar_a_permissao_de_um_env_antigo_aberto_demais(tmp_path):
    caminho = tmp_path / ".env"
    caminho.write_text("SECRET_KEY=abc\n")
    os.chmod(caminho, 0o644)

    segredos.escrever_env(caminho, {"HTTP_PORT": "80"})

    assert _modo(caminho) == 0o600


def test_mascarar_troca_o_segredo_onde_quer_que_apareca():
    texto = segredos.mascarar(
        "a senha SEGREDO-LONGO-123 e outra OUTRA-SENHA-9 aqui",
        ["SEGREDO-LONGO-123", "OUTRA-SENHA-9", ""],
    )

    assert "SEGREDO" not in texto and "OUTRA" not in texto and texto.count("***") == 2


def test_verificador_scram_tem_o_formato_e_nao_revela_a_senha():
    verificador = segredos.verificador_scram("uma-senha-bem-longa-123")

    assert verificador.startswith("SCRAM-SHA-256$4096:") and "uma-senha" not in verificador
    assert verificador != segredos.verificador_scram("uma-senha-bem-longa-123")
