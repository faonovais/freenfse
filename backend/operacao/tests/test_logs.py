"""Logs estruturados sem segredos nem dados pessoais desnecessários (Fase 6, ADR 0008)."""

import io
import json
import logging
import logging.config

import pytest
from django.conf import settings

from core import crypto
from operacao import logs

CHAVE = crypto.gerar_chave()
SENHA_DO_BANCO = "senha-do-banco-do-teste-9f3a"
CPF = "123.456.789-09"
CPF_SEM_PONTOS = "98765432100"
EMAIL = "maria.silva@tomador-exemplo.com.br"
# Montado em pedaços: o valor é falso, mas o texto contínuo imita um segredo de OAuth e o
# gitleaks (que varre o histórico) o apontaria.
SEGREDO_OAUTH = "GOCSPX-" + "abcdef123456"


@pytest.fixture(autouse=True)
def _segredos_conhecidos(settings, monkeypatch):
    settings.SECRET_KEY = "chave-secreta-do-django-do-teste-77aa"
    settings.FREENFSE_CHAVES = [f"2:{CHAVE}", "1:" + crypto.gerar_chave()]
    monkeypatch.setenv("POSTGRES_PASSWORD", SENHA_DO_BANCO)  # como chega pela instalação


def _registro(mensagem, *args, exc_info=None, nivel=logging.ERROR):
    return logging.LogRecord("teste", nivel, __file__, 1, mensagem, args, exc_info)


def _formatar(mensagem, *args, **extra):
    return logs.FormatadorJson().format(_registro(mensagem, *args, **extra))


def test_o_evento_e_uma_linha_json_com_os_campos_basicos():
    linha = _formatar("Nota %s autorizada", 42, nivel=logging.INFO)

    evento = json.loads(linha)
    assert "\n" not in linha
    assert set(evento) == {"ts", "nivel", "logger", "mensagem"}
    assert evento["nivel"] == "INFO" and evento["logger"] == "teste"
    assert evento["mensagem"] == "Nota 42 autorizada"
    assert evento["ts"].endswith("+00:00")


def test_texto_vindo_de_fora_nao_forja_linhas_de_log():
    linha = _formatar('falha\n{"nivel": "INFO", "mensagem": "tudo certo"}')

    assert "\n" not in linha
    assert len(linha.splitlines()) == 1
    assert json.loads(linha)["mensagem"].startswith("falha\n")


@pytest.mark.parametrize(
    "texto",
    [
        f"erro com {settings.SECRET_KEY}",
        f"chave {CHAVE} no meio",
        f"1:{CHAVE}",
        f"postgres://freenfse:{SENHA_DO_BANCO}@banco:5432/freenfse",
        f"falha ao conectar com {SENHA_DO_BANCO}",
    ],
)
def test_os_valores_reais_dos_segredos_da_instalacao_sao_mascarados(texto):
    saida = _formatar(texto)

    for segredo in ("chave-secreta-do-django-do-teste-77aa", CHAVE, SENHA_DO_BANCO):
        assert segredo not in saida
    assert logs.MASCARA in saida


@pytest.mark.parametrize(
    ("texto", "segredo"),
    [
        ("senha=abc12345def", "abc12345def"),
        ('{"password": "supersecreta123"}', "supersecreta123"),
        ("token: ghp_abcdefghijklmnop", "ghp_abcdefghijklmnop"),
        ("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.abc.def", "eyJhbGciOiJIUzI1NiJ9"),
        ("redis://:minha-senha-redis@cache:6379/0", "minha-senha-redis"),
        ("AGE-SECRET-KEY-1QQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQ", "AGE-SECRET-KEY"),
        (
            "-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBgkqhkiG9w0BAQE\n-----END PRIVATE KEY-----",
            "MIIEvQIBADANBgkqhkiG9w0BAQE",
        ),
        ("client_secret=" + SEGREDO_OAUTH, SEGREDO_OAUTH),
    ],
)
def test_padroes_de_segredo_sao_mascarados_mesmo_sem_conhecer_o_valor(texto, segredo):
    saida = _formatar(texto)

    assert segredo not in saida


