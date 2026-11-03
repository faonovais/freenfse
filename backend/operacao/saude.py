"""Estado de saúde da instalação: banco, Redis, worker, agendador (beat) e backup.

Cada verificação é uma função pequena e independente (fácil de trocar nos testes) e devolve só
uma palavra de estado: nunca versão, endereço, usuário nem mensagem de erro do servidor.

* `banco` e `redis`: sem eles a aplicação não atende → `falha` (HTTP 503 no endpoint);
* `worker`: responde ao `ping` do Celery; `agendador`: o beat enfileira todo minuto um
  batimento que o worker grava no Redis — batimento recente prova a cadeia beat → fila → worker;
* `backup`: o último backup tem menos de 30 h. Estes três só *degradam* (HTTP 200).
"""

import datetime as dt
import logging
import time

import redis
from django.conf import settings
from django.db import connection

from operacao import backup

logger = logging.getLogger(__name__)

CHAVE_DO_BATIMENTO = "freenfse:batimento"
VALIDADE_DO_BATIMENTO = 600  # segundos que a marca fica no Redis
IDADE_MAXIMA_DO_BATIMENTO = 180  # segundos: o beat bate todo minuto
IDADE_MAXIMA_DO_BACKUP = dt.timedelta(hours=30)  # backup diário + folga


def _redis():
    return redis.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=2, socket_timeout=2)


def verificar_banco():
    """`ok` se o banco responde a uma consulta simples."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        logger.exception("Verificação de saúde: banco indisponível.")
        return "falha"
    return "ok"


def verificar_redis():
    """`ok` se o Redis responde ao PING."""
    try:
        return "ok" if _redis().ping() else "falha"
    except Exception:
        logger.exception("Verificação de saúde: Redis indisponível.")
        return "falha"


def verificar_worker():
    """`ok` se pelo menos um worker do Celery responde ao ping."""
    from config.celery import app

    try:
        respostas = app.control.ping(timeout=1.0)
    except Exception:
        logger.exception("Verificação de saúde: não foi possível consultar o worker.")
        return "falha"
    return "ok" if respostas else "falha"


def registrar_batimento(agora=None):
    """Grava no Redis o instante do último batimento do agendador (chamado por tarefa do beat)."""
    agora = agora or dt.datetime.now(dt.UTC)
    _redis().setex(CHAVE_DO_BATIMENTO, VALIDADE_DO_BATIMENTO, agora.isoformat())


def idade_do_batimento(agora=None):
    """Segundos desde o último batimento, ou `None` se nunca houve (ou expirou)."""
    agora = agora or dt.datetime.now(dt.UTC)
    valor = _redis().get(CHAVE_DO_BATIMENTO)
    if not valor:
        return None
    return (agora - dt.datetime.fromisoformat(valor.decode())).total_seconds()


def verificar_agendador(agora=None):
    """`ok` se o batimento é recente, `atrasado` se parou, `falha` se o Redis não responde."""
    try:
        idade = idade_do_batimento(agora)
    except Exception:
        return "falha"
    if idade is None or idade > IDADE_MAXIMA_DO_BATIMENTO:
        return "atrasado"
    return "ok"


def verificar_backup(agora=None):
    """`nao_configurado`, `sem_backup`, `atrasado` ou `ok`."""
    agora = agora or dt.datetime.now(dt.UTC)
    try:
        config = backup.config_do_ambiente()
        if not config.destinatarios:
            return "nao_configurado"
        ultimo = backup.ultimo_backup(config.pasta)
    except Exception:
        logger.exception("Verificação de saúde: não foi possível ler os backups.")
        return "falha"
    if not ultimo or not ultimo.get("criado_em"):
        return "sem_backup"
    criado = dt.datetime.fromisoformat(ultimo["criado_em"])
    return "ok" if agora - criado <= IDADE_MAXIMA_DO_BACKUP else "atrasado"


_MEMO = {"quando": None, "resposta": None}


def esquecer_memo():
    """Descarta a última resposta guardada (usado nos testes)."""
    _MEMO.update(quando=None, resposta=None)


def estado(*, com_memo=False, relogio=time.monotonic):
    """`(status, componentes)`: `ok`, `degradado` (algo secundário) ou `falha` (banco/Redis).

    O endpoint é público e cada verificação faz trabalho de verdade (consulta ao banco, ao Redis e
    um `ping` no Celery de até 1 s). Com `com_memo`, a última resposta vale por
    `FREENFSE_SAUDE_CACHE_SEGUNDOS` (por processo): quem martela o endpoint não multiplica o custo.
    """
    validade = getattr(settings, "FREENFSE_SAUDE_CACHE_SEGUNDOS", 0)
    agora = relogio()
    if com_memo and validade and _MEMO["quando"] is not None:
        if agora - _MEMO["quando"] < validade:
            return _MEMO["resposta"]
    resposta = _calcular_estado()
    if com_memo and validade:
        _MEMO.update(quando=agora, resposta=resposta)
    return resposta


def _calcular_estado():
    componentes = {
        "banco": verificar_banco(),
        "redis": verificar_redis(),
        "worker": verificar_worker(),
        "agendador": verificar_agendador(),
        "backup": verificar_backup(),
    }
    if componentes["banco"] != "ok" or componentes["redis"] != "ok":
        return "falha", componentes
    if any(componentes[nome] != "ok" for nome in ("worker", "agendador", "backup")):
        return "degradado", componentes
    return "ok", componentes
