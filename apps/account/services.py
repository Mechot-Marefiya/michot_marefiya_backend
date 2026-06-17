import logging
import os
import secrets
from dataclasses import dataclass

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password, make_password
from django.core.cache import cache
from django.core import signing
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework_simplejwt.tokens import RefreshToken

from apps.account.models import IndividualOwnerProfile, ListingImage, OtpChallenge, OwnerComplianceAgreement
from apps.account.tasks import OtpChallengeCache, send_otp_sms_task
from apps.favorites.models import Favorite, GuestFavorite

logger = logging.getLogger(__name__)


class ImageCreationService:
    @staticmethod
    def create_images(content_object, images_payload):
        # create images
        image_objs = []

        for img_file in images_payload:
            if hasattr(img_file, "is_primary"):
                is_primary = img_file.is_primary
            else:
                is_primary = False

            img_instance = ListingImage(
                content_object=content_object,
                image=img_file,
                alt_text=img_file.name,
                # TODO: Expect a metadata attached in the payload
                is_primary=is_primary,
            )
            image_objs.append(img_instance)

        images = ListingImage.objects.bulk_create(image_objs)

        print("Images Created", images)


class OtpError(Exception):
    """Raised when an OTP challenge cannot be issued or verified."""


@dataclass(frozen=True)
class OtpVerificationResult:
    challenge: OtpChallenge
    user: object | None
    tokens: dict | None = None


class GuestBookingConversionError(Exception):
    """Raised when guest bookings cannot be safely linked to a user."""


@dataclass(frozen=True)
class GuestBookingConversionResult:
    phone: str
    verified_via: str
    linked_counts: dict[str, int]
    already_linked_counts: dict[str, int]

    @property
    def linked_total(self) -> int:
        return sum(self.linked_counts.values())

    @property
    def already_linked_total(self) -> int:
        return sum(self.already_linked_counts.values())


