
import os
from datetime import timedelta
from pathlib import Path
from decouple import config
import dj_database_url
import ssl
from urllib.parse import urlparse



# Note: EMAIL_BACKEND, MEDIA_URL, MEDIA_ROOT are defined explicitly below

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/6.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config('SECRET_KEY')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = config('DEBUG', default=False, cast=bool)

ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='127.0.0.1,localhost').split(',')

# Application Definition

INSTALLED_APPS = [
    'daphne',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

# Local Apps
    'authentication',
    'patients',
    'consultants',
    'payments',
    'consultations',
    
# Third Party
    'rest_framework',
    'rest_framework_simplejwt',
    'corsheaders',
    'channels',
    'anymail',
    
    
]

MIDDLEWARE = [

    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'admin_reorder.middleware.ModelAdminReorder',

]

ROOT_URLCONF = 'rnchealth.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR/'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'rnchealth.wsgi.application'
ASGI_APPLICATION = 'rnchealth.asgi.application'


# Database
# https://docs.djangoproject.com/en/6.0/ref/settings/#databases




DATABASES = {
    'default': dj_database_url.config(
        default=config('DATABASE_URL'),
        conn_max_age=0,
        ssl_require=True
    )
}

# Prevent Celery from holding onto open database slots in the background
CELERY_DB_REUSE_MAX = 1

'''
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("DB_NAME", default="your_dbname_here"),
        "USER": config("DB_USER", default="postgres"),
        "PASSWORD": config("DB_PASSWORD", default="your_password_here"),
        "HOST": config("DB_HOST", ),
        "PORT": config("DB_PORT", default=5432, cast=int),  # Added cast=int here
    }
}

'''

# Password validation
# https://docs.djangoproject.com/en/6.0/ref/settings/#auth-password-validators

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


# Internationalization
# https://docs.djangoproject.com/en/6.0/topics/i18n/

LANGUAGE_CODE = 'en-us'

#TIME_ZONE = 'UTC'

TIME_ZONE = 'Asia/Kolkata'

USE_I18N = True

USE_TZ = True


# ==================== STATIC & MEDIA FILES CONFIGURATION ====================

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [
    BASE_DIR / 'static'
]

# Check if we are in production (where DEBUG is False)
if not DEBUG:
    # Production Settings
    STORAGES = {
        # 1. Media uploads go directly to Supabase S3
        "default": {
            "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
        },
        # 2. Static files (CSS/JS) are compressed and served via WhiteNoise on Render
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
        },
    }

    # Feed your Supabase S3 keys via python-decouple config
    AWS_ACCESS_KEY_ID = config("SUPABASE_S3_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = config("SUPABASE_S3_SECRET_ACCESS_KEY")
    AWS_STORAGE_BUCKET_NAME = config("SUPABASE_STORAGE_BUCKET_NAME", default="rncmedia")
    AWS_S3_ENDPOINT_URL = config("SUPABASE_S3_ENDPOINT_URL")
    # Parse the host from AWS_S3_ENDPOINT_URL (e.g. '<project-ref>.supabase.co')
    # and append the public bucket path so URLs resolve to the public Supabase storage endpoint.
    endpoint_host = urlparse(AWS_S3_ENDPOINT_URL).netloc
    AWS_S3_CUSTOM_DOMAIN = f"{endpoint_host}/storage/v1/object/public/{AWS_STORAGE_BUCKET_NAME}"
    AWS_DEFAULT_ACL = None

    # Settings required for Supabase routing behavior
    AWS_S3_REGION_NAME = "auto"
    AWS_S3_SIGNATURE_VERSION = "s3v4"

    # Prevent django-storages from adding messy expiration querystrings to your URLs
    AWS_QUERYSTRING_AUTH = False

else:
    # Local Development Settings (When DEBUG is True)
    STORAGES = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
        },
    }
    
    MEDIA_URL = '/media/'
    MEDIA_ROOT = BASE_DIR / 'media'

# Jwt configuration 
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME' : timedelta(hours = 1),
    'REFRESH_TOKEN_LIFETIME' : timedelta(days = 7),
    'ROTATE_REFRESH_TOKENS' : True,
    'UPDATE_LAST_LOGIN' : True,
    
}


# REST framework configuration

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        
    ),
    'DEFAULT_PERMISSION_CLASSES' : [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS' : 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,


    'DEFAULT_RENDER_CLASSES' :[
        'rest_framework.renderers.JSONRenderer',
        
    ],
    'DEFAULT_THROTTLE_CLASSES' : [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
        
    ],
    
}



