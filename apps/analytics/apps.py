from django.apps import AppConfig


class AnalyticsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.analytics"
    verbose_name = "Analytics"
    def ready(self):
        # import signals to connect handlers
        try:
            from . import signals  # noqa: F401
        except Exception:
            pass