class OtpService:
    DEFAULT_EXPIRY_SECONDS = 300
    DEFAULT_LENGTH = 6
    DEFAULT_MAX_ATTEMPTS = 5
    DEFAULT_COOLDOWN_SECONDS = 60
    GENERIC_VERIFY_ERROR = "Invalid OTP challenge or code."
    BOOKING_PURPOSES = {
        OtpChallenge.Purpose.GUEST_HOTEL_BOOKING,
        OtpChallenge.Purpose.GUEST_GUESTHOUSE_BOOKING,
        OtpChallenge.Purpose.GUEST_EVENTSPACE_BOOKING,
        OtpChallenge.Purpose.GUEST_CAR_RENTAL_BOOKING,
        OtpChallenge.Purpose.GUEST_PROPERTY_RENTAL_BOOKING,
        OtpChallenge.Purpose.GUEST_CAR_SALE_REVEAL,
        OtpChallenge.Purpose.GUEST_PROPERTY_SALE_REVEAL,
    }

    @staticmethod
    def normalize_phone(phone: str) -> str:
        value = (phone or "").strip().replace(" ", "").replace("-", "")
        if value.startswith("+251"):
            return "0" + value[4:]
        if value.startswith("251") and len(value) == 12:
            return "0" + value[3:]
        return value

    @classmethod
    def generate_code(cls) -> str:
        length = getattr(settings, "OTP_CODE_LENGTH", cls.DEFAULT_LENGTH)
        start = 10 ** (length - 1)
        end = (10 ** length) - 1
        return str(secrets.randbelow(end - start + 1) + start)

    @classmethod
    def _expiry_seconds(cls) -> int:
        return int(
            getattr(
                settings,
                "OTP_EXPIRY_SECONDS",
                getattr(settings, "OTP_TTL_SECONDS", cls.DEFAULT_EXPIRY_SECONDS),
            )
        )

    @classmethod
    def _max_attempts(cls) -> int:
        return int(getattr(settings, "OTP_MAX_ATTEMPTS", cls.DEFAULT_MAX_ATTEMPTS))

    @classmethod
    def _message_for_purpose(cls, purpose: str) -> str:
        minutes = max(cls._expiry_seconds() // 60, 1)
        if purpose in cls.BOOKING_PURPOSES:
            return f"Your Mechot Marefiya booking verification code is {{code}}. It expires in {minutes} minutes."
        return f"Your Mechot Marefiya verification code is {{code}}. It expires in {minutes} minutes."

    @classmethod
    def _resolve_user(cls, *, normalized_phone: str, purpose: str):
        User = get_user_model()
        user_queryset = User.objects.filter(phone=normalized_phone)
        if purpose == OtpChallenge.Purpose.SIGNUP:
            return user_queryset.filter(is_active=False, phone_verified_at__isnull=True).first()
        if purpose in cls.BOOKING_PURPOSES:
            return None
        return user_queryset.filter(is_active=True).first()

    @classmethod
    def _dispatch_sms_task(cls, challenge_id):
        if os.environ.get("DJANGO_SETTINGS_MODULE") == "config.settings.test":
            send_otp_sms_task.apply(args=[str(challenge_id)])
            return
        send_otp_sms_task.delay(str(challenge_id))

    @classmethod
    def create_challenge(cls, *, phone: str, purpose: str = OtpChallenge.Purpose.LOGIN) -> OtpChallenge:
        normalized_phone = cls.normalize_phone(phone)
        if not normalized_phone:
            raise OtpError("Phone number is required.")
        user = cls._resolve_user(normalized_phone=normalized_phone, purpose=purpose)
        if not user:
            if purpose == OtpChallenge.Purpose.SIGNUP:
                raise OtpError("No pending registration found for this phone number.")
            if purpose not in cls.BOOKING_PURPOSES:
                raise OtpError("No active account found for this phone number.")

        code = cls.generate_code()
        expires_at = timezone.now() + timezone.timedelta(seconds=cls._expiry_seconds())
        OtpChallenge.objects.filter(
            phone=normalized_phone,
            purpose=purpose,
            consumed_at__isnull=True,
        ).update(consumed_at=timezone.now(), updated_at=timezone.now())
        challenge = OtpChallenge.objects.create(
            user=user,
            phone=normalized_phone,
            purpose=purpose,
            code_hash=make_password(code),
            expires_at=expires_at,
            max_attempts=cls._max_attempts(),
        )
        message = cls._message_for_purpose(purpose).format(code=code)
        cache.set(
            OtpChallengeCache.pending_key(challenge.id),
            {"phone": normalized_phone, "message": message},
            timeout=cls._expiry_seconds(),
        )
        try:
            cls._dispatch_sms_task(challenge.id)
        except Exception as exc:
            logger.exception("Failed to queue OTP SMS for %s", normalized_phone)
            cache.delete(OtpChallengeCache.pending_key(challenge.id))
            challenge.delete()
            raise OtpError("Could not send OTP. Please try again.") from exc
        return challenge

    @classmethod
    def verify_challenge(
        cls,
        *,
        challenge_id,
        code: str,
        purpose: str = OtpChallenge.Purpose.LOGIN,
        issue_tokens: bool = False,
        user=None,
    ) -> OtpVerificationResult:
        queryset = OtpChallenge.objects.filter(
            id=challenge_id,
            purpose=purpose,
        )
        if user is not None:
            queryset = queryset.filter(user=user)

        challenge = queryset.first()
        if not challenge:
            raise OtpError(cls.GENERIC_VERIFY_ERROR)
        if challenge.is_consumed or challenge.is_expired or challenge.attempts >= challenge.max_attempts:
            raise OtpError(cls.GENERIC_VERIFY_ERROR)

        challenge.attempts += 1
        if not check_password(code, challenge.code_hash):
            challenge.save(update_fields=["attempts", "updated_at"])
            raise OtpError(cls.GENERIC_VERIFY_ERROR)

        challenge.consumed_at = timezone.now()
        challenge.save(update_fields=["attempts", "consumed_at", "updated_at"])
        cache.delete(OtpChallengeCache.pending_key(challenge.id))

        if purpose == OtpChallenge.Purpose.SIGNUP and challenge.user:
            challenge.user.is_active = True
            challenge.user.phone_verified_at = timezone.now()
            challenge.user.save(update_fields=["is_active", "phone_verified_at", "updated_at"])

        tokens = None
        if issue_tokens and challenge.user:
            refresh = RefreshToken.for_user(challenge.user)
            tokens = {
                "refresh": str(refresh),
                "access": str(refresh.access_token),
            }

        return OtpVerificationResult(challenge=challenge, user=challenge.user, tokens=tokens)


class GuestPhoneVerificationService:
    SALT = "guest-phone-verification"
    TOKEN_ERROR = "Guest phone verification is invalid or expired."

    @classmethod
    def create_token(cls, phone: str) -> str:
        normalized_phone = OtpService.normalize_phone(phone)
        if not normalized_phone:
            raise OtpError("Phone number is required.")
        return signing.dumps(
            {
                "phone": normalized_phone,
                "verified_at": timezone.now().isoformat(),
            },
            salt=cls.SALT,
        )

    @classmethod
    def verify_token(cls, *, token: str, phone: str) -> str:
        normalized_phone = OtpService.normalize_phone(phone)
        if not token or not normalized_phone:
            raise OtpError(cls.TOKEN_ERROR)

        max_age = getattr(settings, "GUEST_PHONE_VERIFICATION_MAX_AGE_SECONDS", None)
        try:
            payload = signing.loads(token, salt=cls.SALT, max_age=max_age)
        except signing.BadSignature as exc:
            raise OtpError(cls.TOKEN_ERROR) from exc

        if payload.get("phone") != normalized_phone:
            raise OtpError(cls.TOKEN_ERROR)
        return normalized_phone


class GuestBookingConversionService:
    MODEL_MAPPINGS = (
        ("hotel_bookings", "user", "Booking"),
        ("guesthouse_bookings", "renter", "GuestHouseBooking"),
        ("car_rentals", "renter", "CarRental"),
        ("eventspace_bookings", "user", "EventSpaceBooking"),
        ("property_rental_bookings", "renter", "PropertyRentalBooking"),
    )

    @staticmethod
    def phone_variants(phone: str) -> set[str]:
        normalized = OtpService.normalize_phone(phone)
        variants = {normalized}

        if normalized.startswith("0") and len(normalized) == 10:
            variants.add(f"251{normalized[1:]}")
            variants.add(f"+251{normalized[1:]}")
        elif normalized.startswith("251") and len(normalized) == 12:
            local = f"0{normalized[3:]}"
            variants.add(local)
            variants.add(f"+{normalized}")
        elif normalized.startswith("+251") and len(normalized) == 13:
            variants.add(normalized[1:])
            variants.add(f"0{normalized[4:]}")

        return {value for value in variants if value}

    @classmethod
    def convert_for_user(
        cls,
        *,
        user,
        otp_challenge_id=None,
        otp_code: str | None = None,
    ) -> GuestBookingConversionResult:
        normalized_phone = OtpService.normalize_phone(user.phone)
        if not normalized_phone:
            raise GuestBookingConversionError("Add a phone number to your account before converting guest bookings.")

        verified_via = "stored_phone_verification"
        if otp_challenge_id or otp_code:
            if not otp_challenge_id or not otp_code:
                raise GuestBookingConversionError("Both otp_challenge_id and otp_code are required together.")
            OtpService.verify_challenge(
                challenge_id=otp_challenge_id,
                code=otp_code,
                purpose=OtpChallenge.Purpose.LOGIN,
                issue_tokens=False,
                user=user,
            )
            verified_via = "otp"
        elif not user.phone_verified_at:
            raise GuestBookingConversionError(
                "Phone verification is required before converting guest bookings."
            )

        from apps.listing.models import Booking, CarRental, EventSpaceBooking, GuestHouseBooking, PropertyRentalBooking

        model_map = {
            "Booking": Booking,
            "GuestHouseBooking": GuestHouseBooking,
            "CarRental": CarRental,
            "EventSpaceBooking": EventSpaceBooking,
            "PropertyRentalBooking": PropertyRentalBooking,
        }
        phone_candidates = cls.phone_variants(user.phone)
        linked_counts: dict[str, int] = {}
        already_linked_counts: dict[str, int] = {}

        with transaction.atomic():
            for label, owner_field, model_name in cls.MODEL_MAPPINGS:
                model = model_map[model_name]
                queryset = model.objects.filter(guest_phone__in=phone_candidates)
                conflict = (
                    queryset.exclude(**{f"{owner_field}__isnull": True})
                    .exclude(**{owner_field: user})
                    .first()
                )
                if conflict is not None:
                    raise GuestBookingConversionError(
                        "Some guest bookings for this phone number are already linked to another account."
                    )

                already_linked_counts[label] = queryset.filter(**{owner_field: user}).count()
                linked_counts[label] = queryset.filter(**{f"{owner_field}__isnull": True}).update(
                    **{owner_field: user}
                )

            guest_favorites = GuestFavorite.objects.filter(guest_phone__in=phone_candidates)
            conflict = guest_favorites.exclude(linked_user__isnull=True).exclude(linked_user=user).first()
            if conflict is not None:
                raise GuestBookingConversionError(
                    "Some guest favorites for this phone number are already linked to another account."
                )

            guest_favorites_label = "guest_favorites"
            already_linked_counts[guest_favorites_label] = guest_favorites.filter(linked_user=user).count()
            linked_count = 0
            pending_guest_favorites = guest_favorites.filter(linked_user__isnull=True).select_related("content_type")
            for guest_favorite in pending_guest_favorites:
                Favorite.objects.get_or_create(
                    user=user,
                    content_type=guest_favorite.content_type,
                    object_id=str(guest_favorite.object_id),
                    defaults={
                        "snapshot": guest_favorite.snapshot or {},
                        "snapshot_at": guest_favorite.snapshot_at,
                    },
                )
                guest_favorite.linked_user = user
                guest_favorite.save(update_fields=["linked_user", "updated_at"])
                linked_count += 1
            linked_counts[guest_favorites_label] = linked_count

        return GuestBookingConversionResult(
            phone=normalized_phone,
            verified_via=verified_via,
            linked_counts=linked_counts,
            already_linked_counts=already_linked_counts,
        )


def _assert_admin_actor(admin):
    if admin is None or not getattr(admin, "is_authenticated", False):
        raise ValidationError("An authenticated admin user is required.")
    if not (
        getattr(admin, "is_superuser", False)
        or getattr(getattr(admin, "role", None), "code", None) == "admin"
    ):
        raise ValidationError("Only admins can manage owner compliance agreements.")


def _assert_individual_owner(owner):
    if not isinstance(owner, IndividualOwnerProfile):
        raise ValidationError("Compliance agreements apply only to individual owners.")


def get_latest_agreement(owner):
    _assert_individual_owner(owner)
    return owner.compliance_agreements.order_by("-created_at").first()


def create_agreement(owner, admin, version, note=None) -> OwnerComplianceAgreement:
    _assert_individual_owner(owner)
    _assert_admin_actor(admin)
    if not str(version or "").strip():
        raise ValidationError({"agreement_version": "Agreement version is required."})

    active_agreement = owner.compliance_agreements.filter(
        status=OwnerComplianceAgreement.Status.SIGNED
    ).first()
    if active_agreement:
        raise ValidationError("This owner already has an active signed compliance agreement.")

    latest = get_latest_agreement(owner)
    if latest and latest.status == OwnerComplianceAgreement.Status.PENDING:
        raise ValidationError("This owner already has a pending compliance agreement.")

    return OwnerComplianceAgreement.objects.create(
        owner=owner,
        status=OwnerComplianceAgreement.Status.PENDING,
        agreement_version=str(version).strip(),
        note=note or "",
    )


def sign_agreement(agreement, admin) -> OwnerComplianceAgreement:
    _assert_admin_actor(admin)
    if agreement.status == OwnerComplianceAgreement.Status.SIGNED:
        return agreement

    agreement.status = OwnerComplianceAgreement.Status.SIGNED
    agreement.signed_at = timezone.now()
    agreement.signed_by_admin = admin
    agreement.save(update_fields=["status", "signed_at", "signed_by_admin", "updated_at"])
    return agreement


def revoke_agreement(agreement, admin, note=None) -> OwnerComplianceAgreement:
    _assert_admin_actor(admin)
    agreement.status = OwnerComplianceAgreement.Status.REVOKED
    if note is not None:
        agreement.note = note
    agreement.save(update_fields=["status", "note", "updated_at"])
    return agreement


def is_agreement_active(owner) -> bool:
    _assert_individual_owner(owner)
    return owner.compliance_agreements.filter(
        status=OwnerComplianceAgreement.Status.SIGNED
    ).exists()