def test_cpf_e_email_nao_vao_para_o_log():
    saida = _formatar(f"Tomador {CPF} / {CPF_SEM_PONTOS} contato {EMAIL}")

    for pessoal in (CPF, CPF_SEM_PONTOS, "maria.silva"):
        assert pessoal not in saida
    assert "@tomador-exemplo.com.br" in saida  # o domínio ajuda a diagnosticar e não identifica


def test_numeros_que_nao_sao_cpf_continuam_legiveis():
    chave_de_acesso = "29034012" + "0" * 42  # 50 dígitos
    saida = _formatar(f"Nota {chave_de_acesso} valor 1234.56 número 98765")

    assert chave_de_acesso in saida and "1234.56" in saida and "98765" in saida


def test_a_excecao_tambem_e_mascarada():
    try:
        raise ValueError(f"não consegui autenticar o CPF {CPF} com a senha={SENHA_DO_BANCO}x")
    except ValueError:
        import sys

        linha = _formatar("Falhou", exc_info=sys.exc_info())

    evento = json.loads(linha)
    assert "ValueError" in evento["excecao"] and "Traceback" in evento["excecao"]
    assert CPF not in linha and SENHA_DO_BANCO not in linha


def test_o_filtro_mascara_para_qualquer_formatador():
    fluxo = io.StringIO()
    manipulador = logging.StreamHandler(fluxo)
    manipulador.setFormatter(logging.Formatter("%(message)s"))
    manipulador.addFilter(logs.FiltroDeSegredos())
    registrador = logging.getLogger("teste.filtro")
    registrador.handlers = [manipulador]
    registrador.propagate = False

    registrador.error("senha=%s do CPF %s", "abc12345def", CPF)

    assert "abc12345def" not in fluxo.getvalue() and CPF not in fluxo.getvalue()


def test_a_configuracao_da_aplicacao_liga_o_json_e_o_filtro_de_segredos():
    """O `LOGGING` real: o manipulador padrão usa o formatador JSON e o filtro de segredos."""
    config = settings.LOGGING

    assert config["formatters"]["json"]["()"] == "operacao.logs.FormatadorJson"
    assert config["filters"]["segredos"]["()"] == "operacao.logs.FiltroDeSegredos"
    console = config["handlers"]["console"]
    assert console["filters"] == ["segredos"]
    assert console["formatter"] in {"json", "texto"} and settings.LOG_FORMATO in {"json", "texto"}
    assert config["root"]["handlers"] == ["console"]


def test_de_ponta_a_ponta_a_configuracao_real_nao_deixa_o_segredo_passar():
    """Aplica o `LOGGING` da aplicação (trocando só o destino do fluxo) e registra um segredo."""
    fluxo = io.StringIO()
    config = json.loads(json.dumps(settings.LOGGING))  # cópia
    config["formatters"]["json"] = {"()": "operacao.logs.FormatadorJson"}
    config["filters"]["segredos"] = {"()": "operacao.logs.FiltroDeSegredos"}
    config["handlers"]["console"]["stream"] = fluxo
    config["handlers"]["console"]["formatter"] = "json"
    config["root"]["level"] = "INFO"
    logging.config.dictConfig(config)
    try:
        logging.getLogger("fiscal.emissao").error(
            "Falha ao enviar para %s com senha=%s e %s", EMAIL, SENHA_DO_BANCO, CPF
        )
    finally:
        logging.config.dictConfig(settings.LOGGING)

    linha = fluxo.getvalue().strip()
    evento = json.loads(linha)
    assert evento["logger"] == "fiscal.emissao" and evento["nivel"] == "ERROR"
    for segredo in (SENHA_DO_BANCO, CPF, "maria.silva"):
        assert segredo not in linha


def test_o_worker_do_celery_nao_troca_a_configuracao_de_logs():
    assert settings.CELERY_WORKER_HIJACK_ROOT_LOGGER is False