# CORS Configuration
CORS_ALLOW_ALL_ORIGINS = False 

CORS_ALLOWED_ORIGINS = [
    'http://localhost:5173',
    'http://127.0.0.1:5173',
    'https://rnchealthlive.onrender.com',  # Your production React frontend
    'http://127.0.0.1:8000',
    'http://localhost:8000',
]

# Tell Django Channels to trust requests coming from your frontend site
ALLOWED_REDIRECT_HOSTS = ["rnchealthlive.onrender.com"]

CORS_ALLOW_CREDENTIALS = True
# Trust your frontend for secure state-changing requests (like POST /login)
CSRF_TRUSTED_ORIGINS = [
    "https://rnchealthlive.onrender.com"
]

AUTH_USER_MODEL = 'authentication.User'


#Email Configuration

'''
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = config("EMAIL_HOST", default="smtp.gmail.com")
EMAIL_PORT = config("EMAIL_PORT", default=587, cast=int)
EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=True, cast=bool)

EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="your-email@gmail.com")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="your-app-password")
DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default="rnchealthapp@gmail.com")
'''

EMAIL_BACKEND = "anymail.backends.brevo.EmailBackend"

ANYMAIL = {
    "BREVO_API_KEY": config("BREVO_API_KEY"),
}

DEFAULT_FROM_EMAIL = config("EMAIL_HOST_USER")



#APP Configuration
APP_NAME = 'Rnchealth App'
DOMAIN_URL = config('DOMAIN_URL', default='http://127.0.0.1:8000')
GOOGLE_CLIENT_ID = config('GOOGLE_CLIENT_ID', default='')


#django admin reorder configuration apps for features
ADMIN_REORDER = (
    
    {'app': 'authentication'},
    
    {'app': 'auth',
     'label': 'AUTHORIZATION',
     'models' :(
         'auth.Group',
     )},
    
    {'app': 'patients', 'label': 'Patient Management', 'models': (
        'patients.PatientProfile',
        'patients.PatientMedicalHistory',
    )},
    {'app': 'consultants'},
    
    {'app': 'consultations'},
    
    {'app': 'payments'},

)


# Payment Gateway Configuration (Stripe)

STRIPE_PUBLISHABLE_KEY = config("STRIPE_PUBLISHABLE_KEY")
STRIPE_SECRET_KEY = config("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = config('STRIP_WEBHOOK_SECRET ', 'whsec_...')

# Payment 


PAYMENT_MIN_AMOUNT = 1.00
PAYMENT_MAX_AMOUNT = 20000.00
PAYMENT_DAILY_LIMIT_TRANSACTIONS = 100
PAYMENT_LIMIT_AMOUNT = 50000.00

PAYMENT_LIMIT_AMOUNT = 50000.00


SECURE_WEBSOCKET_ORIGIN = [
    
    'http://127.0.0.1:5173',
    'http://localhost:5173',
    'http://127.0.0.1:3000',
  ]



# ==================== CHANNELS LAYER CONFIGURATION ====================
# Development: Uses InMemory for quick testing (single process only)
# Production: Use Redis for distributed real-time communication across multiple processes
# To use Redis in development, ensure redis-server is running: docker run -d -p 6379:6379 redis:latest
'''
if DEBUG:
    # Development: Use InMemory channel layer (single process, quick testing)
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer",
        },
    }
'''

# Production: Use Redis for distributed channel layer (multiple processes, scalable)
# 1. Keep your clean REDIS_URL environment variable string readout

REDIS_URL = config("REDIS_URL", default="redis://127.0.0.1:6379")

# ==================== DJANGO CHANNELS CONFIGURATION ====================
CHANNEL_LAYERS = {
    "default": {
        # COST FIX: If your channels package is up to date, consider changing this 
        # to "channels_redis.pubsub.RedisPubSubChannelLayer" to drastically cut down polling requests.
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [REDIS_URL],
            "capacity": 200,  # OPTIMIZATION: Reduced from 1500. Lower memory buffers = fewer operations
            "expiry": 15,     # OPTIMIZATION: Reduced from 60. Drop old messages quickly so Redis doesn't bloat
            "group_expiry": 3600, # OPTIMIZATION: Reduced from 86400 (24h) to 1 hour. Cleans up stale groups fast
            # ADD THIS TO PREVENT DAPHNE HANDSHAKE HANGS:
            "redis_config": {
                "socket_timeout": 5,
                "socket_connect_timeout": 5,
            }

        },
    },
}

