"""Configurações do freenfse.

Toda configuração variável vem de variáveis de ambiente (ver `.env.example`).
Nenhum valor sensível é definido neste arquivo.
"""

from pathlib import Path

import environ
from celery.schedules import crontab

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

# Chaves de criptografia de credenciais e certificados (AES-256-GCM): itens
# `versão:chave`; a primeira é a atual. Ver core/crypto.py.
FREENFSE_CHAVES = env.list("FREENFSE_CHAVES", default=[])

# --- Aplicações ---------------------------------------------------------------
# django-tenants: SHARED_APPS vivem no schema público; TENANT_APPS têm uma cópia
# por empresa (schema).
SHARED_APPS = [
    "django_tenants",
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "django.contrib.messages",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    # Provedores instalados; só funcionam com credenciais/flag no ambiente (ver abaixo).
    "allauth.socialaccount.providers.google",
    "allauth.socialaccount.providers.microsoft",
    "allauth.socialaccount.providers.openid_connect",
    "allauth.mfa",
    "allauth.headless",
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
AUTH_USER_MODEL = "core.Usuario"

# A empresa ativa é definida POR REQUISIÇÃO (cabeçalho X-Empresa), nunca por
# domínio nem por sessão (D10): ver core/middleware.py. A ordem importa: o
# usuário (sessão) é resolvido antes de validar o acesso à empresa.
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "core.middleware.Exigir2FAMiddleware",
    "core.middleware.EmpresaPorCabecalhoMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]

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

# --- Redis: fila do Celery e cache --------------------------------------------
REDIS_URL = env("REDIS_URL", default="redis://localhost:6379/0")
# O cache compartilhado entre os processos guarda o contador de tentativas de
# login (bloqueio) e os códigos 2FA já usados; um cache por processo não serviria.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": env("REDIS_CACHE_URL", default=REDIS_URL.rsplit("/", 1)[0] + "/1"),
    }
}

# --- Autenticação (django-allauth, headless) ----------------------------------
AUTHENTICATION_BACKENDS = ["allauth.account.auth_backends.AuthenticationBackend"]
SITE_ID = None

ACCOUNT_ADAPTER = "core.auth.adapters.AccountAdapter"
SOCIALACCOUNT_ADAPTER = "core.auth.adapters.SocialAccountAdapter"
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
# Não há autocadastro: o administrador cadastra o e-mail, que já nasce verificado.
ACCOUNT_EMAIL_VERIFICATION = "none"
# Bloqueio por tentativas falhas: N falhas por e-mail dentro da janela bloqueiam
# novas tentativas (daquele e-mail) até a janela expirar; e no máximo 10 por
# minuto por IP.
ACCOUNT_RATE_LIMITS = {
    "login_failed": (
        f"10/m/ip,{env.int('AUTH_TENTATIVAS_MAXIMAS', default=5)}"
        f"/{env.int('AUTH_BLOQUEIO_SEGUNDOS', default=900)}s/key"
    ),
}

HEADLESS_ONLY = True
HEADLESS_FRONTEND_URLS = {
    "socialaccount_login_error": "/login?erro=social",
}
AUTH_URL_LOGIN = "/login"

# 2FA: TOTP por aplicativo + códigos de recuperação.
MFA_SUPPORTED_TYPES = ["totp", "recovery_codes"]
MFA_TOTP_ISSUER = "freenfse"
# Política: exigir 2FA do Master (recomendado) e/ou de todos os usuários.
AUTH_EXIGIR_2FA_MASTER = env.bool("AUTH_EXIGIR_2FA_MASTER", default=True)
AUTH_EXIGIR_2FA_TODOS = env.bool("AUTH_EXIGIR_2FA_TODOS", default=False)

# Login social: restrição opcional de domínio do e-mail (vazio = qualquer domínio).
AUTH_DOMINIOS_PERMITIDOS = env.list("AUTH_DOMINIOS_PERMITIDOS", default=[])

