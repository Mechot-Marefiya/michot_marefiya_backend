from django.contrib import admin
from django.contrib.contenttypes.admin import GenericTabularInline
from apps.account.models import (
    ListingImage,
    Role,
    User,
    HotelProfile,
    CompanyProfile,
    IndividualOwnerProfile,
)


class ListingImageInline(GenericTabularInline):
    model = ListingImage
    extra = 1  # how many empty slots to show
    fields = ("image", "alt_text", "is_primary")


@admin.register(HotelProfile)
class HotelProfileModelAdmin(admin.ModelAdmin):
    list_display = ["stars", "company"]
    inlines = [ListingImageInline]


admin.site.register(Role)
from django.utils import timezone
from apps.account.enums import RoleCode


def approve_companies(modeladmin, request, queryset):
    try:
        role = Role.objects.get(code=RoleCode.COMPANY.value)
    except Role.DoesNotExist:
        modeladmin.message_user(request, "Company role not configured.")
        return

    for profile in queryset:
        profile.status = CompanyProfile.StatusChoice.APPROVED
        profile.approved_at = timezone.now()
        profile.approved_by = request.user
        profile.save()
        profile.user.role = role
        profile.user.save()


def reject_companies(modeladmin, request, queryset):
    for profile in queryset:
        profile.status = CompanyProfile.StatusChoice.REJECTED
        profile.rejection_reason = "Rejected by admin via Django admin action."
        profile.approved_at = timezone.now()
        profile.approved_by = request.user
        profile.save()


@admin.register(CompanyProfile)
class CompanyProfileAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "status", "approved_at", "approved_by")
    actions = [approve_companies, reject_companies]

admin.site.register(IndividualOwnerProfile)
admin.site.register(User)


@admin.register(ListingImage)
class ListingImageAdmin(admin.ModelAdmin):
    list_display = ("content_type", "object_id", "alt_text", "is_primary", "created_at")
    search_fields = ("alt_text",)
    list_filter = ("is_primary", "content_type")
