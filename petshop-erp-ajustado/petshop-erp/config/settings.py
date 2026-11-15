"""
Configurações do projeto Pet Shop ERP.

Todas as configurações sensíveis ou que mudam entre ambientes (local,
Oracle Cloud, Cloudflare Tunnel) são lidas do arquivo .env.
"""

from pathlib import Path

from decouple import Csv, config

BASE_DIR = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Núcleo
# ---------------------------------------------------------------------------

SECRET_KEY = config("DJANGO_SECRET_KEY")

DEBUG = config("DJANGO_DEBUG", default=False, cast=bool)

ALLOWED_HOSTS = config(
    "DJANGO_ALLOWED_HOSTS",
    default="localhost,127.0.0.1",
    cast=Csv(),
)

CSRF_TRUSTED_ORIGINS = config(
    "DJANGO_CSRF_TRUSTED_ORIGINS",
    default="",
    cast=Csv(),
)

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"


# ---------------------------------------------------------------------------
# Apps
# ---------------------------------------------------------------------------

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

LOCAL_APPS = [
    "core.apps.CoreConfig",
    "accounts.apps.AccountsConfig",
    "produtos.apps.ProdutosConfig",
    "estoque.apps.EstoqueConfig",
    "vendas.apps.VendasConfig",
    "financeiro.apps.FinanceiroConfig",
    "dashboard.apps.DashboardConfig",
    "logs.apps.LogsConfig",
]

INSTALLED_APPS = DJANGO_APPS + LOCAL_APPS


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "logs.middleware.AuditoriaMiddleware",
    "core.middleware.ControleAcessoMiddleware",
]


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]


# ---------------------------------------------------------------------------
# Banco de dados (PostgreSQL)
# ---------------------------------------------------------------------------

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("DB_NAME", default="petshop_db"),
        "USER": config("DB_USER", default="petshop_user"),
        "PASSWORD": config("DB_PASSWORD"),
        "HOST": config("DB_HOST", default="localhost"),
        "PORT": config("DB_PORT", default="5432"),
        "CONN_MAX_AGE": 60,
        "CONN_HEALTH_CHECKS": True,
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ---------------------------------------------------------------------------
# Autenticação e senhas
# ---------------------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# O padrão do Django já usa PBKDF2 com SHA256 e salt. Mantido explícito.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
]

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "core:home"
LOGOUT_REDIRECT_URL = "accounts:login"

# Sessão expira após 8 horas e a cada fechamento do navegador.
SESSION_COOKIE_AGE = 60 * 60 * 8
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"


# ---------------------------------------------------------------------------
# Internacionalização
# ---------------------------------------------------------------------------

LANGUAGE_CODE = "pt-br"
TIME_ZONE = config("DJANGO_TIME_ZONE", default="America/Sao_Paulo")
USE_I18N = True
USE_TZ = True
USE_THOUSAND_SEPARATOR = True


# ---------------------------------------------------------------------------
# Arquivos estáticos (WhiteNoise)
# ---------------------------------------------------------------------------

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# CompressedStaticFilesStorage (sem manifesto) evita erro no collectstatic
# causado pela referência a ".map" no final do bootstrap.min.css.
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}


# ---------------------------------------------------------------------------
# Mensagens (classes do Bootstrap 5)
# ---------------------------------------------------------------------------

from django.contrib.messages import constants as message_constants  # noqa: E402

MESSAGE_TAGS = {
    message_constants.DEBUG: "secondary",
    message_constants.INFO: "info",
    message_constants.SUCCESS: "success",
    message_constants.WARNING: "warning",
    message_constants.ERROR: "danger",
}


# ---------------------------------------------------------------------------
# HTTPS e segurança
# ---------------------------------------------------------------------------

# Atrás de Cloudflare Tunnel ou de um proxy reverso (Etapa 12), o Django
# recebe HTTP simples e confia no cabeçalho X-Forwarded-Proto.
# O gunicorn ficará acessível apenas em 127.0.0.1.
BEHIND_PROXY = config("DJANGO_BEHIND_PROXY", default=True, cast=bool)
if BEHIND_PROXY:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

SECURE_SSL_REDIRECT = config(
    "DJANGO_SECURE_SSL_REDIRECT", default=not DEBUG, cast=bool
)

SECURE_HSTS_SECONDS = config(
    "DJANGO_HSTS_SECONDS", default=0 if DEBUG else 31536000, cast=int
)
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False

COOKIES_SECURE = config("DJANGO_COOKIES_SECURE", default=not DEBUG, cast=bool)
SESSION_COOKIE_SECURE = COOKIES_SECURE
CSRF_COOKIE_SECURE = COOKIES_SECURE

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

# Cabeçalho de onde o middleware de auditoria (Etapa 10) lê o IP do cliente.
# - REMOTE_ADDR: acesso direto ou proxy local que repassa o IP.
# - HTTP_CF_CONNECTING_IP: use com Cloudflare Tunnel.
# - HTTP_X_REAL_IP: use com Nginx configurado para enviá-lo.
CLIENT_IP_HEADER = config("CLIENT_IP_HEADER", default="REMOTE_ADDR")


# ---------------------------------------------------------------------------
# Logs de aplicação (arquivo em var/log com rotação)
# ---------------------------------------------------------------------------

LOG_DIR = BASE_DIR / "var" / "log"
LOG_DIR.mkdir(parents=True, exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "padrao": {
            "format": "{asctime} [{levelname}] {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "padrao",
        },
        "arquivo": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(LOG_DIR / "petshop.log"),
            "maxBytes": 5 * 1024 * 1024,
            "backupCount": 10,
            "formatter": "padrao",
            "encoding": "utf-8",
        },
    },
    "root": {
        "handlers": ["console", "arquivo"],
        "level": "INFO",
    },
    "loggers": {
        "django.request": {
            "handlers": ["console", "arquivo"],
            "level": "WARNING",
            "propagate": False,
        },
        "django.security": {
            "handlers": ["console", "arquivo"],
            "level": "WARNING",
            "propagate": False,
        },
    },
}