"""Configurações do freenfse.

Toda configuração variável vem de variáveis de ambiente (ver `.env.example`).
Nenhum valor sensível é definido neste arquivo.
"""

import tempfile
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
    "operacao",
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
# --- Download em lote (Fase 4) ------------------------------------------------
# O ZIP é gravado nesta pasta (compartilhada entre o backend e o worker) e apagado depois da
# retenção. Em contêineres, monte um volume aqui.
FREENFSE_EXPORTACOES_DIR = env(
    "FREENFSE_EXPORTACOES_DIR", default=str(Path(tempfile.gettempdir()) / "freenfse-exportacoes")
)
FREENFSE_LOTE_MAX_NOTAS = env.int("FREENFSE_LOTE_MAX_NOTAS", default=500)
FREENFSE_LOTE_MAX_MB = env.int("FREENFSE_LOTE_MAX_MB", default=200)
FREENFSE_LOTE_RETENCAO_HORAS = env.int("FREENFSE_LOTE_RETENCAO_HORAS", default=24)
# Agendamentos (Fase 5): atraso máximo com que uma data ainda é executada se o sistema ficou fora
# do ar. Acima disso a data vira aviso, não rascunho. Limitado a 23 h no código (ver ADR 0006).
FREENFSE_AGENDAMENTO_TOLERANCIA_HORAS = env.int("FREENFSE_AGENDAMENTO_TOLERANCIA_HORAS", default=12)

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
    # Notas com resultado incerto: só consulta a Sefin (nunca reenvia), a cada 5 minutos.
    "reconciliar-notas-incertas": {
        "task": "fiscal.tasks.reconciliar_notas_incertas",
        "schedule": crontab(minute="*/5"),
    },
    # Fila de e-mails e de cópias ao Drive (retentativas persistidas): a cada minuto.
    "despachar-documentos-pendentes": {
        "task": "documentos.tasks.despachar_pendentes",
        "schedule": crontab(minute="*"),
    },
    # Dispatcher ÚNICO dos agendamentos: varre todas as empresas a cada minuto e gera rascunhos.
    "despachar-agendamentos": {
        "task": "agendamentos.tasks.despachar_agendamentos",
        "schedule": crontab(minute="*"),
    },
    # Alerta diário (08:20, Brasília) dos rascunhos agendados que esperam aprovação.
    "alertar-rascunhos-pendentes": {
        "task": "agendamentos.tasks.alertar_rascunhos_pendentes",
        "schedule": crontab(hour=8, minute=20),
    },
    # Batimento do agendador: prova que beat -> fila -> worker funcionam (saúde e healthcheck).
    "batimento-do-agendador": {
        "task": "operacao.tasks.batimento",
        "schedule": crontab(minute="*"),
    },
    # Alertas operacionais por e-mail (emissão incerta prolongada, falhas permanentes, backup).
    "verificar-alertas-operacionais": {
        "task": "operacao.tasks.verificar_alertas",
        "schedule": crontab(minute=35),
    },
    # Backup cifrado do banco inteiro: todo dia às 02:30 (Brasília). Falha = log crítico + alerta.
    "fazer-backup": {
        "task": "operacao.tasks.fazer_backup",
        "schedule": crontab(hour=2, minute=30),
    },
    # Expurgo dos registros de envio de e-mail com mais de 5 anos (nenhum documento fiscal).
    "expurgar-envios-de-email": {
        "task": "documentos.tasks.expurgar_envios_email",
        "schedule": crontab(hour=3, minute=10),
    },
    # Expurgo dos ZIPs do download em lote vencidos: de hora em hora.
    "expurgar-exportacoes": {
        "task": "documentos.tasks.expurgar_exportacoes",
        "schedule": crontab(minute=17),
    },
}

# --- Retenção (Fase 6, ADR 0008) ----------------------------------------------------
# Registros de envio de e-mail: 5 anos (decisão #18), depois expurgo automático diário. XML e
# documentos fiscais NÃO têm expurgo automático.
FREENFSE_RETENCAO_ENVIOS_ANOS = env.int("FREENFSE_RETENCAO_ENVIOS_ANOS", default=5)

