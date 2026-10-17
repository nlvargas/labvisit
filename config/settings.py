from pathlib import Path

import dj_database_url
import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1", ".localhost"]),
)
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY", default="dev-insecure-key")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "labs",
    "catalog",
    "orders",
    "whatsapp",
    "panel",
    "routing",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "labs.middleware.LabMiddleware",
]

ROOT_URLCONF = "config.urls"

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
                "labs.context_processors.lab",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=0,
    )
}
if DATABASES["default"]["ENGINE"] == "django.db.backends.postgresql":
    DATABASES["default"]["DISABLE_SERVER_SIDE_CURSORS"] = True

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "es-cl"
TIME_ZONE = "America/Santiago"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}
if DEBUG:
    STORAGES["staticfiles"] = {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# order photos and PDFs go to a private bucket in production; links expire after 5 minutes
MEDIA_BUCKET = env("MEDIA_BUCKET", default="")
if MEDIA_BUCKET:
    STORAGES["default"] = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "bucket_name": MEDIA_BUCKET,
            "region_name": env("AWS_REGION", default="sa-east-1"),
            "default_acl": None,
            "querystring_auth": True,
            "querystring_expire": 300,
            "file_overwrite": False,
        },
    }

CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_CONTENT_TYPE_NOSNIFF = True

# days before order files, WhatsApp messages and unbooked quotes are deleted (see compile.cl/privacidad)
RETENTION_DAYS = env.int("RETENTION_DAYS", default=90)

DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Used when the host has no lab subdomain, e.g. localhost during development.
DEFAULT_LAB_SLUG = env("DEFAULT_LAB_SLUG", default="")

READER_PROVIDER = env("READER_PROVIDER", default="fake")
FAKE_READER_DELAY = env.float("FAKE_READER_DELAY", default=0)
GEMINI_API_KEY = env("GEMINI_API_KEY", default="")
GEMINI_MODEL = env("GEMINI_MODEL", default="gemini-3.8-flash")
GEMINI_FALLBACK_MODELS = env.list(
    "GEMINI_FALLBACK_MODELS", default=["gemini-3.6-flash", "gemini-3.5-flash", "gemini-flash-lite-latest"]
)

JOBS_BACKEND = env("JOBS_BACKEND", default="sync")

# where patients open a lab's pages; {slug} is the lab subdomain
LAB_URL_TEMPLATE = env("LAB_URL_TEMPLATE", default="https://{slug}.lab.compile.cl")

WHATSAPP_BACKEND = env("WHATSAPP_BACKEND", default="console")
WHATSAPP_ACCESS_TOKEN = env("WHATSAPP_ACCESS_TOKEN", default="")
WHATSAPP_APP_SECRET = env("WHATSAPP_APP_SECRET", default="")
WHATSAPP_VERIFY_TOKEN = env("WHATSAPP_VERIFY_TOKEN", default="")
WHATSAPP_API_VERSION = env("WHATSAPP_API_VERSION", default="v25.0")
WHATSAPP_CONVERSATION_TTL_HOURS = 24

GOOGLE_MAPS_API_KEY = env("GOOGLE_MAPS_API_KEY", default="")
GOOGLE_MAPS_MAP_ID = env("GOOGLE_MAPS_MAP_ID", default="DEMO_MAP_ID")
GOOGLE_MAPS_SERVER_KEY = env("GOOGLE_MAPS_SERVER_KEY", default="")

MATCH_PRESELECT_THRESHOLD = 0.92
MATCH_SUGGEST_THRESHOLD = 0.75

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "panel_agenda"
LOGOUT_REDIRECT_URL = "login"

LAB_HOST_SUFFIXES = env.list("LAB_HOST_SUFFIXES", default=[".lab.compile.cl", ".localhost"])

LOG_LEVEL = env("LOG_LEVEL", default="INFO")
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "{asctime} {levelname:<7} {name}: {message}", "style": "{", "datefmt": "%H:%M:%S"},
    },
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "simple"}},
    "loggers": {
        "orders": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
        "labs": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
        "whatsapp": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
    },
}
