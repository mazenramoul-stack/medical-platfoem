"""
Django settings for core project — Multimodal Medical AI Platform.

Reads secrets and DB config from backend/.env via python-decouple.
"""

from datetime import timedelta
from pathlib import Path

from decouple import Csv, config

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config('SECRET_KEY')
DEBUG = config('DEBUG', default=False, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1', cast=Csv())


# Applications -------------------------------------------------------------

DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

THIRD_PARTY_APPS = [
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',  # server-side refresh-token revocation
    'corsheaders',
    'drf_spectacular',  # OpenAPI 3 schema + Swagger/ReDoc docs
]

LOCAL_APPS = [
    'apps.authentication',
    'apps.patients',
    'apps.mri',
    'apps.ecg',
    'apps.echo',
    'apps.eeg',
    'apps.reports',
    'apps.inference',
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS


MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]


ROOT_URLCONF = 'core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'


# Database — MongoDB via djongo -------------------------------------------

DATABASES = {
    'default': {
        'ENGINE': 'djongo',
        'NAME': config('DB_NAME', default='medical_platform'),
        'CLIENT': {
            'host': config('DB_HOST', default='localhost'),
            'port': config('DB_PORT', default=27017, cast=int),
        },
    }
}

# Test database override. djongo + MongoDB cannot reliably create a throwaway
# test database, which historically blocked every APITestCase (auth, permission,
# doctor-isolation) from running on a fresh checkout. When the test runner is
# active, use in-memory SQLite so the HTTP/permission test layer actually runs.
# This affects ONLY `manage.py test`; normal runserver still uses MongoDB/djongo.
import sys  # noqa: E402

if 'test' in sys.argv:
    DATABASES['default'] = {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }


# Password validation -----------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


# Internationalization ----------------------------------------------------

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True


# Static & media files ----------------------------------------------------

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Media access control. Patient media (scans, plots, PDF reports) is PHI and must
# not be served from a public path. It is served by core.media.serve_signed_media,
# which requires a short-lived HMAC signature minted by the API serializers when
# they hand back a *_url. See core/media.py. The secret defaults to SECRET_KEY.
MEDIA_URL_SIGNING_SECRET = config('MEDIA_URL_SIGNING_SECRET', default=SECRET_KEY)
MEDIA_SIGNED_URL_TTL_SECONDS = config('MEDIA_SIGNED_URL_TTL_SECONDS', default=3600, cast=int)

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

AUTH_USER_MODEL = 'authentication.User'


# Django REST Framework ---------------------------------------------------

REST_FRAMEWORK = {
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_RENDERER_CLASSES': (
        'rest_framework.renderers.JSONRenderer',
    ),
    # ScopedRateThrottle only applies to views that set `throttle_scope`
    # (the auth endpoints below) — all other endpoints are unthrottled.
    'DEFAULT_THROTTLE_CLASSES': (
        'rest_framework.throttling.ScopedRateThrottle',
    ),
    'DEFAULT_THROTTLE_RATES': {
        'auth_login': '10/min',
        'auth_register': '5/min',
        'auth_refresh': '30/min',
    },
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'AUTH_HEADER_TYPES': ('Bearer',),
    # Rotate on every refresh and blacklist the previous token, so a stolen or
    # logged-out refresh token cannot be reused (revocation via token_blacklist).
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
}


# CORS --------------------------------------------------------------------

CORS_ALLOWED_ORIGINS = config(
    'CORS_ALLOWED_ORIGINS',
    default='http://localhost:3000',
    cast=Csv(),
)
CORS_ALLOW_CREDENTIALS = True


# Cache — DRF throttle backend --------------------------------------------
# The auth rate throttles store their counters in the default cache. Django's
# built-in LocMemCache is PER-PROCESS, so under multiple gunicorn workers the
# login/register limits are enforced per worker (not globally) and reset on
# reload. Set REDIS_URL in production for a shared, durable throttle
# (`pip install django-redis`); local dev and tests keep the in-memory cache.
REDIS_URL = config('REDIS_URL', default='')
if REDIS_URL:
    CACHES = {
        'default': {
            'BACKEND': 'django_redis.cache.RedisCache',
            'LOCATION': REDIS_URL,
            'OPTIONS': {'CLIENT_CLASS': 'django_redis.client.DefaultClient'},
        },
    }
else:
    CACHES = {
        'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'},
    }


# Production security hardening -------------------------------------------
# Active only in real production (DEBUG=False and not under `manage.py test`),
# so local HTTP development and the test client are unaffected — an HTTPS
# redirect would otherwise 301 every test request. Clears `check --deploy`.
if not DEBUG and 'test' not in sys.argv:
    SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=True, cast=bool)
    SECURE_HSTS_SECONDS = config('SECURE_HSTS_SECONDS', default=31536000, cast=int)  # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    # Trust the X-Forwarded-Proto set by the nginx/gunicorn TLS terminator.
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')


# API documentation (drf-spectacular) -------------------------------------
SPECTACULAR_SETTINGS = {
    'TITLE': 'Multimodal Medical AI Platform API',
    'DESCRIPTION': (
        'Doctor-scoped REST API for brain-MRI, 12-lead ECG, echocardiogram, and '
        'EEG inference plus combined PDF reports. Decision-support only — not a '
        'certified diagnostic device.'),
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    # Public schema/docs for the demo (describes the API surface, not patient
    # data). Tighten SERVE_PERMISSIONS to IsAuthenticated for a hardened deploy.
    'SERVE_PERMISSIONS': ['rest_framework.permissions.AllowAny'],
}
