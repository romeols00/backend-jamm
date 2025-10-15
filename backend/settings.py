"""
Django settings for backend_jamm project.
"""

import os
from pathlib import Path
from datetime import timedelta
import dj_database_url

# --- Percorsi base ---
BASE_DIR = Path(__file__).resolve().parent.parent

# --- Sicurezza ---
SECRET_KEY = os.getenv("SECRET_KEY", "django-insecure-h87)9(u+v*9k3j72z$m#tkty$p7r8@aly))7bo3&s2kx1*l*-")
DEBUG = os.getenv("DEBUG", "True").lower() == "true"

ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

# --- App custom ---
AUTH_USER_MODEL = "api.Utente"

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt",
    "corsheaders",
    "api",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "backend.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
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

WSGI_APPLICATION = "backend.wsgi.application"

# --- Database ---
if DEBUG:
    # ✅ Locale
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": "Jamm_DB",
            "USER": "postgres",
            "PASSWORD": "@Balena2000",
            "HOST": "127.0.0.1",
            "PORT": "3003",
            "OPTIONS": {"connect_timeout": 5},
        }
    }
else:
    # 🚀 Produzione (Render / Railway / Neon)
    ssl_require = os.getenv("DB_SSL_REQUIRE", "True").lower() == "true"
    db_config = dj_database_url.config(
        default=os.getenv("DATABASE_URL"),
        conn_max_age=600,
        ssl_require=ssl_require,
    )
    db_config.setdefault("OPTIONS", {})
    db_config["OPTIONS"]["connect_timeout"] = int(os.getenv("DB_CONNECT_TIMEOUT", "5"))
    DATABASES = {"default": db_config}

# --- JWT e REST ---
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
}

PASSWORD_RESET_TIMEOUT = timedelta(days=3).total_seconds()

# --- Email ---
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = "smtp.gmail.com"
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = "romixlasala@gmail.com"
EMAIL_HOST_PASSWORD = "wefgeopfoivxvutm"
DEFAULT_FROM_EMAIL = EMAIL_HOST_USER

# --- CORS / CSRF ---
FRONTEND_BASE_URL = os.getenv("FRONTEND_BASE_URL", "http://127.0.0.1:5173").rstrip("/")

CORS_ALLOW_CREDENTIALS = True

if DEBUG:
    CORS_ALLOWED_ORIGINS = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    CSRF_TRUSTED_ORIGINS = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
else:
    CORS_ALLOWED_ORIGINS = [
        FRONTEND_BASE_URL,
    ]
    CSRF_TRUSTED_ORIGINS = [
        FRONTEND_BASE_URL,
    ]

# --- Lingua e timezone ---
LANGUAGE_CODE = "it-it"
TIME_ZONE = "Europe/Rome"
USE_I18N = True
USE_TZ = True

# --- Static & Media ---
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# --- Default key ---
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
