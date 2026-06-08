import logging
import secrets
from dataclasses import dataclass

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from apps.account.models import ListingImage, OtpChallenge
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
    user: object
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
    DEFAULT_TTL_SECONDS = 300
    DEFAULT_LENGTH = 6
    DEFAULT_MAX_ATTEMPTS = 5

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
    def _ttl_seconds(cls) -> int:
        return int(getattr(settings, "OTP_TTL_SECONDS", cls.DEFAULT_TTL_SECONDS))

    @classmethod
    def _max_attempts(cls) -> int:
        return int(getattr(settings, "OTP_MAX_ATTEMPTS", cls.DEFAULT_MAX_ATTEMPTS))

    @classmethod
    def create_challenge(cls, *, phone: str, purpose: str = OtpChallenge.Purpose.LOGIN) -> OtpChallenge:
        normalized_phone = cls.normalize_phone(phone)
        if not normalized_phone:
            raise OtpError("Phone number is required.")

        User = get_user_model()
        user_queryset = User.objects.filter(phone=normalized_phone)
        if purpose == OtpChallenge.Purpose.SIGNUP:
            user = user_queryset.filter(is_active=False, phone_verified_at__isnull=True).first()
        else:
            user = user_queryset.filter(is_active=True).first()
        if not user:
            if purpose == OtpChallenge.Purpose.SIGNUP:
                raise OtpError("No pending registration found for this phone number.")
            raise OtpError("No active account found for this phone number.")

        code = cls.generate_code()
        challenge = OtpChallenge.objects.create(
            user=user,
            phone=normalized_phone,
            purpose=purpose,
            code_hash=make_password(code),
            expires_at=timezone.now() + timezone.timedelta(seconds=cls._ttl_seconds()),
            max_attempts=cls._max_attempts(),
        )

        message = f"Your Mechot Marefiya verification code is {code}. It expires in {cls._ttl_seconds() // 60} minutes."
        try:
            from services.sms import send_sms

            send_sms(normalized_phone, message)
        except Exception:
            logger.exception("Failed to send OTP SMS to %s", normalized_phone)
            challenge.delete()
            raise

        challenge.sent_at = timezone.now()
        challenge.save(update_fields=["sent_at", "updated_at"])
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
            raise OtpError("Invalid OTP challenge.")
        if challenge.is_consumed:
            raise OtpError("OTP challenge has already been used.")
        if challenge.is_expired:
            raise OtpError("OTP challenge has expired.")
        if challenge.attempts >= challenge.max_attempts:
            raise OtpError("OTP attempt limit exceeded.")

        challenge.attempts += 1
        if not check_password(code, challenge.code_hash):
            challenge.save(update_fields=["attempts", "updated_at"])
            raise OtpError("Invalid OTP code.")

        challenge.consumed_at = timezone.now()
        challenge.save(update_fields=["attempts", "consumed_at", "updated_at"])

        if purpose == OtpChallenge.Purpose.SIGNUP:
            challenge.user.is_active = True
            challenge.user.phone_verified_at = timezone.now()
            challenge.user.save(update_fields=["is_active", "phone_verified_at", "updated_at"])

        tokens = None
        if issue_tokens:
            refresh = RefreshToken.for_user(challenge.user)
            tokens = {
                "refresh": str(refresh),
                "access": str(refresh.access_token),
            }

        return OtpVerificationResult(challenge=challenge, user=challenge.user, tokens=tokens)


class GuestBookingConversionService:
    MODEL_MAPPINGS = (
        ("hotel_bookings", "user", "Booking"),
        ("guesthouse_bookings", "renter", "GuestHouseBooking"),
        ("car_rentals", "renter", "CarRental"),
        ("eventspace_bookings", "user", "EventSpaceBooking"),
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

        from apps.listing.models import Booking, CarRental, EventSpaceBooking, GuestHouseBooking

        model_map = {
            "Booking": Booking,
            "GuestHouseBooking": GuestHouseBooking,
            "CarRental": CarRental,
            "EventSpaceBooking": EventSpaceBooking,
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
