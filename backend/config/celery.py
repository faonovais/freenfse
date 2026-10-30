"""Aplicação Celery do freenfse (fila de tarefas assíncronas sobre Redis)."""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("freenfse")
# Todas as chaves CELERY_* do settings.py configuram a aplicação.
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
