from django import forms
from django.contrib import admin, messages
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
from apps.account.services import (
    create_agreement as create_owner_agreement_service,
    ensure_individual_owner_login,
    revoke_agreement as revoke_owner_agreement_service,
    sign_agreement as sign_owner_agreement_service,
)


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


class IndividualOwnerProfileAdminForm(forms.ModelForm):
    agreement_status = forms.CharField(
        required=False,
        disabled=True,
        help_text="Current latest agreement status for this owner.",
    )
    agreement_document_status = forms.CharField(
        required=False,
        disabled=True,
        help_text="Shows whether the owner already has an uploaded agreement document.",
    )
    agreement_document = forms.FileField(
        required=False,
        help_text="Upload the signed owner compliance agreement document. Uploading a document signs the agreement.",
    )
    agreement_version = forms.CharField(
        required=False,
        initial="admin-created",
        help_text="Version to use when creating/signing a new agreement.",
    )
    agreement_note = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Optional note stored on the agreement.",
    )
    login_email = forms.EmailField(
        required=False,
        help_text="Optional. If empty, a phone-based placeholder email is used.",
    )
    login_password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=True),
        help_text="Optional. Leave blank to generate one when creating/resetting credentials.",
    )
    reset_login_password = forms.BooleanField(
        required=False,
        help_text="For existing owners, set/reset the login password.",
    )
    send_login_sms = forms.BooleanField(
        required=False,
        initial=True,
        help_text="Send generated or reset credentials to the owner's phone.",
    )

    class Meta:
        model = IndividualOwnerProfile
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            linked_user = self.instance.staff_members.order_by("created_at").first()
            if linked_user:
                self.fields["login_email"].initial = linked_user.email
            agreement = self.instance.compliance_agreements.order_by("-created_at").first()
            if agreement:
                self.fields["agreement_status"].initial = (
                    f"{agreement.status} ({agreement.agreement_version})"
                )
                self.fields["agreement_document_status"].initial = (
                    "uploaded" if agreement.agreement_document else "missing"
                )
                self.fields["agreement_version"].initial = agreement.agreement_version
                self.fields["agreement_note"].initial = agreement.note
            else:
                self.fields["agreement_status"].initial = "missing"
                self.fields["agreement_document_status"].initial = "missing"
        else:
            self.fields["agreement_status"].initial = "will be available after first save"
            self.fields["agreement_document_status"].initial = "will be available after first save"


