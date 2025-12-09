from django.apps import AppConfig


class ListingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.listing"
    def ready(self):
            import apps.listing.signals