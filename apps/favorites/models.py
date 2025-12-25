from django.conf import settings
from django.db import models
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from apps.core.models import AbstractBaseModel


class Favorite(AbstractBaseModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="favorites"
    )

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.CharField(max_length=255)
    content_object = GenericForeignKey("content_type", "object_id")
    # store a small, best-effort snapshot of the target object to avoid N+1 calls
    snapshot = models.JSONField(null=True, blank=True, default=dict)
    snapshot_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Favorite"
        verbose_name_plural = "Favorites"
        unique_together = ("user", "content_type", "object_id")

    def __str__(self):
        return f"Favorite: {self.user} -> {self.content_type.app_label}.{self.content_type.model}({self.object_id})"
