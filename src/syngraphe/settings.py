"""Django settings, every installation-specific value taken from `config.load()`."""

from pathlib import Path

from celery.schedules import crontab

from syngraphe import config

_CONFIG = config.load()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = _CONFIG.secret_key
DEBUG = _CONFIG.debug

# The allowed hosts are rows, checked by the platform's own middleware (ADR-0008).
ALLOWED_HOSTS = ["*"]

# Placement follows tenancy (ADR-0017): the shared schema holds what identifies a person or an
# organisation or is written before any tenant is known; a tenant schema holds one organisation's
# documents. An app on both lists has its tables in both.
SHARED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_htmx",
    "identity",
    "tenancy",
    "audit",
    "shell",
]
TENANT_APPS = [
    "access",
]
INSTALLED_APPS = SHARED_APPS + [app for app in TENANT_APPS if app not in SHARED_APPS]

MIDDLEWARE = [
    "syngraphe.proxy.TrustedProxyMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "syngraphe.logs.RequestContextMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "tenancy.middleware.TenancyMiddleware",
    "identity.middleware.FrameworkAdminMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
]

ROOT_URLCONF = "syngraphe.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.template.context_processors.i18n",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "shell.context_processors.shell",
            ],
        },
    },
]

WSGI_APPLICATION = "syngraphe.wsgi.application"
ASGI_APPLICATION = "syngraphe.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "HOST": _CONFIG.postgres_host,
        "PORT": _CONFIG.postgres_port,
        "NAME": _CONFIG.postgres_db,
        "USER": _CONFIG.postgres_user,
        "PASSWORD": _CONFIG.postgres_password,
        "OPTIONS": {"connect_timeout": 5},
    }
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
# The tenant-query guard (ADR-0017): a tenant-schema model is never queried with no tenant set.
DATABASE_ROUTERS = ["tenancy.routers.TenantGuardRouter"]

AUTH_USER_MODEL = "identity.User"

REDIS_URL = _CONFIG.redis_url
CELERY_BROKER_URL = _CONFIG.celery_broker_url
CELERY_RESULT_BACKEND = _CONFIG.redis_url
CELERY_TASK_TRACK_STARTED = True
# The worker's lines go through the JSON handler below, not Celery's own root setup.
CELERY_WORKER_HIJACK_ROOT_LOGGER = False
# At a fixed hour, so a recreated worker does not push the next run a day further out.
CELERY_BEAT_SCHEDULE = {
    "sweep-sign-in-attempts": {
        "task": "identity.sweep_sign_in_attempts",
        "schedule": crontab(hour=3, minute=0),
    },
}

GIT_REPO_ROOT = _CONFIG.git_repo_root
TRUSTED_PROXIES = _CONFIG.trusted_proxies
DJANGO_ADMIN_PATH = _CONFIG.admin_path
DISPLAY_TIMEZONE = _CONFIG.display_timezone

# Sessions last twelve hours from sign-in, not sliding; the cookie flags follow SITE_HTTPS.
LOGIN_URL = "/signin/"
SESSION_COOKIE_AGE = 12 * 3600
SESSION_SAVE_EVERY_REQUEST = False
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = _CONFIG.site_https
CSRF_COOKIE_SECURE = _CONFIG.site_https

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
    "django.contrib.auth.hashers.ScryptPasswordHasher",
]
# DL-0284: ten characters from a US keyboard, four kinds of character, and the common-password
# and similarity checks.
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "identity.passwords.AddressSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "identity.passwords.KeyboardCompositionValidator"},
]

LANGUAGE_CODE = _CONFIG.default_language
# One catalogue for every app; message ids are English and the catalogue carries Ukrainian.
LOCALE_PATHS = [BASE_DIR / "shell" / "locale"]
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR.parent / "staticfiles"
# The application serves its own static files, hashed and compressed, from what `web` collects as
# it starts (DL-0285).
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# One JSON object per line to stdout — level, logger, message, request id and tenant number where
# known; never a document's text or a person's address.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"request_context": {"()": "syngraphe.logs.RequestContextFilter"}},
    "formatters": {"json": {"()": "syngraphe.logs.JsonFormatter"}},
    "handlers": {
        "stdout": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
            "formatter": "json",
            "filters": ["request_context"],
        }
    },
    "root": {"handlers": ["stdout"], "level": "INFO"},
    "loggers": {
        "django": {"level": "INFO"},
        "django.server": {"level": "INFO", "propagate": True},
    },
}
