# -*- coding: utf-8 -*-
# Django settings for kirppu project.
from decimal import Decimal
from email.utils import getaddresses
import os.path
from django.core.exceptions import ImproperlyConfigured
from django.utils.translation import gettext_lazy as _

import environ


env = environ.Env()
env.read_env(env.str('ENV_PATH', '.env'))

BASE = os.path.dirname(os.path.abspath(__file__))


def _path(path):
    return os.path.normpath(os.path.join(BASE, '..', path))


def get_debug_setting(name: str, cast=None, default=environ.Env.NOTSET):
    """Read a setting only in debug environment.
       Otherwise return default.
       Cast (if given) may be string ("bool") or class (bool).
    """
    if DEBUG:
        if cast is not None:
            if not isinstance(cast, str):
                cast = cast.__name__
            return getattr(env, cast)(name, default=default)
        else:
            return env(name, default=default)
    else:
        return default


DEBUG = env.bool('DEBUG', default=False)

ADMINS = getaddresses(env.list("ADMINS", default=[]))

if env.str("EMAIL_HOST", None) is not None:
    EMAIL_HOST = env.str("EMAIL_HOST")

if env.str("DEFAULT_FROM_EMAIL", None) is not None:
    DEFAULT_FROM_EMAIL = env.str("DEFAULT_FROM_EMAIL")
    SERVER_EMAIL = env.str("DEFAULT_FROM_EMAIL")

DATABASES = {
    'default': env.db(default='sqlite:///db.sqlite3'),
}

# Set KIRPPU_EXTRA_DATABASES="other_event=sqlite:///foobar.sqlite,another_event=sqlite:///barbaz.sqlite" to add
# extra single-event databases available for readonly Events.
# Multi-event databases need additionally to configure the source mapping with KIRPPU_EXTRA_EVENTS,
# like KIRPPU_EXTRA_EVENTS="event_name@db_name,other_name@db_name" where db_name must
# be present in KIRPPU_EXTRA_DATABASES.
_extra_databases = dict(e.split("=", maxsplit=1) for e in env.list("KIRPPU_EXTRA_DATABASES", default=[]))
KIRPPU_EXTRA_DATABASES = [k for k in _extra_databases if k not in DATABASES]
for k in KIRPPU_EXTRA_DATABASES:
    DATABASES[k] = env.db_url_config(_extra_databases[k])
KIRPPU_EXTRA_EVENTS = dict(e.split("@", maxsplit=1) for e in env.list("KIRPPU_EXTRA_EVENTS", default=[]))
if set(KIRPPU_EXTRA_EVENTS.values()) - set(DATABASES.keys()):
    raise ImproperlyConfigured("Some KIRPPU_EXTRA_EVENTS databases were not found in KIRPPU_EXTRA_DATABASES.")

DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'

# Hosts/domain names that are valid for this site; required if DEBUG is False
# See https://docs.djangoproject.com/en/1.5/ref/settings/#allowed-hosts
ALLOWED_HOSTS = env('ALLOWED_HOSTS', default='').split()

if env.str('ASSUME_SSL_HEADER', None) is not None:
    SECURE_PROXY_SSL_HEADER = env.str('ASSUME_SSL_HEADER').split("=", 1)

# Local time zone for this installation. Choices can be found here:
# http://en.wikipedia.org/wiki/List_of_tz_zones_by_name
# although not all choices may be available on all operating systems.
# In a Windows environment this must be set to your system time zone.
TIME_ZONE = 'Europe/Helsinki'

# Language code for this installation. All choices can be found here:
# http://www.i18nguy.com/unicode/language-identifiers.html
LANGUAGE_CODE = 'fi'

_LANGUAGES = env.str("LANGUAGES", "fi,en").split(",")

LANGUAGES = tuple(lang for lang in (
    ('fi', _("Finnish")),
    ('en', _("English")),
) if not _LANGUAGES or lang[0] in _LANGUAGES)

LOCALE_PATHS = (
    _path("locale"),
)

# If you set this to False, Django will make some optimizations so as not
# to load the internationalization machinery.
USE_I18N = True

# If you set this to False, Django will not use timezone-aware datetimes.
USE_TZ = True

# Absolute filesystem path to the directory that will hold user-uploaded files.
# Example: "/var/www/example.com/media/"
MEDIA_ROOT = ''

# URL that handles the media served from MEDIA_ROOT. Make sure to use a
# trailing slash.
# Examples: "http://example.com/media/", "http://media.example.com/"
MEDIA_URL = ''

# Absolute path to the directory static files should be collected to.
# Don't put anything in this directory yourself; store your static files
# in apps' "static/" subdirectories and in STATICFILES_DIRS.
# Example: "/var/www/example.com/static/"
STATIC_ROOT = _path('static/')

