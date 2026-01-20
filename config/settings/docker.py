"""
Docker deployment settings.
"""
import os

from .base import *  # noqa
from .base import MIDDLEWARE, STATICFILES_FINDERS, env

# GENERAL
# ------------------------------------------------------------------------------
DEBUG = env.bool("DJANGO_DEBUG", default=False)
SECRET_KEY = env(
    "DJANGO_SECRET_KEY",
    default="change-me-in-production-use-a-real-secret-key",
)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["*"])

# DATABASE
# ------------------------------------------------------------------------------
# Use SQLite stored in persistent data directory
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': env('DATABASE_PATH', default='/app/data/intentions.db'),
    }
}

# CACHES
# ------------------------------------------------------------------------------
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "",
    }
}

# SECURITY
# ------------------------------------------------------------------------------
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=False)
SESSION_COOKIE_SECURE = env.bool("SESSION_COOKIE_SECURE", default=True)
CSRF_COOKIE_SECURE = env.bool("CSRF_COOKIE_SECURE", default=True)
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=["https://intentions.jonnyspicer.com"])

# STATIC FILES
# ------------------------------------------------------------------------------
STATICFILES_FINDERS.append("django.contrib.staticfiles.finders.AppDirectoriesFinder")
MIDDLEWARE.append('whitenoise.middleware.WhiteNoiseMiddleware')
# Use simple whitenoise storage to avoid issues with missing sourcemaps
STATICFILES_STORAGE = 'whitenoise.storage.CompressedStaticFilesStorage'

# EMAIL
# ------------------------------------------------------------------------------
EMAIL_BACKEND = env(
    "DJANGO_EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend"
)

# Password validation - keep it simple for docker deployment
# ------------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = []
