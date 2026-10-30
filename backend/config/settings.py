"""Configurações do freenfse.

Toda configuração variável vem de variáveis de ambiente (ver `.env.example`).
Nenhum valor sensível é definido neste arquivo.
"""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent
RAIZ_REPOSITORIO = BASE_DIR.parent

env = environ.Env()
# Desenvolvimento fora do Docker: lê o .env da raiz. Variáveis já definidas no
# ambiente (Docker, CI) têm precedência e nunca são sobrescritas.
environ.Env.read_env(RAIZ_REPOSITORIO / ".env", overwrite=False)

# --- Versão (fonte única: arquivo VERSION na raiz do repositório) -------------
VERSAO = (RAIZ_REPOSITORIO / "VERSION").read_text(encoding="utf-8").strip()

# --- Segurança ----------------------------------------------------------------
# Sem valor padrão: a aplicação não sobe sem SECRET_KEY definida.
SECRET_KEY = env("SECRET_KEY")
DEBUG = env.bool("DEBUG", default=False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

# --- Aplicações ---------------------------------------------------------------
# django-tenants: SHARED_APPS vivem no schema público; TENANT_APPS têm uma cópia
# por empresa (schema).
SHARED_APPS = [
    "django_tenants",
    "django.contrib.contenttypes",
    "rest_framework",
    "core",
]
TENANT_APPS = [
    "cadastros",
    "fiscal",
    "documentos",
    "agendamentos",
]
INSTALLED_APPS = list(SHARED_APPS) + [app for app in TENANT_APPS if app not in SHARED_APPS]

TENANT_MODEL = "core.Empresa"
TENANT_DOMAIN_MODEL = "core.Dominio"

# A empresa ativa é definida por requisição (cabeçalho X-Empresa), não por domínio
# nem por sessão (D10). O middleware de empresa entra na Fase 1; até lá toda
# requisição roda no schema público.
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

# --- Banco de dados (PostgreSQL, um schema por empresa) -----------------------
DATABASES = {
    "default": {
        "ENGINE": "django_tenants.postgresql_backend",
        "NAME": env("POSTGRES_DB"),
        "USER": env("POSTGRES_USER"),
        "PASSWORD": env("POSTGRES_PASSWORD"),
        "HOST": env("POSTGRES_HOST", default="localhost"),
        "PORT": env("POSTGRES_PORT", default="5432"),
    }
}
DATABASE_ROUTERS = ("django_tenants.routers.TenantSyncRouter",)
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- API (DRF) ----------------------------------------------------------------
# Autenticação e permissões entram na Fase 1; por ora só JSON, sem sessão.
REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "UNAUTHENTICATED_USER": None,
}

# --- Celery / Redis -----------------------------------------------------------
REDIS_URL = env("REDIS_URL", default="redis://localhost:6379/0")
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_TIMEZONE = "America/Sao_Paulo"
CELERY_TASK_TRACK_STARTED = True
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

# --- Internacionalização ------------------------------------------------------
LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

# --- Logs (saída padrão, capturada pelo Docker) -------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
}
