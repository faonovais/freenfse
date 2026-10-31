"""Endpoint de saúde, batimento do agendador e sonda do beat (Fase 6; pendência da issue #10)."""

import datetime as dt
import io
import json

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client

from operacao import backup, saude

AGORA = dt.datetime(2026, 11, 1, 12, 0, tzinfo=dt.UTC)


class RedisFalso:
    """Substituto mínimo do cliente Redis (o CI não tem Redis no job do backend)."""

    def __init__(self, com_defeito=False):
        self.valores = {}
        self.com_defeito = com_defeito

    def _checar(self):
        if self.com_defeito:
            raise ConnectionError("redis fora do ar: redis://:segredo@cache:6379")

    def ping(self):
        self._checar()
        return True

    def setex(self, chave, _validade, valor):
        self._checar()
        self.valores[chave] = valor.encode()

    def get(self, chave):
        self._checar()
        return self.valores.get(chave)


@pytest.fixture
def redis_falso(monkeypatch):
    falso = RedisFalso()
    monkeypatch.setattr(saude, "_redis", lambda: falso)
    return falso


def _tudo_ok(monkeypatch):
    for nome in ("verificar_banco", "verificar_redis", "verificar_worker", "verificar_agendador"):
        monkeypatch.setattr(saude, nome, lambda: "ok")
    monkeypatch.setattr(saude, "verificar_backup", lambda: "ok")


# -- o endpoint ----------------------------------------------------------------------------------


@pytest.mark.django_db
def test_tudo_certo_responde_200_ok_sem_exigir_login_nem_empresa(monkeypatch):
    _tudo_ok(monkeypatch)

    resposta = Client().get("/api/saude/")

    assert resposta.status_code == 200
    assert resposta.json() == {
        "status": "ok",
        "banco": "ok",
        "redis": "ok",
        "worker": "ok",
        "agendador": "ok",
        "backup": "ok",
    }
    assert Client().head("/api/saude/").status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize("quebrado", ["verificar_banco", "verificar_redis"])
def test_banco_ou_redis_fora_responde_503_falha(monkeypatch, quebrado):
    _tudo_ok(monkeypatch)
    monkeypatch.setattr(saude, quebrado, lambda: "falha")

    resposta = Client().get("/api/saude/")

    assert resposta.status_code == 503 and resposta.json()["status"] == "falha"


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("quebrado", "estado"),
    [
        ("verificar_worker", "falha"),
        ("verificar_agendador", "atrasado"),
        ("verificar_backup", "atrasado"),
        ("verificar_backup", "nao_configurado"),
        ("verificar_backup", "sem_backup"),
    ],
)
def test_worker_agendador_ou_backup_com_problema_so_degradam(monkeypatch, quebrado, estado):
    _tudo_ok(monkeypatch)
    monkeypatch.setattr(saude, quebrado, lambda: estado)

    resposta = Client().get("/api/saude/")

    assert resposta.status_code == 200 and resposta.json()["status"] == "degradado"
    assert resposta.json()[quebrado.removeprefix("verificar_")] == estado


@pytest.mark.django_db
def test_a_resposta_so_traz_palavras_de_estado(monkeypatch):
    _tudo_ok(monkeypatch)
    monkeypatch.setattr(saude, "verificar_banco", lambda: "falha")

    corpo = Client().get("/api/saude/").content.decode()

    for proibido in ("senha", "postgres", "localhost", "Traceback", "versao", "5432"):
        assert proibido.lower() not in corpo.lower()


# -- verificações individuais --------------------------------------------------------------------


@pytest.mark.django_db
def test_o_banco_responde(monkeypatch):
    assert saude.verificar_banco() == "ok"

    def quebrado():
        raise RuntimeError("sem banco")

    monkeypatch.setattr(saude.connection, "cursor", quebrado)
    assert saude.verificar_banco() == "falha"


def test_o_redis_responde_ou_falha_sem_vazar_o_erro(redis_falso, caplog):
    assert saude.verificar_redis() == "ok"
    redis_falso.com_defeito = True

    assert saude.verificar_redis() == "falha"


