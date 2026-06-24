from .base import *  # noqa: F403,F401

DEBUG = env("DEBUG", default=False, cast=bool)  # noqa: F405

MIDDLEWARE = list(MIDDLEWARE)  # noqa: F405
security_middleware = "django.middleware.security.SecurityMiddleware"
whitenoise_middleware = "whitenoise.middleware.WhiteNoiseMiddleware"
if whitenoise_middleware not in MIDDLEWARE and security_middleware in MIDDLEWARE:
    security_index = MIDDLEWARE.index(security_middleware)
    MIDDLEWARE.insert(security_index + 1, whitenoise_middleware)

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

SECURE_SSL_REDIRECT = env("SECURE_SSL_REDIRECT", default=True, cast=bool)  # noqa: F405
SESSION_COOKIE_SECURE = env("SESSION_COOKIE_SECURE", default=True, cast=bool)  # noqa: F405
CSRF_COOKIE_SECURE = env("CSRF_COOKIE_SECURE", default=True, cast=bool)  # noqa: F405
SECURE_HSTS_SECONDS = env("SECURE_HSTS_SECONDS", default=31536000, cast=int)  # noqa: F405
SECURE_HSTS_INCLUDE_SUBDOMAINS = env(
    "SECURE_HSTS_INCLUDE_SUBDOMAINS",
    default=True,
    cast=bool,
)  # noqa: F405
SECURE_HSTS_PRELOAD = env("SECURE_HSTS_PRELOAD", default=True, cast=bool)  # noqa: F405
SECURE_CONTENT_TYPE_NOSNIFF = env("SECURE_CONTENT_TYPE_NOSNIFF", default=True, cast=bool)  # noqa: F405
USE_X_FORWARDED_HOST = env("USE_X_FORWARDED_HOST", default=True, cast=bool)  # noqa: F405
WHITENOISE_MAX_AGE = env("WHITENOISE_MAX_AGE", default=31536000, cast=int)  # noqa: F405
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

frontend_url = env("FRONTEND_URL", default="").rstrip("/")  # noqa: F405
cors_allowed_origins = env.list("CORS_ALLOWED_ORIGINS", default=[])  # noqa: F405
if frontend_url and frontend_url not in cors_allowed_origins:
    cors_allowed_origins.append(frontend_url)

if cors_allowed_origins:
    CORS_ALLOWED_ORIGINS = cors_allowed_origins
    CORS_ALLOW_ALL_ORIGINS = False