# --- Alertas operacionais (Fase 6) -----------------------------------------------
# Por empresa: pelo e-mail configurado da empresa (Fase 4), para os administradores. Horas sem
# resposta definitiva da Sefin até alertar uma nota "enviando"/"incerta".
FREENFSE_ALERTA_EMISSAO_HORAS = env.int("FREENFSE_ALERTA_EMISSAO_HORAS", default=2)
# Da plataforma (backup que falhou): não pertencem a uma empresa, então saem por um SMTP do
# sistema (ALERTAS_SMTP_*; recomendado: caixa dedicada com senha de app). Sem ALERTAS_SMTP_HOST
# o alerta fica só no log (CRITICAL) e no endpoint de saúde. ALERTAS_EMAIL_PARA vazio = os
# usuários Master ativos.
ALERTAS_EMAIL_PARA = env.list("ALERTAS_EMAIL_PARA", default=[])
ALERTAS_SMTP_HOST = env("ALERTAS_SMTP_HOST", default="")
ALERTAS_SMTP_PORTA = env.int("ALERTAS_SMTP_PORTA", default=587)
ALERTAS_SMTP_SEGURANCA = env("ALERTAS_SMTP_SEGURANCA", default="starttls")  # starttls|ssl|nenhuma
ALERTAS_SMTP_USUARIO = env("ALERTAS_SMTP_USUARIO", default="")
ALERTAS_SMTP_SENHA = env("ALERTAS_SMTP_SENHA", default="")
ALERTAS_EMAIL_DE = env("ALERTAS_EMAIL_DE", default=ALERTAS_SMTP_USUARIO or "freenfse@localhost")

# Segundos em que a resposta de /api/saude/ é reaproveitada (por processo): o endpoint é público.
FREENFSE_SAUDE_CACHE_SEGUNDOS = env.int("FREENFSE_SAUDE_CACHE_SEGUNDOS", default=5)

# --- BI (Fase 6) -------------------------------------------------------------------
# Usuário de banco SOMENTE LEITURA que enxerga apenas o schema "bi" (views consolidadas, sem XML
# nem credenciais). Criado por `python manage.py criar_usuario_bi`.
FREENFSE_BI_USUARIO = env("FREENFSE_BI_USUARIO", default="freenfse_bi")

# --- Backup (Fase 6, ADR 0008) --------------------------------------------------
# Pasta dos backups cifrados (volume próprio; copie para fora do servidor). O destinatário é a
# chave PÚBLICA age (age1...): a privada fica fora do servidor e só serve para restaurar.
FREENFSE_BACKUP_DIR = env("FREENFSE_BACKUP_DIR", default="/var/lib/freenfse/backups")
FREENFSE_BACKUP_DESTINATARIO = env("FREENFSE_BACKUP_DESTINATARIO", default="")
FREENFSE_BACKUP_RETENCAO_DIAS = env.int("FREENFSE_BACKUP_RETENCAO_DIAS", default=14)

# --- Internacionalização ------------------------------------------------------
LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

# --- Logs (saída padrão, capturada pelo Docker/journald) --------------------------
# Estruturados (JSON, uma linha por evento) e SEM segredos nem CPF/e-mail: a máscara é feita
# pelo formatador e pelo filtro (operacao/logs.py), não por quem chama o log. LOG_FORMATO=texto
# serve só ao desenvolvimento; o filtro de segredos vale nos dois formatos.
LOG_FORMATO = env("LOG_FORMATO", default="json")
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"segredos": {"()": "operacao.logs.FiltroDeSegredos"}},
    "formatters": {
        "json": {"()": "operacao.logs.FormatadorJson"},
        "texto": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": LOG_FORMATO if LOG_FORMATO in ("json", "texto") else "json",
            "filters": ["segredos"],
        }
    },
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
}
# O worker e o beat usam esta mesma configuração (sem o formato próprio do Celery).
CELERY_WORKER_HIJACK_ROOT_LOGGER = False
