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
    OwnerComplianceAgreement,
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
from apps.account.services import revoke_agreement as revoke_owner_agreement_service, sign_agreement as sign_owner_agreement_service


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
    list_display = (
        "name",
        "user",
        "status",
        "split_config_active",
        "split_type",
        "split_value",
        "approved_at",
        "approved_by",
    )
    list_filter = ("status", "split_config_active", "split_type")
    search_fields = ("name", "user__email", "chapa_subaccount_id")
    actions = [approve_companies, reject_companies]


@admin.register(IndividualOwnerProfile)
class IndividualOwnerProfileAdmin(admin.ModelAdmin):
    list_display = (
        "first_name",
        "last_name",
        "phone",
        "split_config_active",
        "split_type",
        "split_value",
    )
    list_filter = ("split_config_active", "split_type")
    search_fields = ("first_name", "last_name", "phone", "chapa_subaccount_id")


admin.site.register(User)


def sign_owner_agreement(modeladmin, request, queryset):
    for agreement in queryset:
        sign_owner_agreement_service(agreement, request.user)
    modeladmin.message_user(request, f"Signed {queryset.count()} agreement(s).")


def revoke_owner_agreement(modeladmin, request, queryset):
    for agreement in queryset:
        revoke_owner_agreement_service(agreement, request.user)
    modeladmin.message_user(request, f"Revoked {queryset.count()} agreement(s).")


@admin.register(OwnerComplianceAgreement)
class OwnerComplianceAgreementAdmin(admin.ModelAdmin):
    list_display = ("owner", "status", "signed_at", "signed_by_admin", "agreement_version")
    list_filter = ("status",)
    search_fields = (
        "owner__first_name",
        "owner__last_name",
        "owner__phone",
        "owner__staff_members__email",
    )
    readonly_fields = ("signed_at", "signed_by_admin")
    actions = [sign_owner_agreement, revoke_owner_agreement]


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
