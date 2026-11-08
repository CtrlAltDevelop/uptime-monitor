import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from django.templatetags.static import static
from django.urls import reverse_lazy

BASE_DIR = Path(__file__).resolve().parent.parent

DEBUG = os.environ.get("DEBUG", "") == "1"
SECRET_KEY = os.environ.get("SECRET_KEY", "")
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured("Set the SECRET_KEY env var (or DEBUG=1 for local dev).")
    SECRET_KEY = "dev-only-insecure-key"

ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
CSRF_TRUSTED_ORIGINS = [o for o in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",") if o]

INSTALLED_APPS = [
    "unfold",  # must come before django.contrib.admin
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "monitor",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

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

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": Path(os.environ.get("DB_PATH", BASE_DIR / "db.sqlite3")),
    }
}

LANGUAGE_CODE = "en"
TIME_ZONE = os.environ.get("TIME_ZONE", "Asia/Tehran")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# How long raw check results are kept (the dashboard shows the last 30 days).
RESULT_RETENTION_DAYS = int(os.environ.get("RESULT_RETENTION_DAYS", "90"))

# --- Admin theme (django-unfold) ---
_INDIGO = {
    "50": "oklch(96.2% 0.018 272.314)", "100": "oklch(93% 0.034 272.788)",
    "200": "oklch(87% 0.065 274.039)", "300": "oklch(78.5% 0.115 274.713)",
    "400": "oklch(67.3% 0.182 276.935)", "500": "oklch(58.5% 0.233 277.117)",
    "600": "oklch(51.1% 0.262 276.966)", "700": "oklch(45.7% 0.24 277.023)",
    "800": "oklch(39.8% 0.195 277.366)", "900": "oklch(35.9% 0.144 278.697)",
    "950": "oklch(25.7% 0.09 281.288)",
}


def _nav(title: str, icon: str, link: str) -> dict:
    return {"title": title, "icon": icon, "link": reverse_lazy(link)}


UNFOLD = {
    "SITE_TITLE": "Uptime Monitor",
    "SITE_HEADER": "Uptime Monitor",
    "SITE_SUBHEADER": "Service health monitoring",
    "SITE_SYMBOL": "monitor_heart",
    "SITE_URL": "/",
    "THEME": "dark",  # the glass look is designed for dark
    "BORDER_RADIUS": "14px",
    "COLORS": {"primary": _INDIGO},
    "STYLES": [lambda request: static("monitor/admin-glass.css")],
    "DASHBOARD_CALLBACK": "monitor.dashboard.dashboard_callback",
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": False,
        "navigation": [
            {
                "title": "Monitoring",
                "separator": True,
                "items": [
                    _nav("Dashboard", "dashboard", "admin:index"),
                    _nav("Services", "monitor_heart", "admin:monitor_service_changelist"),
                    _nav("Categories", "category", "admin:monitor_category_changelist"),
                    _nav("Check results", "history", "admin:monitor_checkresult_changelist"),
                ],
            },
            {
                "title": "Access",
                "separator": True,
                "items": [
                    _nav("Users", "person", "admin:auth_user_changelist"),
                    _nav("Groups", "group", "admin:auth_group_changelist"),
                ],
            },
        ],
    },
}

LOGIN_URL = "/admin/login/"
LOGIN_REDIRECT_URL = "/admin/"
