from config.settings.base import *  # noqa F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "marefiya-test-cache",
    }
}

REST_FRAMEWORK = {
    **REST_FRAMEWORK,  # noqa F405
    "DEFAULT_THROTTLE_CLASSES": [],
}
