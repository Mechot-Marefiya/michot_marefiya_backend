from django.contrib import admin
from .models import Favorite


@admin.register(Favorite)
class FavoriteAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "content_type", "object_id", "snapshot_at", "created_at")
    search_fields = ("user__username", "object_id")
    readonly_fields = ("snapshot", "snapshot_at")