# Provedores sociais. As credenciais OAuth vêm só do ambiente. Google fica ligado
# quando há credenciais; Microsoft e OpenID Connect ficam instalados e DESLIGADOS
# até a flag correspondente ser ativada.
SOCIALACCOUNT_PROVIDERS = {}
if env("AUTH_GOOGLE_CLIENT_ID", default=""):
    SOCIALACCOUNT_PROVIDERS["google"] = {
        "APPS": [
            {
                "client_id": env("AUTH_GOOGLE_CLIENT_ID"),
                "secret": env("AUTH_GOOGLE_CLIENT_SECRET", default=""),
                "key": "",
            }
        ],
        "SCOPE": ["profile", "email"],
        "AUTH_PARAMS": {"access_type": "online"},
    }
if env.bool("AUTH_MICROSOFT_ATIVO", default=False):
    SOCIALACCOUNT_PROVIDERS["microsoft"] = {
        "APPS": [
            {
                "client_id": env("AUTH_MICROSOFT_CLIENT_ID", default=""),
                "secret": env("AUTH_MICROSOFT_CLIENT_SECRET", default=""),
                "key": "",
                "settings": {"tenant": env("AUTH_MICROSOFT_TENANT", default="organizations")},
            }
        ]
    }
if env.bool("AUTH_OIDC_ATIVO", default=False):
    SOCIALACCOUNT_PROVIDERS["openid_connect"] = {
        "APPS": [
            {
                "provider_id": "oidc",
                "name": env("AUTH_OIDC_NOME", default="OpenID Connect"),
                "client_id": env("AUTH_OIDC_CLIENT_ID", default=""),
                "secret": env("AUTH_OIDC_CLIENT_SECRET", default=""),
                "settings": {"server_url": env("AUTH_OIDC_URL", default="")},
            }
        ]
    }

# IP do cliente atrás do Nginx: use o cabeçalho que o proxy sobrescreve (X-Real-IP).
# Vazio = usa o IP da conexão. Só configure se o backend NÃO for alcançável sem o proxy.
IP_CABECALHO_CONFIAVEL = env("IP_CABECALHO_CONFIAVEL", default="")
if IP_CABECALHO_CONFIAVEL:
    ALLAUTH_TRUSTED_CLIENT_IP_HEADER = IP_CABECALHO_CONFIAVEL
# Atrás de um proxy que termina o HTTPS: o Django passa a ver a requisição como segura.
if env.bool("PROXY_TLS", default=False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# --- Sessão e CSRF -------------------------------------------------------------
# Expiração por inatividade: a validade é renovada a cada requisição.
SESSION_COOKIE_AGE = env.int("SESSAO_INATIVIDADE_MIN", default=30) * 60
SESSION_SAVE_EVERY_REQUEST = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
COOKIES_SEGUROS = env.bool("COOKIES_SEGUROS", default=False)
SESSION_COOKIE_SECURE = COOKIES_SEGUROS
CSRF_COOKIE_SECURE = COOKIES_SEGUROS
CSRF_COOKIE_SAMESITE = "Lax"
# A SPA lê o token CSRF do cookie e o devolve no cabeçalho X-CSRFToken.
CSRF_COOKIE_HTTPONLY = False
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- API (DRF) ----------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    # Padrão restritivo: rotas públicas declaram AllowAny explicitamente.
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
}

# --- Celery -------------------------------------------------------------------
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_TIMEZONE = "America/Sao_Paulo"
CELERY_TASK_TRACK_STARTED = True
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_BEAT_SCHEDULE = {
    # Alertas de vencimento do certificado A1 (30, 15 e 7 dias): todo dia às 06:40 (Brasília).
    "verificar-vencimento-de-certificados": {
        "task": "fiscal.tasks.verificar_vencimento_certificados",
        "schedule": crontab(hour=6, minute=40),
    },
}

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
