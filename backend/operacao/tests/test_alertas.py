"""Alertas da plataforma (backup) e a rotina que roda todos os alertas (Fase 6)."""

import datetime as dt
import smtplib

import pytest
from django.core.cache import cache

from core.models import Usuario
from documentos.tests.simulados import ServidorSmtpFalso
from operacao import alertas, backup, saude, tasks

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _limpar_cache():
    cache.clear()


@pytest.fixture
def master(db):
    return Usuario.objects.create_superuser(email="dono@exemplo.test", password="x" * 14)


@pytest.fixture
def smtp(settings, monkeypatch):
    """SMTP do sistema configurado, com o servidor trocado por um falso (nada sai para a rede)."""
    settings.ALERTAS_SMTP_HOST = "smtp.exemplo.test"
    settings.ALERTAS_EMAIL_DE = "alertas@exemplo.test"
    servidor = ServidorSmtpFalso()
    original = alertas.ProvedorSmtp

    def com_servidor_falso(**dados):
        return original(**dados, fabrica=servidor)

    monkeypatch.setattr(alertas, "ProvedorSmtp", com_servidor_falso)
    return servidor


def test_backup_que_falhou_avisa_os_master_por_email(master, smtp, settings):
    settings.ALERTAS_EMAIL_PARA = []

    enviou = alertas.alertar_backup_falhou("O pg_dump falhou: sem espaço em disco.")

    assert enviou is True
    (mensagem,) = smtp.mensagens
    assert mensagem["para"] == ["dono@exemplo.test"] and mensagem["de"] == "alertas@exemplo.test"
    assert mensagem["mime"]["Subject"] == "[freenfse] O backup do banco falhou"
    assert "sem espaço em disco" in mensagem["mime"].get_body(("plain",)).get_content()


def test_os_destinatarios_podem_ser_definidos_no_ambiente(master, smtp, settings):
    settings.ALERTAS_EMAIL_PARA = ["ti@exemplo.test", "ti@exemplo.test", "dono2@exemplo.test"]

    alertas.alertar_backup_falhou("erro")

    assert smtp.mensagens[0]["para"] == ["dono2@exemplo.test", "ti@exemplo.test"]


def test_um_alerta_por_problema_por_dia(master, smtp):
    assert alertas.alertar_backup_falhou("erro") is True
    assert alertas.alertar_backup_falhou("erro de novo") is False

    assert len(smtp.mensagens) == 1


def test_sem_smtp_do_sistema_o_alerta_vai_para_o_log_critico(master, settings, caplog):
    settings.ALERTAS_SMTP_HOST = ""

    with caplog.at_level("CRITICAL"):
        enviou = alertas.alertar_backup_falhou("erro")

    assert enviou is False
    assert any("não enviado" in r.getMessage() for r in caplog.records)


def test_falha_no_envio_do_alerta_nao_derruba_a_rotina(master, smtp):
    smtp.falha = smtplib.SMTPServerDisconnected("smtp fora")

    assert alertas.alertar_backup_falhou("erro") is False


def test_a_tarefa_de_backup_que_falha_dispara_o_alerta(master, smtp, settings, tmp_path):
    settings.FREENFSE_BACKUP_DIR = str(tmp_path)
    settings.FREENFSE_BACKUP_DESTINATARIO = ""  # sem chave pública: o backup recusa

    with pytest.raises(backup.ErroDeBackup):
        tasks.fazer_backup()

    (mensagem,) = smtp.mensagens
    assert "chave pública do backup" in mensagem["mime"].get_body(("plain",)).get_content()


def test_backup_atrasado_avisa_uma_vez(master, smtp, monkeypatch):
    monkeypatch.setattr(saude, "verificar_backup", lambda: "atrasado")

    assert alertas.verificar_backup_atrasado() is True
    assert alertas.verificar_backup_atrasado() is False
    assert "mais de 30 horas" in smtp.mensagens[0]["mime"].get_body(("plain",)).get_content()


@pytest.mark.parametrize("estado", ["ok", "nao_configurado"])
def test_backup_em_dia_ou_nao_configurado_nao_gera_alerta(master, smtp, monkeypatch, estado):
    monkeypatch.setattr(saude, "verificar_backup", lambda: estado)

    assert alertas.verificar_backup_atrasado() is False
    assert smtp.mensagens == []


def test_a_rotina_percorre_as_empresas_e_a_plataforma(empresa_a, empresa_b, monkeypatch):
    monkeypatch.setattr(saude, "verificar_backup", lambda: "ok")

    resumo = tasks.verificar_alertas()

    assert resumo == {"emissoes": 0, "falhas": 0, "backup": False}


def test_a_rotina_dos_alertas_esta_no_beat_de_hora_em_hora(settings):
    entrada = settings.CELERY_BEAT_SCHEDULE["verificar-alertas-operacionais"]
    assert entrada["task"] == "operacao.tasks.verificar_alertas"
    assert entrada["schedule"].minute == {35} and entrada["schedule"].hour == set(range(24))
    assert dt.timedelta(hours=1)  # a cada hora cheia, no minuto 35
