"""Configurações dos testes: as da aplicação mais o app de apoio, chaves e cache locais."""

import os

os.environ.setdefault("SECRET_KEY", "chave-ficticia-somente-para-testes")

from .settings import *  # noqa: E402, F403

TENANT_APPS = [*TENANT_APPS, "apoio_testes"]  # noqa: F405
INSTALLED_APPS = [*INSTALLED_APPS, "apoio_testes"]  # noqa: F405
ROOT_URLCONF = "config.urls_testes"

# Chaves fictícias, geradas para os testes (nunca usadas fora deles).
FREENFSE_CHAVES = [
    "1:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
]

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Os testes de 2FA ligam a política explicitamente; nos demais, o Master entra sem 2FA.
AUTH_EXIGIR_2FA_MASTER = False
AUTH_EXIGIR_2FA_TODOS = False