@pytest.mark.parametrize(
    ("resposta", "esperado"), [([{"celery@w": {"ok": "pong"}}], "ok"), ([], "falha")]
)
def test_o_worker_responde_ao_ping_do_celery(monkeypatch, resposta, esperado):
    from config.celery import app

    monkeypatch.setattr(app.control, "ping", lambda timeout: resposta)

    assert saude.verificar_worker() == esperado


def test_erro_ao_consultar_o_worker_e_falha(monkeypatch):
    from config.celery import app

    def quebrado(timeout):
        raise OSError("broker fora")

    monkeypatch.setattr(app.control, "ping", quebrado)

    assert saude.verificar_worker() == "falha"


# -- agendador (beat) ----------------------------------------------------------------------------


def test_batimento_recente_e_ok_e_velho_ou_ausente_e_atrasado(redis_falso):
    assert saude.verificar_agendador(AGORA) == "atrasado"  # nunca bateu

    saude.registrar_batimento(AGORA - dt.timedelta(seconds=60))
    assert saude.verificar_agendador(AGORA) == "ok"

    saude.registrar_batimento(AGORA - dt.timedelta(seconds=saude.IDADE_MAXIMA_DO_BATIMENTO + 1))
    assert saude.verificar_agendador(AGORA) == "atrasado"


def test_redis_fora_derruba_a_verificacao_do_agendador(redis_falso):
    redis_falso.com_defeito = True

    assert saude.verificar_agendador(AGORA) == "falha"


def test_a_tarefa_do_beat_grava_o_batimento_e_esta_agendada_todo_minuto(redis_falso, settings):
    from operacao import tasks

    tasks.batimento()

    assert saude.idade_do_batimento() < 5
    entrada = settings.CELERY_BEAT_SCHEDULE["batimento-do-agendador"]
    assert entrada["task"] == "operacao.tasks.batimento"
    assert entrada["schedule"].minute == set(range(60))


def test_a_sonda_do_beat_passa_com_batimento_recente(redis_falso):
    saude.registrar_batimento()
    saida = io.StringIO()

    call_command("verificar_batimento", stdout=saida)

    assert "Agendador ok" in saida.getvalue()


def test_a_sonda_do_beat_falha_sem_batimento_ou_com_batimento_velho(redis_falso):
    with pytest.raises(CommandError, match="ainda não bateu"):
        call_command("verificar_batimento", stdout=io.StringIO())

    saude.registrar_batimento(dt.datetime.now(dt.UTC) - dt.timedelta(seconds=500))
    with pytest.raises(CommandError, match="último batimento"):
        call_command("verificar_batimento", stdout=io.StringIO())


def test_a_sonda_do_beat_falha_se_o_redis_estiver_fora(redis_falso):
    redis_falso.com_defeito = True

    with pytest.raises(CommandError, match="Redis fora do ar") as erro:
        call_command("verificar_batimento", stdout=io.StringIO())

    assert "segredo" not in str(erro.value)


# -- backup --------------------------------------------------------------------------------------


def _manifesto(pasta, momento):
    nome = f"{backup.PREFIXO}{momento.strftime(backup.FORMATO_DO_NOME)}{backup.SUFIXO}"
    (pasta / nome).write_bytes(b"x")
    (pasta / f"{nome}.json").write_text(
        json.dumps({"arquivo": nome, "criado_em": momento.isoformat()})
    )


@pytest.fixture
def backup_configurado(settings, tmp_path):
    settings.FREENFSE_BACKUP_DIR = str(tmp_path)
    settings.FREENFSE_BACKUP_DESTINATARIO = "age1" + "q" * 58
    return tmp_path


def test_backup_nao_configurado_sem_chave_publica(settings, tmp_path):
    settings.FREENFSE_BACKUP_DIR = str(tmp_path)
    settings.FREENFSE_BACKUP_DESTINATARIO = ""

    assert saude.verificar_backup(AGORA) == "nao_configurado"


def test_backup_configurado_sem_nenhum_arquivo(backup_configurado):
    assert saude.verificar_backup(AGORA) == "sem_backup"


def test_backup_recente_ok_e_de_ontem_atrasado(backup_configurado):
    _manifesto(backup_configurado, AGORA - dt.timedelta(hours=20))
    assert saude.verificar_backup(AGORA) == "ok"

    assert saude.verificar_backup(AGORA + dt.timedelta(hours=12)) == "atrasado"