# URL prefix for static files.
# Example: "http://example.com/static/", "http://static.example.com/"
STATIC_URL = '/static/'

# Additional locations of static files
STATICFILES_DIRS = (
    # Put strings here, like "/home/html/static" or "C:/www/django/static".
    # Always use forward slashes, even on Windows.
    # Don't forget to use absolute paths, not relative paths.
)

# List of finder classes that know how to find static files in
# various locations.
STATICFILES_FINDERS = (
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
    # 'django.contrib.staticfiles.finders.DefaultStorageFinder',
)

# Make this unique, and don't share it with anybody.
SECRET_KEY = env.str('SECRET_KEY', default=(
    '' if not DEBUG else '=#j)-ml7x@a2iw9=#l7%i89l%cry6kch6x49=0%vcasq!!@97-'
))

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]


ROOT_URLCONF = 'kirppu_project.urls'

# Python dotted path to the WSGI application used by Django's runserver.
WSGI_APPLICATION = 'kirppu_project.wsgi.application'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'APP_DIRS': True,
        'DIRS': (os.path.join(os.path.dirname(__file__), '..', 'templates').replace('\\', '/'),),
        'OPTIONS': {
            'debug': DEBUG,
            'context_processors': [
                'django.contrib.auth.context_processors.auth',
                'django.template.context_processors.debug',
                'django.template.context_processors.i18n',
                'django.template.context_processors.media',
                'django.template.context_processors.request',
                'django.template.context_processors.static',
                'django.template.context_processors.tz',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

INSTALLED_APPS = (
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Uncomment the next line to enable the admin:
    'django.contrib.admin',
    # Uncomment the next line to enable admin documentation:
    # 'django.contrib.admindocs',
    'kirppuauth',
    'kirppu.apps.KirppuApp',
)

AUTH_USER_MODEL = 'kirppuauth.User'
KIRPPU_USER_ADAPTER = 'kirppu.models.UserAdapterBase'

# A sample logging configuration. The only tangible logging
# performed by this configuration is to send an email to
# the site admins on every HTTP 500 error when DEBUG=False.
# See http://docs.djangoproject.com/en/dev/topics/logging for
# more details on how to customize your logging configuration.
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'filters': {
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse'
        }
    },
    'handlers': {
        'mail_admins': {
            'level': 'ERROR',
            'filters': ['require_debug_false'],
            'class': 'django.utils.log.AdminEmailHandler'
        },
        'console': {
            'level': 'DEBUG' if DEBUG else 'WARNING',
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'django.request': {
            'handlers': ['mail_admins'],
            'level': 'ERROR',
            'propagate': False,
        },
        'celery': {
            'handlers': ['console'],
            'level': 'DEBUG' if DEBUG else 'WARNING',
            'propagate': True
        },
        'kompassi_oauth2': {
            'handlers': ['console'],
            'level': 'DEBUG' if DEBUG else 'WARNING',
            'propagate': True
        },
    },
}

# Mapping from Kompassi user fields to Kirppu user fields.
# for SSOClerkForm
KOMPASSI_USER_MAP = [
    # Kompassi, django
    ('username', 'username'),
    ('email', 'email'),
    ('first_name', 'first_name'),
    ('surname', 'last_name'),
    ('phone', 'phone'),
]
# for OAuth2
KOMPASSI_USER_MAP_V2 = [
    # django, Kompassi
    ('username', 'username'),
    ('email', 'email'),
    ('first_name', 'first_name'),
    ('last_name', 'surname'),
    ('phone', 'phone'),
]

KOMPASSI_API_APPLICATION_NAME = env(
    'KOMPASSI_API_APPLICATION_NAME',
    default='kirppu',
)
KOMPASSI_API_APPLICATION_PASSWORD = env(
    'KOMPASSI_API_APPLICATION_PASSWORD',
    default='fill me in',
)

KOMPASSI_HOST = env('KOMPASSI_HOST', default='https://kompassi.eu')
KOMPASSI_API_V1_URL = '{KOMPASSI_HOST}/api/v1'.format(**locals())
KOMPASSI_OAUTH2_AUTHORIZATION_URL = '{KOMPASSI_HOST}/oauth2/authorize/'.format(**locals())
KOMPASSI_OAUTH2_TOKEN_URL = '{KOMPASSI_HOST}/oauth2/token/'.format(**locals())
KOMPASSI_OAUTH2_REVOKE_URL = '{KOMPASSI_HOST}/oauth2/revoke/'.format(**locals())

KOMPASSI_OAUTH2_CLIENT_ID = env(
    'KOMPASSI_OAUTH2_CLIENT_ID',
    default='kompassi_insecure_test_client_id',
)

KOMPASSI_OAUTH2_CLIENT_SECRET = env(
    'KOMPASSI_OAUTH2_CLIENT_SECRET',
    default='kompassi_insecure_test_client_secret'
)

KOMPASSI_OAUTH2_SCOPE = ['read']
KOMPASSI_API_V2_USER_INFO_URL = '{KOMPASSI_HOST}/api/v2/people/me'.format(**locals())
KOMPASSI_API_V2_EVENT_INFO_URL_TEMPLATE = '{kompassi_host}/api/v2/events/{event_slug}'
KOMPASSI_ADMIN_GROUP = env('KOMPASSI_ADMIN_GROUP', default='admins')


# Kirppu authentication configurations:
#
# Case     | LOGIN_URL       | LOGOUT_URL       | USE_SSO | kirppuauth? |
# ---------+-----------------+------------------+---------+-------------
# Internal | /accounts/login | /accounts/logout | False   | Yes
# Embed    | project url     | project url      | False   | No
# OAUTH2#1 | /oauth2/login   | /oauth2/logout   | True    | Yes
# OAUTH2#2 | /oauth2/login   | /accounts/logout | True    | Yes
#
# #1: Use this if server supports token revokation. KOMPASSI_OAUTH2_REVOKE_URL is needed.
# #2: Use this if server does not support token revokation.

# This can be left to default if kirppuauth module is installed.
# LOGIN_URL = '/oauth2/login'
if env.str("LOGIN_URL", default=None) is not None:
    LOGIN_URL = env.str("LOGIN_URL")
if env.str("LOGOUT_URL", default=None) is not None:
    LOGOUT_URL = env.str("LOGOUT_URL")
else:
    LOGOUT_URL = "/accounts/logout"

# Absolute URL for user "Profile". Leave None if the link should not be displayed.
# 'https://kompassidev.tracon.fi/profile'
PROFILE_URL = env('PROFILE_URL', default=None)

# Whether external login and SSO clerk add are enabled (True) or not (False).
KIRPPU_USE_SSO = env.bool('KIRPPU_USE_SSO', default=False)

# If True, admin can change identity.
KIRPPU_SU_AS_USER = "kirppuauth" in INSTALLED_APPS

# Automatic checkout login. May not be enabled in non-dev environments!
# If "*", first enabled Clerk is automatically used.
# If string, Clerk with that user is used, if it is enabled.
KIRPPU_AUTO_CLERK = get_debug_setting("KIRPPU_AUTO_CLERK", str, default=None)

KIRPPU_COPY_ITEM_WHEN_UNPRINTED = False
KIRPPU_MAX_ITEMS_PER_VENDOR = 2000
KIRPPU_ALLOW_PROVISION_FUNCTIONS = env.bool("KIRPPU_ALLOW_PROVISION_FUNCTIONS", default=False)

# Prefix- and postfix content of currency values.
KIRPPU_CURRENCY = {
    # Content text for currency spans.
    "css": ("", "\\00a0\\20AC"),  # euro.
    # Content for html elements (that cannot be styled with css content).
    "html": ("", "&nbsp;&euro;"),
    # Content for raw text use (js).
    "raw": ("", "\u00a0€"),
}

# Minimum and maximum price for an item.
KIRPPU_MIN_MAX_PRICE = env.tuple("KIRPPU_MIN_MAX_PRICE", default=('1', '400'))

# Maximum purchase amount.
KIRPPU_MAX_PURCHASE = env.str("KIRPPU_MAX_PURCHASE", default='0')

KIRPPU_SHORT_CODE_EXPIRATION_TIME_MINUTES = env.int("KIRPPU_SHORT_CODE_EXPIRATION_TIME_MINUTES", default=10)
KIRPPU_EXHAUST_SHORT_CODE_ON_LOGOUT = env.bool("KIRPPU_EXHAUST_SHORT_CODE_ON_LOGOUT", default=False)
KIRPPU_SHORT_CODE_LENGTH = 5
KIRPPU_MOBILE_LOGIN_RATE_LIMIT = "5/m"

# Show list of unused counters using clerk code without registering the counter?
KIRPPU_COUNTER_LIST = env.bool("KIRPPU_COUNTER_LIST", default=False)

CSRF_FAILURE_VIEW = "kirppu.views.kirppu_csrf_failure"

AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
]
if KIRPPU_USE_SSO:
    AUTHENTICATION_BACKENDS.insert(0, 'kompassi_oauth2.backends.KompassiOAuth2AuthenticationBackend')

# Load local settings that are not stored in repository. This must be last at end of settings.
try:
    from .local_settings import *
except ImportError:
    if DEBUG:
        print("Module local_settings not found.")
