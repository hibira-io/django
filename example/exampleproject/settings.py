"""A live chat room on django-hibira. Set HIBIRA_APP_ID, HIBIRA_APP_KEY and
HIBIRA_APP_SECRET (from your app page on https://hibira.io/portal), then:

    python manage.py migrate
    python manage.py runserver
"""

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = "example-only-not-secret"
DEBUG = True
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.staticfiles",
    "django_hibira",
    "chat",
]
MIDDLEWARE = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
]
ROOT_URLCONF = "exampleproject.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": ["django.template.context_processors.request"]},
}]
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}
STATIC_URL = "/static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
TIME_ZONE = "UTC"

# Connection settings come from HIBIRA_APP_ID, HIBIRA_APP_KEY,
# HIBIRA_APP_SECRET (and HIBIRA_HOST / HIBIRA_PORT / HIBIRA_USE_TLS for a
# local server).
HIBIRA = {
    "AUTHORIZE_CHANNEL": "chat.realtime.authorize",
}
