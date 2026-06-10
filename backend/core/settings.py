"""
Django settings for core project.
Optimized for high-precision accounting and secure cross-platform mobile API communication.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(os.path.join(BASE_DIR, ".env"))

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-)z_s!)2u-il!g($kxw!8$!y=fld%#pq_pi*%n=sb3p9mc@612s",
)

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get("DJANGO_DEBUG", "True") == "True"

# Allow local machine, local network testing, and Android/iOS Emulator bridges
ALLOWED_HOSTS = ["*"]


# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Core Scaffolding Dependencies
    "rest_framework",
    "corsheaders",
    "rest_framework.authtoken",
    # Local Accounting and Engine Application (Mapped using the dynamic 'ledger' label)
    "tracker.apps.TrackerConfig",
]

# 🔌 ALIGNED AUTH MODEL LINK: Swapped 'tracker.User' to 'ledger.User' to match the app label configuration
AUTH_USER_MODEL = "ledger.User"

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",  # 🧼 DE-DUPLICATED: Placed strictly at the top of the stack
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "core.urls"

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

WSGI_APPLICATION = "core.wsgi.application"


# Database
# https://docs.djangoproject.com/en/6.0/ref/settings/#databases

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": os.environ.get("DB_NAME", "mywealth_sync_db"),
        "USER": os.environ.get("DB_USER", "root"),
        "PASSWORD": os.environ.get(
            "DB_PASSWORD"
        ),  # 🔐 Pulls cleanly from your .env file
        "HOST": os.environ.get("DB_HOST", "127.0.0.1"),
        "PORT": os.environ.get("DB_PORT", "3306"),
        "OPTIONS": {
            "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
        },
    }
}


# Password validation
# https://docs.djangoproject.com/en/6.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization
# https://docs.djangoproject.com/en/6.0/topics/i18n/

LANGUAGE_CODE = "en-us"

# Enforce Indian Standard Time (IST) for precise accounting logs
TIME_ZONE = "Asia/Kolkata"

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.0/howto/static-files/

STATIC_URL = "static/"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ==============================================================================
# SECURITY & NETWORK CONFIGURATIONS FOR MOBILE ACCESS
# ==============================================================================

CORS_ALLOWED_ORIGINS = [
    "http://localhost:8081",
    "http://127.0.0.1:8081",
]
CORS_ALLOW_ALL_ORIGINS = DEBUG

REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
}


# ==============================================================================
# GLOBAL ACCOUNTING APP CONSTANTS (Single Source of Truth)
# ==============================================================================

ACCOUNT_TYPES = [
    ("ASSET", "Asset (Bank, Wallet)"),
    ("LIABILITY", "Liability (Credit Cards, Loans)"),
    ("INCOME", "Income (Salary, Freelance Direct)"),
    ("EXPENSE", "Expense (Food, Fuel, Bills)"),
]

TRANSACTION_STATUS_CHOICES = [
    ("INTENT", "Scanned / Deep Link Dispatched"),
    ("UNRECONCILED", "Imported Log / Text Message Parsed"),
    ("VERIFIED", "Double-Entry Confirmed and Reconciled"),
    ("FAILED", "Failed / Cancelled Transaction"),
]
