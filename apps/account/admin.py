from django.contrib import admin
from django.contrib.contenttypes.admin import GenericTabularInline
from django.utils import timezone
from apps.account.models import (
    ListingImage,
    Role,
    User,
    HotelProfile,
    CompanyProfile,
    IndividualOwnerProfile,
    OtpChallenge,
)


class ListingImageInline(GenericTabularInline):
    model = ListingImage
    extra = 1  # how many empty slots to show
    fields = ("image", "alt_text", "is_primary")


def activate_hotels(modeladmin, request, queryset):
    updated = queryset.update(is_active=True, updated_at=timezone.now())
    modeladmin.message_user(request, f"Activated {updated} hotel(s).")


def deactivate_hotels(modeladmin, request, queryset):
    updated = queryset.update(is_active=False, updated_at=timezone.now())
    modeladmin.message_user(request, f"Deactivated {updated} hotel(s).")


@admin.register(HotelProfile)
class HotelProfileModelAdmin(admin.ModelAdmin):
    list_display = ["company", "stars", "featured", "is_active"]
    list_filter = ["featured", "is_active"]
    actions = [activate_hotels, deactivate_hotels]
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


@admin.register(OtpChallenge)
class OtpChallengeAdmin(admin.ModelAdmin):
    list_display = ("phone", "purpose", "user", "expires_at", "consumed_at", "attempts", "sent_at")
    list_filter = ("purpose", "consumed_at")
    search_fields = ("phone", "user__email")
    readonly_fields = (
        "user",
        "phone",
        "purpose",
        "code_hash",
        "expires_at",
        "consumed_at",
        "attempts",
        "max_attempts",
        "sent_at",
        "created_at",
        "updated_at",
    )


@admin.register(ListingImage)
class ListingImageAdmin(admin.ModelAdmin):
    list_display = ("content_type", "object_id", "alt_text", "is_primary", "created_at")
    search_fields = ("alt_text",)
    list_filter = ("is_primary", "content_type")
