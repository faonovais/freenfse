from config.celery import app
from core.tasks import ping


def test_aplicacao_celery_le_configuracao_do_django(settings):
    assert app.conf.broker_url == settings.CELERY_BROKER_URL
    assert app.conf.timezone == "America/Sao_Paulo"


def test_task_ping_executa_localmente():
    assert ping.apply().get() == "pong"
