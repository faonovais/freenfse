"""Validação dos parâmetros e perguntas interativas."""

import pytest
from freenfse_instalador import parametros
from freenfse_instalador.parametros import ErroDeParametro, Parametros

CHAVE_AGE = "age1" + "q" * 58


def _p(**ajustes):
    base = {"modo": "compose", "dominio": "nfse.exemplo.com.br"}
    base.update(ajustes)
    return Parametros(**base)


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("NFSE.Exemplo.com.br", "nfse.exemplo.com.br"),
        ("servidor-interno", "servidor-interno"),
        ("192.168.0.10", "192.168.0.10"),
    ],
)
def test_dominio_valido_e_normalizado(entrada, esperado):
    assert parametros.validar_dominio(entrada) == esperado


@pytest.mark.parametrize(
    "entrada",
    ["", "https://nfse.exemplo.com.br", "nfse.exemplo.com.br/", "a b.com", "-x.com", "x_y.com"],
)
def test_dominio_invalido_e_recusado_com_orientacao(entrada):
    with pytest.raises(ErroDeParametro):
        parametros.validar_dominio(entrada)


@pytest.mark.parametrize("porta", ["0", "70000", "abc", None])
def test_porta_invalida(porta):
    with pytest.raises(ErroDeParametro):
        parametros.validar_porta(porta, "HTTP")


def test_letsencrypt_exige_email_dominio_publico_e_porta_80():
    with pytest.raises(ErroDeParametro, match="e-mail"):
        parametros.validar(_p(tls="letsencrypt"))
    for dominio in ("10.0.0.5", "servidor", "nfse.empresa.local"):
        with pytest.raises(ErroDeParametro, match="domínio público"):
            parametros.validar(_p(tls="letsencrypt", email="ti@exemplo.com.br", dominio=dominio))
    with pytest.raises(ErroDeParametro, match="porta 80"):
        parametros.validar(_p(tls="letsencrypt", email="ti@exemplo.com.br", porta_http=8080))

    ok = parametros.validar(_p(tls="letsencrypt", email="ti@exemplo.com.br"))
    assert ok.https and ok.url == "https://nfse.exemplo.com.br"


def test_certificado_proprio_exige_os_dois_arquivos_existentes(tmp_path):
    with pytest.raises(ErroDeParametro, match="--certificado"):
        parametros.validar(_p(tls="proprio"))
    with pytest.raises(ErroDeParametro, match="não encontrado"):
        parametros.validar(
            _p(tls="proprio", certificado=tmp_path / "x.pem", chave_privada=tmp_path / "y.pem")
        )
    cert, chave = tmp_path / "c.pem", tmp_path / "k.pem"
    cert.write_text("c"), chave.write_text("k")
    assert parametros.validar(_p(tls="proprio", certificado=cert, chave_privada=chave)).https


def test_so_a_chave_publica_do_backup_e_aceita():
    assert parametros.validar(_p(chave_publica_backup=CHAVE_AGE)).chave_publica_backup == CHAVE_AGE
    with pytest.raises(ErroDeParametro, match="PÚBLICA") as erro:
        parametros.validar(_p(chave_publica_backup="AGE-SECRET-KEY-1ABCDEF"))
    assert "AGE-SECRET-KEY-1ABCDEF" not in str(erro.value)  # nem ecoa o valor recusado


def test_chave_de_backup_ou_gerar_nao_os_dois(tmp_path):
    with pytest.raises(ErroDeParametro, match="não os dois"):
        parametros.validar(_p(chave_publica_backup=CHAVE_AGE, gerar_chave_backup=tmp_path / "k"))


def test_dados_precisa_ser_caminho_absoluto():
    with pytest.raises(ErroDeParametro, match="absoluto"):
        parametros.validar(_p(dados="relativo/dados"))


def test_url_com_portas_nao_padrao():
    assert _p(porta_http=8080).url == "http://nfse.exemplo.com.br:8080"
    assert _p(tls="proprio", porta_https=8443).url == "https://nfse.exemplo.com.br:8443"


def test_modo_interativo_pergunta_o_que_falta():
    respostas = iter(["NFSE.Teste.com.br", "letsencrypt", "ti@teste.com.br", ""])

    p = parametros.ler_argumentos(["compose", "--simular"], entrada=lambda _: next(respostas))

    assert (
        p.dominio == "nfse.teste.com.br" and p.tls == "letsencrypt" and p.email == "ti@teste.com.br"
    )
    assert str(p.dados) == "/var/lib/freenfse"


def test_pergunta_de_novo_quando_a_resposta_e_invalida(capsys):
    respostas = iter(["http://errado", "certo.exemplo.com.br"])

    valor = parametros.perguntar(
        "Domínio", validador=parametros.validar_dominio, entrada=lambda _: next(respostas)
    )

    assert valor == "certo.exemplo.com.br" and "não parece um domínio" in capsys.readouterr().out


def test_nao_interativo_nao_pergunta_e_exige_o_dominio():
    with pytest.raises(ErroDeParametro, match="Informe o domínio"):
        parametros.ler_argumentos(
            ["compose", "--nao-interativo", "--simular"], entrada=lambda _: 1 / 0
        )