@admin.register(IndividualOwnerProfile)
class IndividualOwnerProfileAdmin(admin.ModelAdmin):
    form = IndividualOwnerProfileAdminForm
    list_display = (
        "first_name",
        "last_name",
        "phone",
        "login_user",
        "split_config_active",
        "split_type",
        "split_value",
    )
    list_filter = ("split_config_active", "split_type")
    search_fields = ("first_name", "last_name", "phone", "chapa_subaccount_id")
    readonly_fields = ("login_user",)
    actions = []
    fieldsets = (
        (
            "Owner Profile",
            {
                "fields": (
                    "first_name",
                    "last_name",
                    "address",
                    "phone",
                    "national_id_number",
                )
            },
        ),
        (
            "Login Credentials",
            {
                "fields": (
                    "login_user",
                    "login_email",
                    "login_password",
                    "reset_login_password",
                    "send_login_sms",
                ),
                "description": (
                    "Individual owners log in through the normal phone + password endpoint. "
                    "Saving this profile creates or repairs the linked login user."
                ),
            },
        ),
        (
            "Owner Compliance Agreement",
            {
                "fields": (
                    "agreement_status",
                    "agreement_document_status",
                    "agreement_document",
                    "agreement_version",
                    "agreement_note",
                ),
                "description": (
                    "Property-rental booking is blocked until an individual owner has a signed "
                    "compliance agreement. Upload the agreement document and save to create/sign it here."
                ),
            },
        ),
        (
            "Payment Split",
            {
                "fields": (
                    "chapa_subaccount_id",
                    "split_type",
                    "split_value",
                    "split_config_active",
                )
            },
        ),
    )

    def _save_compliance_agreement_document_from_form(self, request, obj, form):
        uploaded_document = form.cleaned_data.get("agreement_document")
        if not uploaded_document:
            return

        signed_agreement = obj.compliance_agreements.filter(
            status=OwnerComplianceAgreement.Status.SIGNED
        ).first()
        if signed_agreement:
            signed_agreement.agreement_document = uploaded_document
            signed_agreement.save(update_fields=["agreement_document", "updated_at"])
            self.message_user(request, "Owner compliance agreement document updated.", messages.SUCCESS)
            return

        agreement = obj.compliance_agreements.filter(
            status=OwnerComplianceAgreement.Status.PENDING
        ).order_by("-created_at").first()
        if agreement is None:
            version = form.cleaned_data.get("agreement_version") or "admin-created"
            note = form.cleaned_data.get("agreement_note") or "Created from Django admin owner detail."
            agreement = create_owner_agreement_service(
                obj,
                request.user,
                version=version,
                note=note,
                agreement_document=uploaded_document,
            )
        else:
            changed_fields = []
            version = form.cleaned_data.get("agreement_version")
            note = form.cleaned_data.get("agreement_note")
            if version and agreement.agreement_version != version:
                agreement.agreement_version = version
                changed_fields.append("agreement_version")
            if note is not None and agreement.note != note:
                agreement.note = note
                changed_fields.append("note")
            agreement.agreement_document = uploaded_document
            changed_fields.append("agreement_document")
            if changed_fields:
                changed_fields.append("updated_at")
                agreement.save(update_fields=changed_fields)

        sign_owner_agreement_service(agreement, request.user)
        self.message_user(request, "Owner compliance agreement document uploaded and signed.", messages.SUCCESS)

    def login_user(self, obj):
        if not obj or not obj.pk:
            return "Will be created on save."
        user = obj.staff_members.order_by("created_at").first()
        return user.email if user else "Missing - save to create credentials."

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        self._save_compliance_agreement_document_from_form(request, obj, form)
        result = ensure_individual_owner_login(
            obj,
            email=form.cleaned_data.get("login_email"),
            password=form.cleaned_data.get("login_password"),
            send_credentials_sms=form.cleaned_data.get("send_login_sms", True),
            reset_password=bool(form.cleaned_data.get("reset_login_password")),
        )

        if result.created:
            self.message_user(request, "Created linked individual-owner login user.", messages.SUCCESS)
        elif result.password_changed:
            self.message_user(request, "Updated individual-owner login password.", messages.SUCCESS)
        else:
            self.message_user(request, "Individual-owner login user is linked and active.", messages.INFO)

        if result.password_changed:
            if result.sms_sent:
                self.message_user(request, "Login credentials were sent by SMS.", messages.SUCCESS)
            elif result.sms_error:
                self.message_user(
                    request,
                    f"SMS failed: {result.sms_error}. Temporary password: {result.password}",
                    messages.WARNING,
                )
            else:
                self.message_user(
                    request,
                    f"SMS was not sent. Temporary password: {result.password}",
                    messages.WARNING,
                )


admin.site.register(User)


def sign_owner_agreement(modeladmin, request, queryset):
    signed_count = 0
    skipped_count = 0
    for agreement in queryset:
        if not agreement.agreement_document:
            skipped_count += 1
            continue
        sign_owner_agreement_service(agreement, request.user)
        signed_count += 1
    modeladmin.message_user(
        request,
        f"Signed {signed_count} agreement(s). Skipped {skipped_count} without documents.",
    )


def revoke_owner_agreement(modeladmin, request, queryset):
    for agreement in queryset:
        revoke_owner_agreement_service(agreement, request.user)
    modeladmin.message_user(request, f"Revoked {queryset.count()} agreement(s).")


@admin.register(OwnerComplianceAgreement)
class OwnerComplianceAgreementAdmin(admin.ModelAdmin):
    list_display = ("owner", "status", "has_document", "signed_at", "signed_by_admin", "agreement_version")
    list_filter = ("status",)
    search_fields = (
        "owner__first_name",
        "owner__last_name",
        "owner__phone",
        "owner__staff_members__email",
    )
    readonly_fields = ("signed_at", "signed_by_admin")
    actions = [sign_owner_agreement, revoke_owner_agreement]

    def has_document(self, obj):
        return bool(obj.agreement_document)

    has_document.boolean = True


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
