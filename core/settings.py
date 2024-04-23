"""
Django settings for django_demo project.

Generated by 'django-admin startproject' using Django 4.2.1.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/4.2/ref/settings/
"""
import os
from pathlib import Path

# import django.db.models

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Quick-start development settings - unsuitable for production
# https://docs.djangoproject.com/en/5.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-&t(9z)u@$8oe!2n+1*qv7x-*kz^kqn$sz06w^0@$yj2wu^4pii'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True
DEBUG_MODAL_EXCEPTIONS = True

ALLOWED_HOSTS = ['*']
CORS_ALLOW_ALL_ORIGINS = True
# CSRF_TRUSTED_ORIGINS = [r'^http://*', r'^https://*']
# CORS_ALLOWED_ORIGINS = [r'^http://*', r'^https://*']

# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'request_id',
    'corsheaders',
    'rest_framework',
    'user',
    'bot',
    'chat',
    'collection',
    'document',
    'django_celery_results',
    'django_celery_beat',
]

MIDDLEWARE = [
    'request_id.middleware.RequestIdMiddleware',
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
AUTH_USER_MODEL = 'user.MyUser'

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

# Database
# https://docs.djangoproject.com/en/5.0/ref/databases/

DJANGO_DB_POSTGRESQL = 'postgresql'
DJANGO_DB = 'default'
# 设置pg_service.conf 文件目录
# os.environ.setdefault('PGSERVICEFILE', f"{BASE_DIR}/.service.conf")
DATABASES_ALL = {
    DJANGO_DB_POSTGRESQL: {
        "ENGINE": "django.db.backends.postgresql",
        'NAME': os.environ.get('DB_NAME', 'db_name'),
        'USER': os.environ.get('DB_USER', 'db_user'),
        'PASSWORD': os.environ.get('DB_PASSWORD', 'db_user_password'),
        'HOST': os.environ.get('DB_HOST', '127.0.0.1'),
        'PORT': os.environ.get('DB_PORT', '5432'),
        "OPTIONS": {
            # "service": "pg_service",
        },
    }
}

DATABASES_ALL['default'] = DATABASES_ALL[DJANGO_DB_POSTGRESQL]
# DATABASES_ALL['default'] = DATABASES_ALL['mysql']
DATABASES = {
    'default': DATABASES_ALL.get(os.environ.get('DJANGO_DB', 'default'))
}

# redis
REDIS_HOST = os.environ.get('REDIS_HOST', '127.0.0.1')
REDIS_PORT = os.environ.get('REDIS_PORT', '6379')
REDIS_PASSWORD = os.environ.get('REDIS_PASSWORD', '')
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": f"redis://{REDIS_HOST}:{REDIS_PORT}/0",  # noqa
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        }
    }
}
if REDIS_PASSWORD:
    CACHES['default']['OPTIONS']['PASSWORD'] = REDIS_PASSWORD

if os.environ.get('DEBUG', 'false').lower() == 'true':
    print(f"DATABASES: {DATABASES}")
    print(f"CACHES: {CACHES}")

# django-request-id
REQUEST_ID_HEADER = None
REQUEST_ID = None

LOG_FILE = os.environ.get('LOG_FILE', 'all.log')
if not os.path.exists(LOG_FILE):
    dirname = os.path.dirname(LOG_FILE)
    if dirname:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    "filters": {
        "request_id": {
            "()": "request_id.logging.RequestIdFilter"
        }
    },
    'formatters': {
        'verbose': {
            'format': "[{asctime}] [{name}::{funcName}::{lineno:d}] [{levelname}] {request_id} {message}",
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            "filters": ["request_id"],
            'formatter': 'verbose',
        },
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOG_FILE,
            'formatter': 'verbose',
            'maxBytes': 1024 * 1024 * 300,  # 300M
        },
    },
    'root': {
        'handlers': ['console'],
        'level': os.getenv('LOG_LEVEL', 'INFO'),
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file'],
            'level': os.getenv('LOG_LEVEL', 'INFO'),
            'propagate': False,
        },
        'django.utils.autoreload': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        }
    },
}

# Password validation
# https://docs.djangoproject.com/en/4.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

REST_FRAMEWORK = {
    # 全局配置异常模块
    # 设置自定义异常文件路径，在api应用下创建exception文件，exception_handler函数
    'EXCEPTION_HANDLER': 'core.utils.exceptions.custom_exception_handler',

    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_PARSER_CLASSES': (
        'core.utils.views.ServerSentEventRenderer',
        'rest_framework.parsers.JSONParser',
        'rest_framework.renderers.BrowsableAPIRenderer',
    ),

    'DEFAULT_AUTHENTICATION_CLASSES': (
        'core.utils.authentication.MyAuthentication',
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.BasicAuthentication',
        # # 'rest_framework_jwt.authentication.JSONWebTokenAuthentication',
    ),
}

# Internationalization
# https://docs.djangoproject.com/en/5.0/topics/i18n/

# LANGUAGE_CODE = 'en-us'
# TIME_ZONE = 'UTC'
LANGUAGE_CODE = "zh-hans"
TIME_ZONE = "Asia/Shanghai"

USE_I18N = True
USE_TZ = True

STATIC_ROOT = 'static'
STATIC_URL = 'static/'

# celery
CELERY_BROKER_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/0"  # noqa
CELERY_TIMEZONE = TIME_ZONE
CELERY_RESULT_BACKEND = "django-db"  # django-db/django-cache
CELERY_ACCEPT_CONTENT = ['application/json', ]
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TASK_TIME_LIMIT = 50

# DEFAULT_AUTO_FIELD = 'django.db.models.UUIDField'

# oss
OSS_PUBLIC_KEY = os.environ.get('OSS_PUBLIC_KEY', 'public_key')

# rag api
RAG_HOST = os.environ.get('RAG_HOST', 'https://api.scinav.myscale.cloud')
RAG_API_KEY = os.environ.get('RAG_API_KEY', 'api_key')

# object path url host
OBJECT_PATH_URL_HOST = os.environ.get('OBJECT_PATH_URL_HOST', 'object_path_url_host')

# authing
AUTHING_APP_ID = os.environ.get('AUTHING_APP_ID', 'authing_app_id')
AUTHING_APP_SECRET = os.environ.get('AUTHING_APP_SECRET', 'authing_app_secret')
AUTHING_APP_HOST = os.environ.get('AUTHING_APP_HOST', 'authing_app_host')
AUTHING_APP_REDIRECT_URI = os.environ.get('AUTHING_APP_REDIRECT_URI', 'authing_app_redirect_uri')