# ==================== CELERY CONFIGURATION ====================
CELERY_BROKER_URL = config(
    'REDIS_URL', 
    default=f"redis://{config('REDIS_HOST', default='localhost')}:{config('REDIS_PORT', default=6379)}/0"
)

# SSL Configurations (Kept perfectly intact for Render's OS environment)
CELERY_BROKER_USE_SSL = {
    'ssl_cert_reqs': 'required',
    'ssl_ca_certs': '/etc/ssl/certs/ca-certificates.crt'
}

# OPTIMIZATION: Slow down Celery's aggressive background polling loop!
# Protect Celery from hanging indefinitely on network proxies
CELERY_BROKER_TRANSPORT_OPTIONS = {
    'polling_interval': 5.0,
    'socket_timeout': 5,
    'socket_connect_timeout': 5,
}
# CRITICAL COST FIX: Stop storing task execution results in Redis unless absolutely mandatory.
# If your backend tasks just execute logic (like cleaning up calls) and don't return data 
# to the frontend via task IDs, ignore the results entirely!
CELERY_TASK_IGNORE_RESULT = True  
CELERY_RESULT_BACKEND = None     # If IGNORE_RESULT is True, we don't need a backend database connection

# If you ABSOLUTELY need results for specific tasks, keep this line but override it 
# inside individual tasks using @shared_task(ignore_result=False)
# If keeping the backend, add an expiry to prevent endless storage:
# CELERY_RESULT_EXPIRE = 300  # Remove results after 5 minutes

# Celery performance tweaks for single-core / low-RAM servers
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'

# Disable background worker synchronization noise (Gossip/Mingo)
# This prevents workers from constantly chatting with each other via Redis
CELERY_WORKER_GOSSIP = False
CELERY_WORKER_MINGO = False
CELERY_WORKER_SEND_TASK_EVENTS = False

# Task limits
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60  
CELERY_TASK_SOFT_TIME_LIMIT = 25 * 60  

# Celery Beat Settings (Scheduled Tasks)
CELERY_BEAT_SCHEDULE = {
    'cleanup-stale-calls': {
        'task': 'consultations.cleanup_stale_calls',
        'schedule': 600.0,  # 10 minutes is a great balance
    },
}

# Celery worker settings
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_WORKER_MAX_TASKS_PER_CHILD = 500
CELERY_WORKER_LOG_FORMAT = '[%(levelname)s/%(processName)s] %(message)s'

# ==================== LOGGING CONFIGURATION ====================
# Reduces terminal spam from channels and daphne WebSocket messages

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
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
            'formatter': 'simple',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'daphne': {
            'handlers': ['console'],
            'level': 'WARNING',  # Reduce daphne verbosity
            'propagate': False,
        },
        'channels': {
            'handlers': ['console'],
            'level': 'WARNING',  # Reduce channels verbosity
            'propagate': False,
        },
        'channels_redis': {
            'handlers': ['console'],
            'level': 'WARNING',  # Reduce channels_redis verbosity
            'propagate': False,
        },
    },
}

# ==================== CACHING CONFIGURATION ====================

CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        # 1. Grab the live production REDIS_URL from your Render dashboard env,
        # otherwise fall back to building the local localhost string on DB index /0
        'LOCATION': config(
            'REDIS_URL',
            default=f"redis://{config('REDIS_HOST', default='localhost')}:{config('REDIS_PORT', default=6379)}/0"
        ),
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            'CONNECTION_POOL_CLASS': 'redis.connection.BlockingConnectionPool',
            'CONNECTION_POOL_CLASS_KWARGS': {
                'max_connections': 50,
                'timeout': 20,
            },
            'SOCKET_CONNECT_TIMEOUT': 5,
            'SOCKET_TIMEOUT': 5,
            'IGNORE_EXCEPTIONS': False,
        },
        'KEY_PREFIX': 'healthapp_cache',
        'TIMEOUT': 300,  # 5 minutes default timeout
    }
}

#SSL/TLS CONFIGURATION FOR PRODUCTION(Security settings to ensure secure connections and protect against common web vulnerabilities)
if not DEBUG:
    # Tell Django your app is running behind Render's secure proxy load balancer
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    
    # Handled natively at Render's routing layer; keep False here to protect WebSockets
    SECURE_SSL_REDIRECT = False 
    
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_SAMESITE = 'None'
    CSRF_COOKIE_SAMESITE = 'None'
    
    SECURE_HSTS_SECONDS = 31536000  # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True