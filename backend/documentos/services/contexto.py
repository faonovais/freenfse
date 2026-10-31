"""Apoio comum dos serviços de documentos: empresa ativa, relógio e intervalos de retentativa."""

import datetime as dt

from django.db import connection
from django.utils import timezone

from core.models import Empresa

# Esperas antes da 2ª, 3ª, 4ª… tentativa (a 1ª é imediata). Persistidas em `proxima_tentativa`.
INTERVALOS_DE_RETENTATIVA = (
    dt.timedelta(minutes=1),
    dt.timedelta(minutes=5),
    dt.timedelta(minutes=30),
    dt.timedelta(hours=2),
    dt.timedelta(hours=6),
)
# Quanto tempo uma tentativa "reservada" por um processo vale antes de outro poder refazê-la.
RESERVA_DA_TENTATIVA = dt.timedelta(minutes=10)


def empresa_atual():
    """Empresa do schema ativo (os sinais e as tarefas já rodam dentro dele)."""
    return Empresa.objects.get(schema_name=connection.schema_name)


def agora():
    """Instante atual (ponto de troca dos testes)."""
    return timezone.now()


def espera_apos(tentativas):
    """Espera antes de tentar de novo, dado quantas tentativas já falharam (a última se repete)."""
    indice = min(max(tentativas, 1), len(INTERVALOS_DE_RETENTATIVA)) - 1
    return INTERVALOS_DE_RETENTATIVA[indice]
