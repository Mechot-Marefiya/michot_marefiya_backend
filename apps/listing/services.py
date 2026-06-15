import logging
from dataclasses import dataclass
from datetime import date, timedelta, datetime
from uuid import uuid4
from django.conf import settings
from django.core.cache import cache
from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.db.models import Count, F, Min,Q
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.utils import timezone
from django.conf import settings
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple,Any,List
from rest_framework.exceptions import ValidationError
from decimal import Decimal
from apps.account.models import CompanyProfile, HotelProfile, OtpChallenge
from apps.account.services import (
    GuestPhoneVerificationService,
    ImageCreationService,
    OtpError,
    OtpService,
)
from apps.core.models import Address,Facility
from apps.listing.exceptions import BookingConflict
from apps.listing.models import (
    Amenity,
    Booking,
    BookingItem,
    GuestHouseBooking,
    GuestHouseBookingItem,
    PropertyRentalAvailability,
    PropertyRentalBooking,
    PropertyListing,
    RoomListing,
    StayAvailability,EventSpaceListing,
    Transaction,CarAvailability,EventSpaceAvailability,
    Season, SeasonalRate, BookingItemPrice, RoomInventory,
    CarListing,
    EventSpaceBooking,
    EventSpaceBookingItem,
    CarRental,
    CarRentalExtensionRequest,
    CarRentalItem,
    GuestHouseRoom, GuestHouseInventory, GuestHouseProfile
)

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError as DjangoValidationError
from apps.listing.models import TermsAndConditions
from apps.listing.models import RoomListing, RoomInventory
from apps.core.utils import convert_currency
from apps.core.services.email_service import BookingEmailService, has_deliverable_email
from apps.notifications.services import NotificationService
from apps.notifications.models import Notification
from services.sms import normalize_phone_number, send_sms



logger = logging.getLogger(__name__)
_VERIFICATION_NOTE_UNSET = object()


def _booking_confirmation_phone(booking):
    return (
        getattr(booking, "guest_phone", None)
        or getattr(getattr(booking, "user", None), "phone", None)
        or getattr(getattr(booking, "renter", None), "phone", None)
    )


def _send_booking_confirmation_sms_first(booking, *, label="booking"):
    phone = _booking_confirmation_phone(booking)
    if phone:
        check_in = getattr(booking, "check_in_date", getattr(booking, "start_date", None))
        check_out = getattr(booking, "check_out_date", getattr(booking, "end_date", None))
        message = (
            f"Your Mechot Marefiya {label} {booking.booking_reference} is confirmed"
            f"{f' for {check_in} to {check_out}' if check_in and check_out else ''}. "
            f"Total: {booking.total_price} {booking.currency}."
        )
        try:
            send_sms(phone, message)
        except Exception as exc:
            logger.warning(
                "Could not send %s confirmation SMS for %s: %s",
                label,
                getattr(booking, "id", None),
                exc,
            )

    if has_deliverable_email(getattr(booking, "guest_email", "")):
        BookingEmailService.send_booking_confirmation(booking)


class ListingGeocodingService:
    @staticmethod
    def schedule(instance, should_dispatch: bool = True) -> bool:
        if not should_dispatch or instance is None:
            return False

        address = getattr(instance, "address", None)
        if address is None:
            return False

        from apps.listing.tasks import geocode_listing_async

        model_label = f"{instance._meta.app_label}.{instance._meta.model_name}"

        transaction.on_commit(
            lambda: geocode_listing_async.delay(instance.pk, model_label)
        )
        return True


def verify_listing(listing, actor, verification_note=_VERIFICATION_NOTE_UNSET):
    if actor is None or not getattr(actor, "is_authenticated", False):
        raise ValidationError("Authenticated admin user is required for verification.")

    listing.is_verified = True
    listing.verified_at = timezone.now()
    listing.verified_by = actor
    update_fields = ["is_verified", "verified_at", "verified_by", "updated_at"]

    if hasattr(listing, "verification_note") and verification_note is not _VERIFICATION_NOTE_UNSET:
        listing.verification_note = verification_note
        update_fields.append("verification_note")

    listing.save(update_fields=update_fields)
    return listing


def unverify_listing(listing, actor):
    if actor is None or not getattr(actor, "is_authenticated", False):
        raise ValidationError("Authenticated admin user is required for verification.")

    listing.is_verified = False
    listing.verified_at = None
    listing.verified_by = None
    update_fields = ["is_verified", "verified_at", "verified_by", "updated_at"]

    if hasattr(listing, "verification_note"):
        listing.verification_note = None
        update_fields.append("verification_note")

    listing.save(update_fields=update_fields)
    return listing


class GuestBookingOtpError(Exception):
    """Raised when guest booking OTP verification fails."""


@dataclass(frozen=True)
class GuestBookingOtpChallenge:
    challenge_id: str
    phone: str
    booking_type: str
    expires_at: object


class GuestBookingOtpService:
    PURPOSE_MAP = {
        "hotel": OtpChallenge.Purpose.GUEST_HOTEL_BOOKING,
        "guesthouse": OtpChallenge.Purpose.GUEST_GUESTHOUSE_BOOKING,
        "eventspace": OtpChallenge.Purpose.GUEST_EVENTSPACE_BOOKING,
        "car_rental": OtpChallenge.Purpose.GUEST_CAR_RENTAL_BOOKING,
        "property_rental": OtpChallenge.Purpose.GUEST_PROPERTY_RENTAL_BOOKING,
    }

    @classmethod
    def _purpose_for_booking_type(cls, booking_type: str) -> str:
        purpose = cls.PURPOSE_MAP.get(booking_type)
        if not purpose:
            raise GuestBookingOtpError("Invalid booking type.")
        return purpose

    @classmethod
    def create_challenge(cls, *, phone: str, booking_type: str) -> GuestBookingOtpChallenge:
        try:
            challenge = OtpService.create_challenge(
                phone=phone,
                purpose=cls._purpose_for_booking_type(booking_type),
            )
        except Exception as exc:
            raise GuestBookingOtpError(str(exc)) from exc

        return GuestBookingOtpChallenge(
            challenge_id=str(challenge.id),
            phone=challenge.phone,
            booking_type=booking_type,
            expires_at=challenge.expires_at,
        )

    @classmethod
    def verify_challenge(cls, *, challenge_id, code: str, phone: str, booking_type: str):
        try:
            challenge = OtpChallenge.objects.filter(id=challenge_id).only("phone").first()
            normalized_phone = OtpService.normalize_phone(phone)
            if not challenge or challenge.phone != normalized_phone:
                raise GuestBookingOtpError(OtpService.GENERIC_VERIFY_ERROR)
            OtpService.verify_challenge(
                challenge_id=challenge_id,
                code=code,
                purpose=cls._purpose_for_booking_type(booking_type),
                issue_tokens=False,
            )
            return GuestPhoneVerificationService.create_token(normalized_phone)
        except Exception as exc:
            if isinstance(exc, GuestBookingOtpError):
                raise
            raise GuestBookingOtpError(str(exc)) from exc

    @staticmethod
    def verify_guest_token(*, token: str, phone: str):
        try:
            return GuestPhoneVerificationService.verify_token(token=token, phone=phone)
        except OtpError as exc:
            raise GuestBookingOtpError(str(exc)) from exc


class GuestContactRevealOtpService:
    PURPOSE_MAP = {
        "car_sale_reveal": OtpChallenge.Purpose.GUEST_CAR_SALE_REVEAL,
        "property_sale_reveal": OtpChallenge.Purpose.GUEST_PROPERTY_SALE_REVEAL,
    }

    @classmethod
    def _purpose_for_reveal_type(cls, reveal_type: str) -> str:
        purpose = cls.PURPOSE_MAP.get(reveal_type)
        if not purpose:
            raise GuestBookingOtpError("Invalid reveal type.")
        return purpose

    @classmethod
    def create_challenge(cls, *, phone: str, reveal_type: str) -> GuestBookingOtpChallenge:
        try:
            challenge = OtpService.create_challenge(
                phone=phone,
                purpose=cls._purpose_for_reveal_type(reveal_type),
            )
        except Exception as exc:
            raise GuestBookingOtpError(str(exc)) from exc

        return GuestBookingOtpChallenge(
            challenge_id=str(challenge.id),
            phone=challenge.phone,
            booking_type=reveal_type,
            expires_at=challenge.expires_at,
        )

    @classmethod
    def verify_challenge(cls, *, challenge_id, code: str, phone: str, reveal_type: str):
        try:
            challenge = OtpChallenge.objects.filter(id=challenge_id).only("phone").first()
            normalized_phone = OtpService.normalize_phone(phone)
            if not challenge or challenge.phone != normalized_phone:
                raise GuestBookingOtpError(OtpService.GENERIC_VERIFY_ERROR)
            OtpService.verify_challenge(
                challenge_id=challenge_id,
                code=code,
                purpose=cls._purpose_for_reveal_type(reveal_type),
                issue_tokens=False,
            )
            return GuestPhoneVerificationService.create_token(normalized_phone)
        except Exception as exc:
            if isinstance(exc, GuestBookingOtpError):
                raise
            raise GuestBookingOtpError(str(exc)) from exc

    @staticmethod
    def verify_guest_token(*, token: str, phone: str):
        try:
            return GuestPhoneVerificationService.verify_token(token=token, phone=phone)
        except OtpError as exc:
            raise GuestBookingOtpError(str(exc)) from exc

DEFAULT_PLATFORM_FEE_RATE = Decimal("0.05")
BOOKING_PHONE_SOURCES = (
    (Booking, "user", "guest_phone"),
    (GuestHouseBooking, "renter", "guest_phone"),
    (EventSpaceBooking, "user", "guest_phone"),
    (CarRental, "renter", "guest_phone"),
)


def _phone_variants(phone: Optional[str]) -> List[str]:
    if not phone:
        return []

    stripped = str(phone).strip().replace(" ", "").replace("-", "")
    variants = {stripped}

    normalized = normalize_phone_number(stripped)
    if normalized:
        variants.add(normalized)
        if normalized.startswith("251"):
            variants.add(f"+{normalized}")
            variants.add(f"0{normalized[3:]}")

    return [variant for variant in variants if variant]


def _resolve_booking_phone_identity(booking=None, user=None, phone: Optional[str] = None) -> Optional[str]:
    candidates = []

    if phone:
        candidates.append(phone)

    if user is not None:
        candidates.append(getattr(user, "phone", None))

    if booking is not None:
        candidates.append(getattr(booking, "guest_phone", None))
        owner = getattr(booking, "user", None) or getattr(booking, "renter", None)
        if owner is not None:
            candidates.append(getattr(owner, "phone", None))

    for candidate in candidates:
        normalized = normalize_phone_number(candidate)
        if normalized:
            return normalized

    return None


def has_prior_booking_for_phone(phone: Optional[str], exclude_booking=None) -> bool:
    variants = _phone_variants(phone)
    if not variants:
        return False

    for model, owner_field, guest_field in BOOKING_PHONE_SOURCES:
        query = Q(**{f"{guest_field}__in": variants}) | Q(**{f"{owner_field}__phone__in": variants})
        if exclude_booking is not None and isinstance(exclude_booking, model):
            query &= ~Q(pk=exclude_booking.pk)
        if model.objects.filter(query).exists():
            return True

    return False


def get_effective_platform_fee_rate(*, booking=None, user=None, phone: Optional[str] = None, exclude_booking=None):
    phone_identity = _resolve_booking_phone_identity(booking=booking, user=user, phone=phone)
    if phone_identity and not has_prior_booking_for_phone(phone_identity, exclude_booking=exclude_booking or booking):
        return Decimal("0.00")

    fee_rate = getattr(settings, "PLATFORM_FEE_RATE", DEFAULT_PLATFORM_FEE_RATE)
    if not isinstance(fee_rate, Decimal):
        fee_rate = Decimal(str(fee_rate))
    return fee_rate


class ListingService:
    @staticmethod
    def schedule_geocoding(instance, should_dispatch: bool = True) -> bool:
        return ListingGeocodingService.schedule(instance, should_dispatch=should_dispatch)

    @staticmethod
    @transaction.atomic()
    def create_room_listing(validated_data: dict):
        validated_data.setdefault("is_active", False)
        skip_async_geocoding = bool(validated_data.pop("_skip_async_geocoding", False))
        hotel_id = validated_data.pop("hotel_id")
        images = validated_data.pop("images")
        address_data = validated_data.pop("address", None)
        amenity_ids = validated_data.pop("amenities")

        # Get hotel instance (validation already done in serializer)
        hotel_profile = get_object_or_404(HotelProfile, id=hotel_id)

        # Handle address: use branch address if provided, otherwise use company HQ address
        if address_data:
            address_instance = ListingService.create_address(address_data)
        else:
            address_instance = hotel_profile.company.address

        # Create room listing
        room_listing_instance = RoomListing.objects.create(
            hotel=hotel_profile, address=address_instance, **validated_data
        )

        # Set amenities
        room_listing_instance.amenities.set(amenity_ids)

        # Create images
        ImageCreationService.create_images(room_listing_instance, images)

        # Create availability records for the room
        StayAvailabilityService.create_availability(
            hotel_profile,
            room_listing_instance,
            room_listing_instance.total_units
        )

        ListingGeocodingService.schedule(room_listing_instance, should_dispatch=not skip_async_geocoding)

        return room_listing_instance

    @staticmethod
    @staticmethod
    @transaction.atomic()
    def create_guest_house_listing(validated_data: dict):
        validated_data.setdefault("is_active", False)
        skip_async_geocoding = bool(validated_data.pop("_skip_async_geocoding", False))
        images = validated_data.pop("images", [])
        address_data = validated_data.pop("address", None)
        amenity_ids = validated_data.pop("amenities", [])
        facility_ids = validated_data.pop("facilities", [])
        
        # determine owner and fallback address
        company = validated_data.get("company")
        individual_owner = validated_data.get("individual_owner")
        
        if address_data:
            address_instance = ListingService.create_address(address_data)
        elif company:
            address_instance = company.address
        elif individual_owner:
            address_instance = individual_owner.address
        else:
             raise ValidationError("Address is required.")

        guest_house_profile = GuestHouseProfile.objects.create(
            address=address_instance,
            **validated_data,
        )
        
        amenities = []
        for id in amenity_ids:
            instance = get_object_or_404(Amenity, id=id)
            amenities.append(instance)
        guest_house_profile.amenities.set(amenities)
        
        facilities = []
        for id in facility_ids:
            instance = get_object_or_404(Facility, id=id)
            facilities.append(instance)
        guest_house_profile.facility.set(facilities)
        
        ImageCreationService.create_images(guest_house_profile, images)

        ListingGeocodingService.schedule(guest_house_profile, should_dispatch=not skip_async_geocoding)

        return guest_house_profile


    @staticmethod
    @transaction.atomic()
    def create_property_listing(validated_data: dict):
        validated_data.setdefault("is_active", False)
        skip_async_geocoding = bool(validated_data.pop("_skip_async_geocoding", False))
        images = validated_data.pop("images", [])
        address_data = validated_data.pop("address", None)
        
        company = validated_data.get("company")
        individual_owner = validated_data.get("individual_owner")

        if address_data:
            address_instance = ListingService.create_address(address_data)
        elif company:
            address_instance = company.address
        elif individual_owner:
            address_instance = individual_owner.address
        else:
            raise ValidationError("Address is required.")

        property_listing_instance = PropertyListing.objects.create(
            address=address_instance,
            **validated_data,
        )

        ImageCreationService.create_images(property_listing_instance, images)

        ListingGeocodingService.schedule(property_listing_instance, should_dispatch=not skip_async_geocoding)

        return property_listing_instance

    @staticmethod
    @transaction.atomic()
    def create_event_space_listing(validated_data: dict):
        validated_data.setdefault("is_active", False)
        skip_async_geocoding = bool(validated_data.pop("_skip_async_geocoding", False))
        images = validated_data.pop("images", [])
        address_data = validated_data.pop("address", None)
        amenity_ids = validated_data.pop("amenities", [])
        
        company_id = validated_data.pop("company_id")
        hotel = get_object_or_404(HotelProfile, company__id=company_id)
        
        if address_data:
            address_instance = ListingService.create_address(address_data)
        else:
            address_instance = hotel.company.address

        instance = EventSpaceListing.objects.create(
            hotel=hotel,
            address=address_instance,
            **validated_data
        )
        
        amenities = []
        for id in amenity_ids:
            amenities.append(get_object_or_404(Amenity, id=id))
        instance.amenities.set(amenities)

        ImageCreationService.create_images(instance, images)
        
        EventSpaceAvailabilityService.create_availability(
            instance, instance.total_units
        )

        ListingGeocodingService.schedule(instance, should_dispatch=not skip_async_geocoding)

        return instance

    @staticmethod
    def get_or_create_address(address_data: dict) -> Address:
        """
        Get existing address or create new one.
        Prevents duplicate addresses by normalizing and matching on key fields.
        """
        if not address_data:
            return None
            
        # Normalize data for matching
        street = address_data.get('street_line1', '').strip()
        city = address_data.get('city', '').strip()
        country = address_data.get('country', 'Ethiopia').strip()
        sub_city = address_data.get('sub_city', '').strip()
        
        # Try to find existing address
        existing = Address.objects.filter(
            street_line1__iexact=street,
            city__iexact=city,
            country__iexact=country,
            sub_city__iexact=sub_city,
        ).first()
        
        if existing:
            return existing
        
        # Create new if not found
        return Address.objects.create(**address_data)
    
    @staticmethod
    def create_address(address_data) -> Address:
        """
        Legacy method - use get_or_create_address instead.
        Kept for backward compatibility.
        """
        return ListingService.get_or_create_address(address_data)

    @staticmethod
    def _clear_geocoding_fields(instance):
        update_fields = []
        for field_name in ("latitude", "longitude", "formatted_address", "place_id", "address_components"):
            if hasattr(instance, field_name):
                setattr(instance, field_name, None)
                update_fields.append(field_name)

        if update_fields:
            if hasattr(instance, "updated_at"):
                update_fields.append("updated_at")
            instance.save(update_fields=update_fields)

    @staticmethod
    def _update_address(instance, address_data, *, reset_geocoding: bool = True):
        if not address_data:
            return False

        address = instance.address
        
        new_address = ListingService.get_or_create_address(address_data)
        if instance.address != new_address:
            instance.address = new_address
            update_fields = ["address"]
            if hasattr(instance, "updated_at"):
                update_fields.append("updated_at")
            instance.save(update_fields=update_fields)
            if reset_geocoding:
                ListingService._clear_geocoding_fields(instance)
            return True
        return False

    @staticmethod
    def _update_images(instance, new_images, kept_image_ids):
        from apps.account.models import ListingImage
        from django.contrib.contenttypes.models import ContentType
        
        ct = ContentType.objects.get_for_model(instance)
        
        if kept_image_ids is not None:
            ListingImage.objects.filter(
                content_type=ct, 
                object_id=instance.id
            ).exclude(
                id__in=kept_image_ids
            ).delete()
            
        if new_images:
            ImageCreationService.create_images(instance, new_images)

    @staticmethod
    @transaction.atomic()
    def update_room_listing(instance: RoomListing, validated_data: dict, kept_image_ids: list = None):
        skip_async_geocoding = bool(validated_data.pop("_skip_async_geocoding", False))
        images = validated_data.pop("images", [])
        address_data = validated_data.pop("address", None)
        amenity_ids = validated_data.pop("amenities", None)
        
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        if address_data:
            ListingService._update_address(instance, address_data, reset_geocoding=not skip_async_geocoding)
            ListingGeocodingService.schedule(instance, should_dispatch=not skip_async_geocoding)
              
        if amenity_ids is not None:
            instance.amenities.set(amenity_ids)
            
        ListingService._update_images(instance, images, kept_image_ids)
        
        return instance

    @staticmethod
    @transaction.atomic()
    def update_guest_house_profile(instance: GuestHouseProfile, validated_data: dict, kept_image_ids: list = None):
        skip_async_geocoding = bool(validated_data.pop("_skip_async_geocoding", False))
        images = validated_data.pop("images", [])
        address_data = validated_data.pop("address", None)
        amenity_ids = validated_data.pop("amenities", None)
        facility_ids = validated_data.pop("facilities", None)
        
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        if address_data:
            ListingService._update_address(instance, address_data, reset_geocoding=not skip_async_geocoding)
            ListingGeocodingService.schedule(instance, should_dispatch=not skip_async_geocoding)
        
        if amenity_ids is not None:
            instance.amenities.set(Amenity.objects.filter(id__in=amenity_ids))
            
        if facility_ids is not None:
             instance.facilities.set(Facility.objects.filter(id__in=facility_ids))
             
        ListingService._update_images(instance, images, kept_image_ids)
        return instance

    @staticmethod
    @transaction.atomic()
    def update_event_space_listing(instance: EventSpaceListing, validated_data: dict, kept_image_ids: list = None):
        skip_async_geocoding = bool(validated_data.pop("_skip_async_geocoding", False))
        images = validated_data.pop("images", [])
        address_data = validated_data.pop("address", None)
        amenity_ids = validated_data.pop("amenities", None)
        
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        if address_data:
            ListingService._update_address(instance, address_data, reset_geocoding=not skip_async_geocoding)
            ListingGeocodingService.schedule(instance, should_dispatch=not skip_async_geocoding)
              
        if amenity_ids is not None:
            instance.amenities.set(Amenity.objects.filter(id__in=amenity_ids))
            
        ListingService._update_images(instance, images, kept_image_ids)
        return instance

    @staticmethod
    @transaction.atomic()
    def update_property_listing(instance: PropertyListing, validated_data: dict, kept_image_ids: list = None):
        skip_async_geocoding = bool(validated_data.pop("_skip_async_geocoding", False))
        images = validated_data.pop("images", [])
        address_data = validated_data.pop("address", None)
        
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        if address_data:
            ListingService._update_address(instance, address_data, reset_geocoding=not skip_async_geocoding)
            ListingGeocodingService.schedule(instance, should_dispatch=not skip_async_geocoding)
              
        ListingService._update_images(instance, images, kept_image_ids)
        return instance
    
    @staticmethod
    @transaction.atomic()
    def update_hotel_profile(instance: HotelProfile, validated_data: dict, kept_image_ids: list = None):        
        skip_async_geocoding = bool(validated_data.pop("_skip_async_geocoding", False))
        company_data = validated_data.pop("company", {})
        address_data = validated_data.pop("address", None)
        images = validated_data.pop("images", [])
        facility_ids = validated_data.pop("facilities", None)
        
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        if company_data:
            company = instance.company
            company_address_data = company_data.pop("address", None)
            
            for attr, value in company_data.items():
                setattr(company, attr, value)
            company.save()
            
            if company_address_data:
                 ListingService._update_address(company, company_address_data)

        if address_data:
            ListingService._update_address(instance, address_data, reset_geocoding=not skip_async_geocoding)
            ListingGeocodingService.schedule(instance, should_dispatch=not skip_async_geocoding)

        if facility_ids is not None:
               instance.facilities.set(Facility.objects.filter(id__in=facility_ids))
             
        ListingService._update_images(instance, images, kept_image_ids)
        
        return instance


class TermsService:
    
    @staticmethod
    def get_active_terms(content_object):
        # Get active T&C for a hotel/guesthouse/event space/company.
        
        from django.contrib.contenttypes.models import ContentType
        from apps.listing.models import TermsAndConditions
        
        ct = ContentType.objects.get_for_model(content_object)
        
        terms = TermsAndConditions.objects.filter(
            content_type=ct,
            object_id=content_object.id,
            is_active=True
        ).order_by('-effective_date').first()
        
        return terms
    
    @staticmethod
    def validate_and_snapshot_terms(
        content_object,
        terms_version: str,
        terms_accepted: bool,
        allow_missing: bool = False
    ) -> dict:
        
        if not terms_accepted:
            if allow_missing:
                return {
                    'version': terms_version or "WALK-IN",
                    'content_snapshot': "Terms accepted in person (Walk-in)",
                    'accepted_at': timezone.now()
                }
            raise DjangoValidationError("Terms and conditions must be accepted.")
        
        ct = ContentType.objects.get_for_model(content_object)
        terms = TermsAndConditions.objects.filter(
            content_type=ct,
            object_id=content_object.id,
            version=terms_version,
            is_active=True
        ).first()
        
        if not terms:
            raise DjangoValidationError(
                f"Terms and conditions version '{terms_version}' not found or inactive."
            )
        
        return {
            'version': terms.version,
            'content_snapshot': terms.content,
            'accepted_at': timezone.now()
        }


class StayAvailabilityService:
    @staticmethod
    def create_availability(hotel, room, room_quantity, days=90):
        today = date.today()
        # rooms = RoomListing.objects.filter(hotel=hotel)

        objs = []
        for i in range(days):
            objs.append(
                StayAvailability(
                    hotel=hotel,
                    room=room,
                    available_rooms=room_quantity,
                    date=today + timedelta(days=i),
                    # is_available=True,
                )
            )

        StayAvailability.objects.bulk_create(objs, batch_size=1000,ignore_conflicts=True)

    # * This get_available_rooms method will be used to render our room list table.
    @staticmethod
    def get_available_rooms(hotel, check_in_date, check_out_date):
        required_days = (check_out_date - check_in_date).days

        qs = (
            StayAvailability.objects
            .filter(
                hotel=hotel,
                date__gte=check_in_date,
                date__lt=check_out_date,
                available_rooms__gt=0
            )
            .values("room")
            .annotate(
                total_days=Count("date", distinct=True),
                min_available=Min("available_rooms")
            )
            .filter(total_days=required_days)  # available every day
        )

        # extract room IDs
        room_ids = [row["room"] for row in qs]

        rooms = RoomListing.objects.filter(id__in=room_ids)

        # TODO: attach min_available to room instance to return to frontend

        return rooms, qs

    @staticmethod
    def validate_availability(hotel, rooms_info, check_in_date, check_out_date, lock=True):
        date_cursor = check_in_date
        room_ids = [room_info["room"].id for room_info in rooms_info]
        dates = []
        while date_cursor < check_out_date:
            dates.append(date_cursor)
            date_cursor += timedelta(days=1)
        
        queryset = StayAvailability.objects.filter(
            hotel=hotel,
            room_id__in=room_ids,
            date__in=dates
        )
        if lock:
            queryset = queryset.select_for_update()
            
        availabilities = queryset
        
        availability_map = {}
        for av in availabilities:
            key = (av.room_id, av.date)
            availability_map[key] = av
        
        for date_cursor in dates:
            for room_info in rooms_info:
                room = room_info["room"]
                quantity = room_info["quantity"]
                key = (room.id, date_cursor)
                availability = availability_map.get(key)
                
                if not availability:
                    raise ValidationError(
                        f"Availability has not been released for {room.title} on {date_cursor}. "
                        "Please choose closer dates."
                    )
                
                if availability.available_rooms < quantity:
                    raise BookingConflict(
                        f"Not enough rooms available for {room.title} on {date_cursor}. "
                        f"Available: {availability.available_rooms}, Requested: {quantity}"
                    )

    @staticmethod
    def update_availability(
        hotel,
        rooms_info,
        check_in_date,
        check_out_date,
        increment: bool = False,
    ):
        date_cursor = check_in_date
        room_ids = [room_info["room"].id for room_info in rooms_info]
        dates = []
        while date_cursor < check_out_date:
            dates.append(date_cursor)
            date_cursor += timedelta(days=1)
        
        for date_cursor in dates:
            for room_info in rooms_info:
                room_id = room_info["room"].id
                quantity = room_info["quantity"]
                obj = StayAvailability.objects.select_for_update().filter(
                    hotel=hotel, room_id=room_id, date=date_cursor
                )
                if increment:
                    obj.update(available_rooms=F(
                        "available_rooms") + quantity)
                else:
                    obj.update(available_rooms=F(
                        "available_rooms") - quantity)
    
    @staticmethod
    @transaction.atomic()
    def update_guest_house_room(instance: GuestHouseRoom, validated_data: dict, kept_image_ids: list = None):
        images = validated_data.pop("images", [])
        amenities = validated_data.pop("amenities", None)
        
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        instance.save()
        
        if amenities is not None:
             instance.amenities.set(amenities)

        ListingService._update_images(instance, images, kept_image_ids)
        return instance

    @staticmethod
    def search_stays(city, check_in_date, check_out_date, number_of_guests):
        required_days = (check_out_date - check_in_date).days

        qs = (
            StayAvailability.objects
            .filter(
                hotel__company__address__city__icontains=city,
                room__number_of_guests__gte=number_of_guests,
                date__gte=check_in_date,
                date__lt=check_out_date,
                available_rooms__gt=0
            )
            .values("hotel", "room")
            .annotate(
                total_days=Count("date", distinct=True),
                min_available=Min("available_rooms")
            )
            .filter(total_days=required_days)
        )

        hotel_ids = list(set([row["hotel"] for row in qs]))
        hotels = HotelProfile.objects.filter(id__in=hotel_ids).select_related(
            "company", "company__address"
        ).prefetch_related("room_listings", "images", "facilities")

        availability_data = list(qs)
        
        # Optimize: Fetch all relevant rooms in one query
        all_room_ids = [row["room"] for row in availability_data]
        all_rooms = RoomListing.objects.filter(id__in=all_room_ids).select_related("hotel", "address")
        rooms_by_id = {r.id: r for r in all_rooms}
        
        results = []
        for hotel in hotels:
            hotel_rooms_data = [row for row in availability_data if row["hotel"] == hotel.id]
            
            hotel_data = {
                "hotel": hotel,
                "rooms": []
            }
            
            for row in hotel_rooms_data:
                room_id = row["room"]
                room = rooms_by_id.get(room_id)
                if room:
                    hotel_data["rooms"].append({
                        "room": room,
                        "available_units": row["min_available"]
                    })
            
            if hotel_data["rooms"]:
                results.append(hotel_data)
        
        return results

    @staticmethod
    def ensure_future_availability(days_ahead=180, start_date=None):
        start = start_date or date.today()
        end = start + timedelta(days=days_ahead)
        rooms = RoomListing.objects.select_related("hotel")
        created = 0
        batch = []
        for room in rooms:
            if not room.hotel:
                continue
            existing_dates = set(
                StayAvailability.objects.filter(
                    room=room,
                    date__gte=start,
                    date__lt=end
                ).values_list("date", flat=True)
            )
            cursor = start
            while cursor < end:
                if cursor not in existing_dates:
                    batch.append(
                        StayAvailability(
                            hotel=room.hotel,
                            room=room,
                            date=cursor,
                            available_rooms=room.total_units
                        )
                    )
                    if len(batch) >= 1000:
                        StayAvailability.objects.bulk_create(batch, batch_size=1000,ignore_conflicts=True)
                        created += len(batch)
                        batch = []
                cursor += timedelta(days=1)
        if batch:
            StayAvailability.objects.bulk_create(batch, batch_size=1000,ignore_conflicts=True)
            created += len(batch)
        return created

    @staticmethod
    def get_availability_matrix(hotel_id, start_date, end_date):
        room_ids = RoomListing.objects.filter(hotel_id=hotel_id).values_list('id', flat=True)
        
        availability_qs = StayAvailability.objects.filter(
            hotel_id=hotel_id,
            room_id__in=room_ids,
            date__gte=start_date,
            date__lte=end_date
        ).values('room_id', 'date', 'available_rooms')
        
        matrix = {}
        for row in availability_qs:
            r_id = str(row['room_id'])
            d_str = row['date'].isoformat()
            if r_id not in matrix: matrix[r_id] = {}
            matrix[r_id][d_str] = row['available_rooms']
            
        return matrix


class GuestHouseAvailabilityService:
    @staticmethod
    def get_availability_matrix(guest_house_id, start_date, end_date):
        room_ids = GuestHouseRoom.objects.filter(guest_house_id=guest_house_id).values_list('id', flat=True)
        
        inventory_qs = GuestHouseInventory.objects.filter(
            guest_house_room_id__in=room_ids,
            date__gte=start_date,
            date__lte=end_date
        ).values('guest_house_room_id', 'date', 'available_rooms')
        
        matrix = {}
        for row in inventory_qs:
            r_id = str(row['guest_house_room_id'])
            d_str = row['date'].isoformat()
            if r_id not in matrix: matrix[r_id] = {}
            matrix[r_id][d_str] = row['available_rooms']
            
        return matrix


class PriceService:
    @staticmethod
    def _season_matches(season: Season, when: date) -> bool:
        if not season.active:
            return False
        if season.recurring:
            start_md = (season.start_date.month, season.start_date.day)
            end_md = (season.end_date.month, season.end_date.day)
            md = (when.month, when.day)
            if start_md <= end_md:
                return start_md <= md <= end_md
            return md >= start_md or md <= end_md
        return season.start_date <= when <= season.end_date

    @staticmethod
    def resolve_price(room: RoomListing, when: date) -> Decimal:
        # 1) RoomInventory override
        inv = RoomInventory.objects.filter(room_listing=room, date=when).first()
        if inv and inv.price is not None:
            return Decimal(inv.price)

        # 2) SeasonalRate candidates
        hotel = room.hotel
        company = getattr(hotel, 'company', None) if hotel else None

        candidates = SeasonalRate.objects.filter(active=True).select_related('season')
        # narrow to possible scopes to reduce in-memory checks
        scope_q = Q(room=room) | Q(hotel=hotel)
        if company:
            scope_q |= Q(company=company)
        scope_q |= Q(room__isnull=True, hotel__isnull=True, company__isnull=True)
        candidates = candidates.filter(scope_q)

        matched = []
        for rate in candidates:
            if not PriceService._season_matches(rate.season, when):
                continue
            # days_of_week optional filter
            if rate.days_of_week:
                try:
                    if when.weekday() not in rate.days_of_week:
                        continue
                except Exception:
                    pass
            matched.append(rate)

        if matched:
            # sort by priority desc then specificity (room>hotel>company>global)
            def score(r):
                # specificity: room > hotel > company > global
                spec = 0
                if r.room:
                    spec = 3
                elif r.hotel:
                    spec = 2
                elif r.company:
                    spec = 1
                # use created_at as deterministic tie-breaker; later entries win
                return (r.priority, spec, getattr(r, 'created_at', None))

            # sort by priority desc, then specificity desc, then created_at desc
            matched.sort(key=score, reverse=True)
            chosen = matched[0]
            if chosen.price_override is not None:
                return Decimal(chosen.price_override)
            if chosen.multiplier is not None:
                base = Decimal(room.base_price)
                return (base * Decimal(chosen.multiplier)).quantize(Decimal('0.01'))

        # 3) fallback to base price
        return Decimal(room.base_price)

    @staticmethod
    def resolve_price_detail(listing: any, when: date) -> dict:
        # Returns detailed info for a single date: final price and source info

        if isinstance(listing, RoomListing):
            inv = RoomInventory.objects.filter(room_listing=listing, date=when).first()
            if inv and inv.price is not None:
                p = Decimal(inv.price).quantize(Decimal('0.01'))
                base = Decimal(listing.base_price)
                return {
                    "price": p,
                    "price_per_unit": p,
                    "source": "inventory",
                    "rate_id": None,
                    "note": None,
                    "is_discounted": p < base,
                }

            hotel = listing.hotel
            company = getattr(hotel, 'company', None) if hotel else None

            candidates = SeasonalRate.objects.filter(active=True).select_related('season')
            scope_q = Q(room=listing) | (Q(hotel=hotel) & Q(room__isnull=True))
            if company:
                scope_q |= (Q(company=company) & Q(hotel__isnull=True) & Q(room__isnull=True))
            scope_q |= Q(room__isnull=True, hotel__isnull=True, company__isnull=True)
            candidates = candidates.filter(scope_q)

            matched = []
            for rate in candidates:
                if not PriceService._season_matches(rate.season, when):
                    continue
                if rate.days_of_week:
                    try:
                        if when.weekday() not in rate.days_of_week:
                            continue
                    except Exception:
                        pass
                matched.append(rate)

            if matched:
                def score(r):
                    spec = 0
                    if r.room:
                        spec = 3
                    elif r.hotel:
                        spec = 2
                    elif r.company:
                        spec = 1
                    return (r.priority, spec, getattr(r, 'created_at', None))

                matched.sort(key=score, reverse=True)
                chosen = matched[0]
                if chosen.price_override is not None:
                    p = Decimal(chosen.price_override).quantize(Decimal('0.01'))
                    base = Decimal(listing.base_price)
                    return {
                        "price": p,
                        "price_per_unit": p,
                        "source": "seasonal",
                        "rate_id": str(chosen.id),
                        "note": None,
                        "is_discounted": p < base,
                    }
                if chosen.multiplier is not None:
                    base = Decimal(listing.base_price)
                    p = (base * Decimal(chosen.multiplier)).quantize(Decimal('0.01'))
                    return {
                        "price": p,
                        "price_per_unit": p,
                        "source": "seasonal",
                        "rate_id": str(chosen.id),
                        "note": f"multiplier {chosen.multiplier}",
                        "is_discounted": p < base,
                    }

        base = Decimal(listing.base_price).quantize(Decimal('0.01'))
        return {
            "price": base,
            "price_per_unit": base,
            "source": "base",
            "rate_id": None,
            "note": None,
            "is_discounted": False,
        }

    @staticmethod
    def resolve_price_details_batch(listing: any, start_date: date, end_date: date) -> list:
        
        if isinstance(listing, GuestHouseRoom):
            return PriceService._resolve_guesthouse_price_batch(listing, start_date, end_date)

        if not isinstance(listing, RoomListing):
            results = []
            cursor = start_date
            while cursor < end_date:
                detail = PriceService.resolve_price_detail(listing, cursor)
                detail['date'] = cursor
                results.append(detail)
                cursor += timedelta(days=1)
            return results

        room = listing
        dates = []
        cursor = start_date
        while cursor < end_date:
            dates.append(cursor)
            cursor += timedelta(days=1)
        
        inv_qs = RoomInventory.objects.filter(
            room_listing=room,
            date__in=dates
        )
        inventories = {inv.date: inv for inv in inv_qs}
        
        hotel = room.hotel
        company = getattr(hotel, 'company', None) if hotel else None
        
        scope_q = Q(room=room) | Q(hotel=hotel)
        if company:
            scope_q |= Q(company=company)
        scope_q |= Q(room__isnull=True, hotel__isnull=True, company__isnull=True)
        
        seasonal_rates = SeasonalRate.objects.filter(
            active=True
        ).filter(scope_q).select_related('season')
        
        seasonal_rates_list = list(seasonal_rates)
        
        results = []
        base_price = Decimal(room.base_price)
        
        for date_val in dates:
            inv = inventories.get(date_val)
            if inv and inv.price is not None:
                p = Decimal(inv.price).quantize(Decimal('0.01'))
                results.append({
                    "date": date_val,
                    "price": p,
                    "price_per_unit": p,
                    "source": "inventory",
                    "rate_id": None,
                    "note": None,
                    "is_discounted": p < base_price,
                })
                continue
            
            matched = []
            for rate in seasonal_rates_list:
                if not PriceService._season_matches(rate.season, date_val):
                    continue
                if rate.days_of_week:
                    try:
                        if date_val.weekday() not in rate.days_of_week:
                            continue
                    except Exception:
                        pass
                matched.append(rate)
            
            if matched:
                def score(r):
                    spec = 3 if r.room else (2 if r.hotel else (1 if r.company else 0))
                    return (r.priority, spec, getattr(r, 'created_at', None))
                
                matched.sort(key=score, reverse=True)
                chosen = matched[0]
                
                if chosen.price_override is not None:
                    p = Decimal(chosen.price_override).quantize(Decimal('0.01'))
                    results.append({
                        "date": date_val,
                        "price": p,
                        "price_per_unit": p,
                        "source": "seasonal",
                        "rate_id": str(chosen.id),
                        "note": None,
                        "is_discounted": p < base_price,
                    })
                    continue
                
                if chosen.multiplier is not None:
                    p = (base_price * Decimal(chosen.multiplier)).quantize(Decimal('0.01'))
                    results.append({
                        "date": date_val,
                        "price": p,
                        "price_per_unit": p,
                        "source": "seasonal",
                        "rate_id": str(chosen.id),
                        "note": f"multiplier {chosen.multiplier}",
                        "is_discounted": p < base_price,
                    })
                    continue
            
            # Fallback to base price
            p = base_price.quantize(Decimal('0.01'))
            results.append({
                "date": date_val,
                "price": p,
                "price_per_unit": p,
                "source": "base",
                "rate_id": None,
                "note": None,
                "is_discounted": False,
            })
        return results

    @staticmethod
    def _resolve_guesthouse_price_batch(room: GuestHouseRoom, start_date: date, end_date: date) -> list:
        dates = []
        cursor = start_date
        while cursor < end_date:
            dates.append(cursor)
            cursor += timedelta(days=1)
        
        inv_qs = GuestHouseInventory.objects.filter(
            guest_house_room=room,
            date__in=dates
        )
        inventories = {inv.date: inv for inv in inv_qs}
        
        results = []
        base_price = Decimal(room.base_price)
        
        for date_val in dates:
            inv = inventories.get(date_val)
            if inv and inv.price is not None:
                p = Decimal(inv.price).quantize(Decimal('0.01'))
                results.append({
                    "date": date_val,
                    "price": p,
                    "price_per_unit": f"{p:.2f}",
                    "source": "inventory",
                    "rate_id": None,
                    "note": None,
                    "is_discounted": p < base_price,
                })
            else:
                p = base_price.quantize(Decimal('0.01'))
                results.append({
                    "date": date_val,
                    "price": p,
                    "price_per_unit": f"{p:.2f}",
                    "source": "base",
                    "rate_id": None,
                    "note": None,
                    "is_discounted": False,
                })
        return results


class PriceCalculationService:
    @staticmethod
    def calculate_totals(item_subtotals, fee_rate=None):
        # Base math for calculating totals. Returns raw Decimals.
        items_subtotal = sum(Decimal(str(s)) for s in item_subtotals)
        
        if fee_rate is None:
            fee_rate = getattr(settings, 'PLATFORM_FEE_RATE', DEFAULT_PLATFORM_FEE_RATE)
        if not isinstance(fee_rate, Decimal):
            fee_rate = Decimal(str(fee_rate))
            
        platform_fee = items_subtotal * fee_rate
        grand_total = items_subtotal + platform_fee
        
        return {
            "items_subtotal": items_subtotal,
            "platform_fee": platform_fee,
            "platform_fee_percentage": fee_rate * 100,
            "grand_total": grand_total
        }

    @staticmethod
    def calculate_totals_with_addons(base_subtotals, addon_subtotals=None, fee_rate=None):
        base_subtotal = sum(Decimal(str(s)) for s in base_subtotals)
        addon_subtotal = sum(Decimal(str(s)) for s in (addon_subtotals or []))

        if fee_rate is None:
            fee_rate = getattr(settings, 'PLATFORM_FEE_RATE', DEFAULT_PLATFORM_FEE_RATE)
        if not isinstance(fee_rate, Decimal):
            fee_rate = Decimal(str(fee_rate))

        platform_fee = base_subtotal * fee_rate
        grand_total = base_subtotal + addon_subtotal + platform_fee

        return {
            "items_subtotal": base_subtotal,
            "addons_subtotal": addon_subtotal,
            "platform_fee": platform_fee,
            "platform_fee_percentage": fee_rate * 100,
            "grand_total": grand_total,
        }

    @staticmethod
    def calculate_preview_totals(item_subtotals, currency="ETB", display_currency=None, items=None, fee_rate=None):
        
        base_res = PriceCalculationService.calculate_totals(item_subtotals, fee_rate=fee_rate)
        
        response = {
            "totals": {
                "items_subtotal": f"{base_res['items_subtotal']:.2f}",
                "platform_fee": f"{base_res['platform_fee']:.2f}",
                "platform_fee_percentage": f"{base_res['platform_fee_percentage']:.2f}",
                "grand_total": f"{base_res['grand_total']:.2f}",
                "currency": currency
            },
            "conversion": None
        }

        if display_currency and display_currency.upper() != currency.upper():
            from apps.core.utils import convert_currency
            from django.utils.timezone import now
            try:
                conv_subtotal, rate = convert_currency(base_res["items_subtotal"], currency, display_currency, return_rate=True)
                conv_fee = convert_currency(base_res["platform_fee"], currency, display_currency)
                conv_grand = convert_currency(base_res["grand_total"], currency, display_currency)
                
                conversion_data = {
                    "from": currency,
                    "to": display_currency.upper(),
                    "rate": f"{rate:g}",
                    "calculated_at": now().isoformat(),
                    "items_subtotal": f"{conv_subtotal:.2f}",
                    "platform_fee": f"{conv_fee:.2f}",
                    "platform_fee_percentage": f"{base_res['platform_fee_percentage']:.2f}",
                    "grand_total": f"{conv_grand:.2f}",
                }
                
                if items:
                    for item in items:
                        ppu = Decimal(str(item.get("price_per_unit", 0)))
                        sub = Decimal(str(item.get("subtotal", 0)))
                        
                        conv_ppu = convert_currency(ppu, currency, display_currency)
                        conv_sub = convert_currency(sub, currency, display_currency)
                        
                        item["conversion"] = {
                            "price_per_unit": f"{conv_ppu:.2f}",
                            "subtotal": f"{conv_sub:.2f}",
                            "currency": display_currency.upper()
                        }
                        
                        for entry in item.get("breakdown", []):
                            entry_ppu = Decimal(str(entry.get("price_per_unit", 0)))
                            conv_entry_ppu = convert_currency(entry_ppu, currency, display_currency)
                            entry["conversion"] = {
                                "price_per_unit": f"{conv_entry_ppu:.2f}",
                                "currency": display_currency.upper()
                            }
                
                response["conversion"] = conversion_data
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Price preview currency conversion failed: {e}")
                
        return response


class BookingService:
    @transaction.atomic()
    @staticmethod

    def create_booking(validated_data, user=None, is_walk_in=False):
        guest_email = validated_data.get("guest_email")
        guest_phone = validated_data.get("guest_phone")
        if not guest_phone or not str(guest_phone).strip():
            raise ValidationError({"guest_phone": "Phone number is required for every booking."})

        items_data = validated_data.pop("items")
        
        # Extract T&C data
        terms_accepted = validated_data.pop("terms_accepted", False)
        terms_version = validated_data.pop("terms_version", "")
        
        payment_currency = validated_data.pop("payment_currency", "ETB")
        
        if user:
            validated_data["user"] = user
        
        check_in_date = validated_data.get("check_in_date")
        check_out_date = validated_data.get("check_out_date")
        
        rooms_info = []
        for item in items_data:
            room = item["room"]
            units = item["units_booked"]
            rooms_info.append({"room": room, "quantity": units})
        
        if rooms_info:
            hotel = rooms_info[0]["room"].hotel
            StayAvailabilityService.validate_availability(
                hotel, rooms_info, check_in_date, check_out_date
            )
            
            is_privileged = False
            
            if user and user.is_superuser:
                 is_privileged = True
            elif user and user.is_authenticated and is_walk_in:
                 from apps.listing.utils import is_user_staff_of_listing
                 if is_user_staff_of_listing(user, hotel):
                     is_privileged = True
            
            if is_privileged:
                 validated_data['status'] = Booking.BookingStatus.WALK_IN

            try:
                tc_data = TermsService.validate_and_snapshot_terms(
                    content_object=hotel,
                    terms_version=terms_version,
                    terms_accepted=terms_accepted,
                    allow_missing=is_privileged
                )
                
                validated_data['terms_accepted'] = True
                validated_data['terms_version'] = tc_data['version']
                validated_data['terms_accepted_at'] = tc_data['accepted_at']
                validated_data['terms_content_snapshot'] = tc_data['content_snapshot']
            except Exception as e:
                logger.error(f"T&C validation failed: {e}")
                raise
        
        booking = Booking.objects.create(currency=payment_currency, **validated_data)


        nights = (check_out_date - check_in_date).days

        for item in items_data:
            room = item["room"]
            units = item["units_booked"]

            price_details = PriceService.resolve_price_details_batch(
                 room, check_in_date, check_out_date
            )
            total_room_native = sum(d['price_per_unit'] for d in price_details)
            avg_rate_native = total_room_native / nights if nights > 0 else 0
            
            converted_rate = avg_rate_native
            if room.currency != payment_currency:
                try:
                    from apps.core.utils import convert_currency
                    converted_rate = convert_currency(avg_rate_native, room.currency, payment_currency)
                except Exception:
                     converted_rate = avg_rate_native

            booking_item = BookingItem.objects.create(
                booking=booking,
                room=room,
                units_booked=units,
                price_per_unit=converted_rate,
            )

            # Build item snapshot (capture display-ready fields at booking time)
            try:
                # collect up to 3 image urls from listing images (may be relative)
                images_qs = list(room.images.all()[:3])
                image_urls = [getattr(img.image, 'url', None) for img in images_qs if getattr(img, 'image', None)]
            except Exception:
                image_urls = []

            # compute min available units across the stay period at booking moment
            try:
                from django.db.models import Min
                min_av = StayAvailability.objects.filter(
                    hotel=room.hotel,
                    room=room,
                    date__gte=booking.check_in_date,
                    date__lt=booking.check_out_date,
                ).aggregate(min_available=Min('available_rooms'))
                available_units_at_booking = min_av.get('min_available') or 0
            except Exception:
                available_units_at_booking = None

            item_snapshot = {
                "room_id": str(room.id),
                "title": room.title,
                "images": image_urls,
                "nightly_rate": f"{booking_item.price_per_unit:.2f}",
                "stay_total": f"{booking_item.subtotal(nights=nights):.2f}",
                "subtotal": f"{booking_item.subtotal(nights=nights):.2f}",  # Legacy alias
                "currency": str(booking.currency),
                "units_booked": booking_item.units_booked,
                "nights": nights,
                "available_units_at_booking_time": available_units_at_booking,
                "original_price_currency": room.currency,
                "original_price_details": [
                    {
                        k: (v.isoformat() if hasattr(v, 'isoformat') else str(v) if isinstance(v, Decimal) else v) 
                        for k, v in d.items()
                    }
                    for d in price_details
                 ]
            }

            # store snapshot on booking item
            booking_item.snapshot = item_snapshot
            booking_item.save(update_fields=['snapshot'])

            addons_data = item.get("addons", [])
            if addons_data:
                for addon_input in addons_data:
                    offering = addon_input.get('_offering')
                    if not offering:
                        continue 
                    
                    if offering.hotel_id != room.hotel_id:
                        from rest_framework.exceptions import ValidationError
                        raise ValidationError({
                            "addons": f"{offering.name} is not available for {room.hotel.name}"
                        })
                    
                    addon_price = offering.price_per_unit
                    if offering.currency != payment_currency:
                        try:
                            from apps.core.utils import convert_currency
                            addon_price = convert_currency(offering.price_per_unit, offering.currency, payment_currency)
                        except Exception:
                            addon_price = offering.price_per_unit

                    from apps.listing.models import BookingAddon
                    BookingAddon.objects.create(
                        booking_item=booking_item,
                        offering=offering,
                        name=offering.name,
                        description=offering.description,
                        category=offering.category,
                        quantity=addon_input.get('quantity', 1),
                        price_per_unit=addon_price,
                        currency=payment_currency # now matches booking
                    )
            StayAvailabilityService.update_availability(
                hotel=room.hotel,
                rooms_info=[{"room": room, "quantity": units}],
                check_in_date=booking.check_in_date,
                check_out_date=booking.check_out_date,
                increment=False,
            )

        # Calculate total using the shared logic (Base + 5% Fee)
        fee_rate = get_effective_platform_fee_rate(booking=booking, user=user, exclude_booking=booking)
        booking.total_price = BookingService.get_booking_total(booking, fee_rate=fee_rate)
        
        booking.save()

        # build booking-level snapshot and persist
        try:
            hotel_info = None
            if rooms_info:
                hotel_obj = rooms_info[0]['room'].hotel
                try:
                    hotel_image_qs = list(hotel_obj.images.all()[:1])
                    hotel_image = getattr(hotel_image_qs[0].image, 'url', None) if hotel_image_qs else None
                except Exception:
                    hotel_image = None

                hotel_info = {
                    "id": str(hotel_obj.id),
                    "name": getattr(hotel_obj.company, 'name', None) if getattr(hotel_obj, 'company', None) else None,
                    "image": hotel_image,
                }

            nights = (booking.check_out_date - booking.check_in_date).days
            items_snapshots = []
            raw_rooms_subtotal = Decimal('0.00')
            raw_addons_subtotal = Decimal('0.00')

            for it in booking.items.all():
                room_total = it.subtotal(nights=nights)
                raw_rooms_subtotal += room_total
                
                addon_list = []
                for addon in it.addons.all():
                    addon_total = addon.subtotal()
                    raw_addons_subtotal += addon_total
                    addon_list.append({
                        "name": addon.name,
                        "quantity": addon.quantity,
                        "price_per_unit": f"{addon.price_per_unit:.2f}",
                        "subtotal": f"{addon_total:.2f}",
                        "currency": addon.currency,
                    })

                items_snapshots.append({
                    "room": {
                        "id": str(it.room.id),
                        "title": it.room.title,
                    },
                    "units_booked": it.units_booked,
                    "nights": nights,
                    "nightly_rate": f"{it.price_per_unit:.2f}",
                    "stay_total": f"{room_total:.2f}",
                    "addons": addon_list,
                    "images": it.snapshot.get('images') if isinstance(it.snapshot, dict) else [],
                })

            platform_fee = raw_rooms_subtotal * fee_rate
            grand_total = raw_rooms_subtotal + raw_addons_subtotal + platform_fee

            booking_snapshot = {
                "booking_id": str(booking.id),
                "check_in_date": booking.check_in_date.isoformat(),
                "check_out_date": booking.check_out_date.isoformat(),
                "currency": str(booking.currency),
                "hotel": hotel_info,
                "billing": {
                    "subtotal_rooms": f"{raw_rooms_subtotal:.2f}",
                    "subtotal_addons": f"{raw_addons_subtotal:.2f}",
                    "platform_fee": f"{platform_fee:.2f}",
                    "grand_total": f"{grand_total:.2f}",
                },
                "items": items_snapshots,
                "snapshot_version": 3,
            }

            booking.snapshot = booking_snapshot
            booking.save(update_fields=['snapshot'])
        except Exception:
            # do not fail booking creation if snapshot generation fails
            pass
        return booking

    @staticmethod
    def cancel_booking(booking: Booking):
        """Called when the user cancel their booking.

        Args:
            booking (Booking): Booking instance.

        Returns:
            Booking: Cancelled Booking instance.
        """
        if booking.status in [
            Booking.BookingStatus.CANCELLED,
            Booking.BookingStatus.CONFIRMED
        ]:
            raise BookingConflict(
                "Booking is already finalized and cannot be changed."
            )
        for item in booking.items.all():
            StayAvailabilityService.update_availability(
                hotel=item.room.hotel,
                rooms_info=[
                    {"room": item.room, "quantity": item.units_booked}],
                check_in_date=booking.check_in_date,
                check_out_date=booking.check_out_date,
                increment=True,
            )
        booking.status = booking.BookingStatus.CANCELLED
        booking.save()

        NotificationService.create_notification(
            user=booking.user,
            notification_type=Notification.NotificationType.BOOKING_CANCELLED,
            title="Booking Cancelled",
            message=f"Your booking {booking.booking_reference} at {booking.items.first().room.hotel.company.name} has been cancelled.",
            metadata={
                'booking_reference': booking.booking_reference,
                'booking_id': str(booking.id),
                'hotel_name': booking.items.first().room.hotel.company.name
            },
            priority=Notification.Priority.HIGH
        )

        return booking
    #partial cancel
    @staticmethod
    @transaction.atomic
    def partial_cancel_booking(booking_item: BookingItem, units_to_cancel: int):
        booking = booking_item.booking
        if booking.status in [
            Booking.BookingStatus.CANCELLED,
            Booking.BookingStatus.CONFIRMED,
        ]:
            raise BookingConflict("Booking is already finalized and cannot be changed.")
        if units_to_cancel <= 0:
            raise BookingConflict("Units to cancel must be greater than zero.")

        if units_to_cancel > booking_item.units_booked:
            raise BookingConflict(
                f"You cannot cancel more units ({units_to_cancel}) "
                f"than booked ({booking_item.units_booked})."
            )

        # Update availability (increment=True since we release rooms)
        StayAvailabilityService.update_availability(
            hotel=booking_item.room.hotel,
            rooms_info=[
                {"room": booking_item.room, "quantity": units_to_cancel}
            ],
            check_in_date=booking.check_in_date,
            check_out_date=booking.check_out_date,
            increment=True,
        )
        booking_item.units_booked -= units_to_cancel

        # If zero, delete the booking item
        if booking_item.units_booked == 0:
            booking_item.delete()
        else:
            booking_item.save()

        # Recalculate booking total
        use_seasonal = getattr(settings, 'FEATURE_SEASONAL_PRICING', False)
        if use_seasonal:
            total_price = Decimal('0.00')
            for pip in BookingItemPrice.objects.filter(booking_item__booking=booking):
                total_price += (Decimal(pip.price_per_unit) * Decimal(pip.units))
            booking.total_price = total_price
        else:
            nights = (booking.check_out_date - booking.check_in_date).days
            total_price = Decimal('0.00')
            for item in booking.items.all():
                total_price += (Decimal(item.price_per_unit) * Decimal(item.units_booked) * Decimal(nights))
            booking.total_price = total_price
        booking.save()

        return booking

    @staticmethod
    def confirm_booking(booking: Booking):
        """Called when the user complete payment."""
        if booking.status == Booking.BookingStatus.CONFIRMED:
            logger.info(f"Booking {booking.id} is already CONFIRMED, skipping.")
            return booking

        if booking.status == Booking.BookingStatus.CANCELLED:
             # If it was cancelled by the timer just as they paid, we might need a recovery path
             # but for now, we follow the "finalized" rule unless explicitly asked to revive.
            raise BookingConflict(
                f"Booking {booking.id} was already CANCELLED and cannot be confirmed."
            )

        # FINAL INTEGRITY CHECK: Ensure legal record exists before confirmation
        if not booking.terms_accepted or not booking.terms_version or not booking.terms_content_snapshot:
            logger.error(f"CRITICAL: Booking {booking.id} is being confirmed but lacks T&C snapshot!")
            # We still allow legacy bookings to be confirmed if they were created before this system
            if not booking.is_legacy:
                 raise ValidationError("Legal integrity check failed: Missing T&C snapshot for non-legacy booking.")

        booking.status = booking.BookingStatus.CONFIRMED
        booking.save()
        logger.info(f"Booking {booking.id} status updated to CONFIRMED.")
        
        _send_booking_confirmation_sms_first(booking, label="hotel booking")
        
        if booking.user_id:
            NotificationService.create_notification(
                user=booking.user,
                notification_type=Notification.NotificationType.BOOKING_CONFIRMED,
                title="Booking Confirmed",
                message=f"Your booking {booking.booking_reference} at {booking.items.first().room.hotel.company.name} is confirmed.",
                metadata={
                    'booking_reference': booking.booking_reference,
                    'booking_id': str(booking.id),
                    'hotel_name': booking.items.first().room.hotel.company.name
                },
                priority=Notification.Priority.HIGH
            )

        # Notify Vendor (Company Owner)
        try:
            vendor_user = booking.items.first().room.hotel.company.user
            if vendor_user:
                NotificationService.create_notification(
                    user=vendor_user,
                    notification_type=Notification.NotificationType.NEW_BOOKING_RECEIVED,
                    title="New Booking Received",
                    message=f"New booking ({booking.booking_reference}) received for {booking.items.first().room.hotel.company.name}.",
                    metadata={
                        'booking_reference': booking.booking_reference,
                        'booking_id': str(booking.id),
                    },
                    priority=Notification.Priority.HIGH
                )
        except Exception:
            logger.warning(f"Could not send vendor notification for Booking {booking.id}")
        
        return booking
    
    @staticmethod
    def get_booking_total(booking, fee_rate=None):
        if fee_rate is None:
            fee_rate = get_effective_platform_fee_rate(booking=booking)

        use_seasonal = getattr(settings, 'FEATURE_SEASONAL_PRICING', False)
        item_subtotals = []
        addon_subtotals = []

        if use_seasonal:
            for pip in BookingItemPrice.objects.filter(booking_item__booking=booking):
                item_subtotals.append(Decimal(pip.price_per_unit) * Decimal(pip.units))
        else:
            nights = (booking.check_out_date - booking.check_in_date).days
            for item in booking.items.all():
                item_subtotals.append(Decimal(item.price_per_unit) * Decimal(item.units_booked) * Decimal(nights))
        
        from apps.listing.models import BookingAddon
        for addon in BookingAddon.objects.filter(booking_item__booking=booking):
            addon_subtotal = Decimal(addon.price_per_unit) * Decimal(addon.quantity)
            addon_subtotals.append(addon_subtotal)
        
        calculation = PriceCalculationService.calculate_totals_with_addons(
            item_subtotals,
            addon_subtotals,
            fee_rate=fee_rate,
        )
        return calculation["grand_total"]
class EventSpaceBookingService:
    @transaction.atomic()
    @staticmethod
    def create_booking(validated_data, user=None, is_walk_in=False):
        """
        Creates a new Event Space Booking, validates availability, and decrements inventory, 
        using only the base price for calculation.
        """
        guest_phone = validated_data.get("guest_phone")
        if not guest_phone or not str(guest_phone).strip():
            raise ValidationError({"guest_phone": "Phone number is required for every booking."})

        items_data = validated_data.pop("items")
        
        terms_accepted = validated_data.pop("terms_accepted", False)
        terms_version = validated_data.pop("terms_version", "")
        
        if user:
            validated_data["user"] = user
        
        check_in = validated_data["check_in_date"]
        check_out = validated_data["check_out_date"]
        payment_currency = validated_data.pop("payment_currency", "ETB")
        validated_data.pop("is_walk_in", None)

        if not items_data:
            raise ValidationError("Items are required")
        
        first_space = items_data[0]["event_space"]
        hotel = first_space.hotel
        
        is_privileged = False
        
        if user and user.is_superuser:
                is_privileged = True
        elif user and user.is_authenticated and is_walk_in:
                from apps.listing.utils import is_user_staff_of_listing
                if is_user_staff_of_listing(user, hotel):
                    is_privileged = True

        if is_privileged:
             validated_data['status'] = EventSpaceBooking.BookingStatus.WALK_IN

        if is_privileged and not terms_accepted:
            terms_accepted = True

        try:
            snapshot_data = TermsService.validate_and_snapshot_terms(
                 content_object=hotel,
                 terms_version=terms_version,
                 terms_accepted=terms_accepted,
                 allow_missing=is_privileged
            )
        except Exception as e:
            logger.error(f"T&C validation failed: {e}")
            raise

        booking = EventSpaceBooking.objects.create(
            currency=payment_currency,
            **validated_data,
        )
        booking.terms_accepted = True
        booking.terms_version = snapshot_data['version']
        booking.terms_content_snapshot = snapshot_data['content_snapshot']
        booking.terms_accepted_at = snapshot_data['accepted_at']

        booking.save()

        space_infos = []
        for item_data in items_data:
            space_infos.append({
                "space_listing": item_data["event_space"],
                "quantity": item_data["units_booked"] 
            })

        EventSpaceAvailabilityService.validate_availability(
            space_infos, check_in, check_out
        )

        for item_data in items_data:
            space = item_data["event_space"]
            
            price_per_unit = space.base_price
            if space.currency != payment_currency:
                try:
                    price_per_unit = convert_currency(space.base_price, space.currency, payment_currency)
                except Exception:
                    price_per_unit = space.base_price

            EventSpaceBookingItem.objects.create(
                booking=booking,
                event_space=space,
                units_booked=item_data["units_booked"],
                price_per_unit=price_per_unit,
            )

        EventSpaceAvailabilityService.update_availability(
            space_infos, 
            check_in, 
            check_out,
            increment=False, 
        )

        fee_rate = get_effective_platform_fee_rate(booking=booking, user=user, exclude_booking=booking)
        booking.total_price = EventSpaceBookingService.get_booking_total(booking, fee_rate=fee_rate)
        
        try:
            duration = (booking.check_out_date - booking.check_in_date).days or 1
            items_snapshots = []
            raw_base_subtotal = Decimal('0.00')

            for it in booking.items.all():
                space_total = it.units_booked * it.price_per_unit
                raw_base_subtotal += space_total
                items_snapshots.append({
                    "event_space": {
                        "id": str(it.event_space.id),
                        "title": it.event_space.title,
                    },
                    "units_booked": it.units_booked,
                    "nights": duration,
                    "nightly_rate": f"{(it.price_per_unit / duration):.2f}",
                    "stay_total": f"{space_total:.2f}",
                    "currency": booking.currency,
                })

            platform_fee = raw_base_subtotal * fee_rate
            grand_total = raw_base_subtotal + platform_fee

            booking.snapshot = {
                "booking_id": str(booking.id),
                "check_in_date": booking.check_in_date.isoformat(),
                "check_out_date": booking.check_out_date.isoformat(),
                "currency": booking.currency,
                "billing": {
                    "subtotal_items": f"{raw_base_subtotal:.2f}",
                    "platform_fee": f"{platform_fee:.2f}",
                    "grand_total": f"{grand_total:.2f}",
                },
                "audit_items": items_snapshots,
                "snapshot_version": 3,
            }
        except Exception as e:
            logger.error(f"Snapshot creation failed for EventSpace booking: {e}")

        booking.save(update_fields=['total_price', 'snapshot'])
        
        return booking

    @staticmethod
    def cancel_booking(booking: EventSpaceBooking):
        # Logic remains the same, as it only deals with status and availability update
        if booking.status in [
            booking.BookingStatus.CANCELLED,
            booking.BookingStatus.CONFIRMED 
        ]:
            raise BookingConflict(
                "Booking is already finalized and cannot be changed."
            )
        
        spaces_info = []
        for item in booking.items.all():
            spaces_info.append({
                "space_listing": item.event_space, 
                "quantity": item.units_booked
            })

        # Increment Availability
        EventSpaceAvailabilityService.update_availability(
            spaces_info=spaces_info,
            check_in_date=booking.check_in_date,
            check_out_date=booking.check_out_date,
            increment=True, 
        )
        
        booking.status = booking.BookingStatus.CANCELLED
        booking.save()

        NotificationService.create_notification(
            user=booking.user,
            notification_type=Notification.NotificationType.BOOKING_CANCELLED,
            title="Event Space Booking Cancelled",
            message=f"Your booking {booking.booking_reference} for {booking.items.first().event_space.title} has been cancelled.",
            metadata={
                'booking_reference': booking.booking_reference,
                'booking_id': str(booking.id),
                'space_title': booking.items.first().event_space.title
            },
            priority=Notification.Priority.HIGH
        )

        return booking

    @staticmethod
    @transaction.atomic
    def partial_cancel_booking(booking_item: EventSpaceBookingItem, units_to_cancel: int):
        """Partially cancels units from a specific EventSpaceBookingItem."""
        booking = booking_item.booking
        # Check conflict status
        if booking.status in [
            booking.BookingStatus.CANCELLED,
            booking.BookingStatus.CONFIRMED,
        ]:
            raise BookingConflict("Booking is already finalized and cannot be changed.")
            
        if units_to_cancel <= 0:
            raise BookingConflict("Units to cancel must be greater than zero.")

        if units_to_cancel > booking_item.units_booked:
            raise BookingConflict(
                f"You cannot cancel more units ({units_to_cancel}) "
                f"than booked ({booking_item.units_booked})."
            )

        spaces_info = [
            {"space_listing": booking_item.event_space, "quantity": units_to_cancel}
        ]
        
        # Update availability (increment=True)
        EventSpaceAvailabilityService.update_availability(
            spaces_info=spaces_info,
            check_in_date=booking.check_in_date,
            check_out_date=booking.check_out_date,
            increment=True,
        )
        
        # Update item's booked quantity
        booking_item.units_booked -= units_to_cancel

        # If zero, delete the booking item
        if booking_item.units_booked == 0:
            booking_item.delete()
        else:
            booking_item.save()

        # Recalculate booking total (Simplified: sum current item subtotals)
        booking.total_price = sum(item.subtotal() for item in booking.items.all())
        booking.save()

        return booking

    @staticmethod
    def confirm_booking(booking: EventSpaceBooking):
        # Logic remains the same
        if booking.status in [
            booking.BookingStatus.CANCELLED,
            booking.BookingStatus.CONFIRMED
        ]:
            raise BookingConflict(
                "Booking is already finalized and cannot be changed."
            )

        if not booking.terms_accepted or not booking.terms_version or not booking.terms_content_snapshot:
            logger.error(f"CRITICAL: EventSpaceBooking {booking.id} confirmed without T&C snapshot!")
            if not booking.is_legacy:
                raise ValidationError("Legal integrity check failed: Missing T&C snapshot.")

        booking.status = booking.BookingStatus.CONFIRMED
        booking.save()

        _send_booking_confirmation_sms_first(booking, label="event space booking")

        if booking.user_id:
            NotificationService.create_notification(
                user=booking.user,
                notification_type=Notification.NotificationType.BOOKING_CONFIRMED,
                title="Event Space Booking Confirmed",
                message=f"Your booking {booking.booking_reference} for {booking.items.first().event_space.title} is confirmed.",
                metadata={
                    'booking_reference': booking.booking_reference,
                    'booking_id': str(booking.id),
                    'space_title': booking.items.first().event_space.title
                },
                priority=Notification.Priority.HIGH
            )

        # Notify Vendor
        try:
            vendor_user = booking.items.first().event_space.hotel.company.user
            if vendor_user:
                NotificationService.create_notification(
                    user=vendor_user,
                    notification_type=Notification.NotificationType.NEW_BOOKING_RECEIVED,
                    title="New Event Booking Received",
                    message=f"New booking ({booking.booking_reference}) received for {booking.items.first().event_space.title}.",
                    metadata={
                        'booking_reference': booking.booking_reference,
                        'booking_id': str(booking.id),
                    },
                    priority=Notification.Priority.HIGH
                )
        except Exception:
            logger.warning(f"Could not send vendor notification for EventSpaceBooking {booking.id}")

        return booking
    
    @staticmethod
    def get_booking_total(booking: EventSpaceBooking, fee_rate=None):
        if fee_rate is None:
            fee_rate = get_effective_platform_fee_rate(booking=booking)

        # this calculates total price for the booking including platform fee from settings.
        item_subtotals = [item.subtotal() for item in booking.items.all()]
        calculation = PriceCalculationService.calculate_totals(item_subtotals, fee_rate=fee_rate)
        return calculation["grand_total"]

class PaymentService:
    """
    Handles payment initiation, verification, and transaction recording
    """

    @staticmethod
    def initiate_payment(booking: Booking, amount: float, provider: str):
        """
        Trigger the payment gateway
        Returns payment session info (URL / token)
        """
        # pseudo-code; replace with actual SDK/API
        payment_session_id = f"{booking.id}-{int(datetime.now().timestamp())}"
        return {
            "provider": provider,
            "session_id": payment_session_id,
            "amount": amount,
            "currency": "USD",
            "checkout_url": f"https://fakepayment.com/pay/{payment_session_id}"
        }

    @staticmethod
    def handle_webhook(provider: str, payload: dict):
        """
        Called by payment provider asynchronously
        payload must include provider_payment_id, booking_id, status, amount, etc.
        """
        booking_id = payload.get("booking_id")
        payment_status = payload.get("status")
        provider_payment_id = payload.get("provider_payment_id")
        amount = payload.get("amount")
        currency = payload.get("currency")

        booking = Booking.objects.get(id=booking_id)

        Transaction.objects.create(
            booking=booking,
            provider=provider,
            provider_payment_id=provider_payment_id,
            amount=amount,
            currency=currency,
            status=payment_status
        )

        if payment_status == "success":
            BookingService.confirm_booking(booking)
        else:
            # TODO: Find a way to handle retry logic
            BookingService.cancel_booking(booking)
class CarAvailabilityService:

    @staticmethod
    def create_availability(car_listing, days=90):
        today = date.today()
        objs = []

        for i in range(days):
            objs.append(
                CarAvailability(
                    car_listing=car_listing,
                    date=today + timedelta(days=i),
                    available_units=car_listing.quantity,
                )
            )
        
        CarAvailability.objects.bulk_create(
            objs, 
            batch_size=1000,
            ignore_conflicts=True
        )
    @staticmethod
    def get_available_cars(check_start, check_end):
        required_days = (check_end - check_start).days

        qs = (
            CarAvailability.objects
            .filter(
                date__gte=check_start,
                date__lt=check_end,
                available_units__gt=0
            )
            .values("car_listing")
            .annotate(
                total_days=Count("date", distinct=True),
                min_available=Min("available_units")
            )
            .filter(total_days=required_days)
        )

        car_ids = [row["car_listing"] for row in qs]
        cars = CarListing.objects.filter(id__in=car_ids)

        return cars, qs
    @staticmethod
    @transaction.atomic
    def validate_availability(car_listing, quantity, start_date, end_date):
        dates = []
        d = start_date
        while d < end_date:
            dates.append(d)
            d += timedelta(days=1)

        # get rows for those dates for this car
        qs = CarAvailability.objects.select_for_update().filter(
            car_listing=car_listing,
            date__in=dates
        )

        availability_map = {av.date: av for av in qs}

        for dt in dates:
            av = availability_map.get(dt)

            if not av:
                raise BookingConflict(
                    f"No availability entry for {car_listing} on {dt}"
                )

            if av.available_units < quantity:
                raise BookingConflict(
                    f"{car_listing} not enough units on {dt}, "
                    f"Available: {av.available_units}, Requested: {quantity}"
                )

    @staticmethod
    def check_daily_availability(car_listing, start_date, end_date, quantity):
        try:
            CarAvailabilityService.validate_availability(
                car_listing=car_listing,
                quantity=quantity,
                start_date=start_date,
                end_date=end_date,
            )
        except BookingConflict as exc:
            return {"available": False, "reason": str(exc)}

        return {"available": True, "reason": ""}

    @staticmethod
    def reserve_daily_units(car_listing, start_date, end_date, quantity):
        CarAvailabilityService.update_availability(
            car_listing=car_listing,
            quantity=quantity,
            start_date=start_date,
            end_date=end_date,
            increment=False,
        )

    @staticmethod
    def release_daily_units(car_listing, start_date, end_date, quantity):
        CarAvailabilityService.update_availability(
            car_listing=car_listing,
            quantity=quantity,
            start_date=start_date,
            end_date=end_date,
            increment=True,
        )

    @staticmethod
    def update_availability(car_listing, quantity, start_date, end_date, increment=False):

        dates = []
        d = start_date
        while d < end_date:
            dates.append(d)
            d += timedelta(days=1)

        for dt in dates:
            qs = CarAvailability.objects.select_for_update().filter(
                car_listing=car_listing,
                date=dt
            )
            if increment:
                qs.update(available_units=F("available_units") + quantity)
            else:
                qs.update(available_units=F("available_units") - quantity)
    @staticmethod
    def search_available_cars(
        start_date,
        end_date,
        brand=None,
        car_class=None,
        seats=None,
    ):
        required_days = (end_date - start_date).days

        qs = (
            CarAvailability.objects
            .filter(
                date__gte=start_date,
                date__lt=end_date,
                available_units__gt=0
            )
            .values("car_listing")
            .annotate(
                total_days=Count("date", distinct=True),
                min_available=Min("available_units")
            )
            .filter(total_days=required_days)
        )

        car_ids = [row["car_listing"] for row in qs]

        cars = CarListing.objects.filter(id__in=car_ids)

        if brand:
            cars = cars.filter(brand=brand)
        if car_class:
            cars = cars.filter(car_class=car_class)
        if seats:
            cars = cars.filter(seats__gte=seats)

        # Return mapped availability data
        availability_map = {
            row["car_listing"]: row["min_available"] for row in qs
        }

        result = []
        for car in cars:
            result.append({
                "car": car,
                "available_units": availability_map.get(car.id, 0)
            })

        return result
    @staticmethod
    def ensure_future_availability(days_ahead=180, start_date=None):
        start = start_date or date.today()
        end = start + timedelta(days=days_ahead)

        car_listings = CarListing.objects.all()
        created = 0
        batch = []

        for car in car_listings:
            existing_dates = set(
                CarAvailability.objects.filter(
                    car_listing=car,
                    date__gte=start,
                    date__lt=end
                ).values_list("date", flat=True)
            )

            cursor = start
            while cursor < end:
                if cursor not in existing_dates:
                    batch.append(
                        CarAvailability(
                            car_listing=car,
                            date=cursor,
                            available_units=car.quantity,
                        )
                    )
                    if len(batch) >= 1000:
                        CarAvailability.objects.bulk_create(
                            batch,
                            batch_size=1000,
                            ignore_conflicts=True
                        )
                        created += len(batch)
                        batch = []
                cursor += timedelta(days=1)

        if batch:
            CarAvailability.objects.bulk_create(
                batch,
                batch_size=1000,
                ignore_conflicts=True
            )
            created += len(batch)

        return created

class EventSpaceAvailabilityService:
    @staticmethod
    def create_availability(space_listing, units_quantity, days=90):
        """
        Populates EventSpaceAvailability records for a new listing.
        The price comes from the listing's base_price (or other logic).
        """
        today = timezone.now().date()
        objs = []
        base_price = space_listing.base_price 
        for i in range(1, days + 1):
            objs.append(
                EventSpaceAvailability(
                    space_listing=space_listing,
                    available_eventspace=units_quantity, 
                    date=today + timedelta(days=i),
                    price=base_price,
                )
            )

        EventSpaceAvailability.objects.bulk_create(
            objs, batch_size=1000, ignore_conflicts=True
        )
        
    @staticmethod
    def ensure_availability(space_listing, start_date, days):
        existing_dates = set(
            EventSpaceAvailability.objects.filter(
                space_listing=space_listing,
                date__range=[start_date, start_date + timedelta(days=days)]
            ).values_list('date', flat=True)
        )
        
        objs = []
        base_price = space_listing.base_price or 0 
        
        for i in range(days):
            d = start_date + timedelta(days=i)
            if d not in existing_dates:
                 objs.append(
                    EventSpaceAvailability(
                        space_listing=space_listing,
                        available_eventspace=space_listing.total_units, 
                        date=d,
                        price=base_price,
                    )
                )
        
        if objs:
             EventSpaceAvailability.objects.bulk_create(
                objs, batch_size=1000, ignore_conflicts=True
            )


    @staticmethod
    def get_available_listings(hotel, space_type, check_in_date, check_out_date):
        """
        Retrieves EventSpaceListings that have availability for ALL days in the range.
        """
        required_days = (check_out_date - check_in_date).days

        # Aggregate availability across the date range
        qs = (
            EventSpaceAvailability.objects
            .filter(
                space_listing__hotel=hotel,
                space_listing__space_type=space_type,
                date__gte=check_in_date,
                date__lt=check_out_date,
                available_eventspace__gt=0 # Must have at least 1 unit available
            )
            .values("space_listing")
            .annotate(
                total_days=Count("date", distinct=True),
                min_available=Min("available_eventspace")
            )
            .filter(total_days=required_days) # Ensure availability exists for ALL days
        )

        # Extract listing IDs
        listing_ids = [row["space_listing"] for row in qs]

        listings = EventSpaceListing.objects.filter(id__in=listing_ids)

        return listings, qs

    @staticmethod
    def validate_availability(space_infos, check_in_date, check_out_date, lock=True):
        """
        Validates if the requested quantity of each space is available on ALL dates.
        `space_infos` is a list of dictionaries: [{"space_listing": listing_obj, "quantity": 1}]
        """
        dates = []
        date_cursor = check_in_date
        while date_cursor < check_out_date:
            dates.append(date_cursor)
            date_cursor += timedelta(days=1)
        
        space_listing_ids = [info["space_listing"].id for info in space_infos]
        queryset = EventSpaceAvailability.objects.filter(
            space_listing_id__in=space_listing_ids,
            date__in=dates
        )
        if lock:
            queryset = queryset.select_for_update()
            
        availabilities = queryset
        
        availability_map = {}
        for av in availabilities:
            key = (av.space_listing_id, av.date)
            availability_map[key] = av
        
        for date_cursor in dates:
            for info in space_infos:
                listing = info["space_listing"]
                quantity = info["quantity"]
                key = (listing.id, date_cursor)
                availability = availability_map.get(key)
                
                if not availability:
                    raise BookingConflict(
                        f"No availability data for {listing.title} on {date_cursor}"
                    )
                
                if availability.available_eventspace < quantity:
                    raise BookingConflict(
                        f"Not enough units available for {listing.title} on {date_cursor}. "
                        f"Available: {availability.available_eventspace}, Requested: {quantity}"
                    )

    @staticmethod
    def update_availability(
        space_infos,
        check_in_date,
        check_out_date,
        increment: bool = False,
    ):
        """
        Updates the available_units count. Decrements on booking, increments on cancellation.
        """
        dates = []
        date_cursor = check_in_date
        while date_cursor < check_out_date:
            dates.append(date_cursor)
            date_cursor += timedelta(days=1) 
        with transaction.atomic():
            for date_cursor in dates:
                for info in space_infos:
                    listing_id = info["space_listing"].id
                    quantity = info["quantity"]
                    
                    obj = EventSpaceAvailability.objects.select_for_update().filter(
                        space_listing_id=listing_id, date=date_cursor
                    )

                    if increment:
                        obj.update(available_eventspace=F("available_eventspace") + quantity)
                    else:
                        obj.update(available_eventspace=F("available_eventspace") - quantity)
                    
    @staticmethod
    def ensure_future_availability(days_ahead=180, start_date=None):
        """
        A maintenance function to ensure all listings have availability populated for the future.
        """
        start = start_date or timezone.now().date()
        end = start + timedelta(days=days_ahead)
        
        # Select related data to avoid N+1 queries in the loop
        listings = EventSpaceListing.objects.select_related("hotel")
        created = 0
        batch = []
        
        for listing in listings:
            if not listing.hotel:
                continue
            
            # Find all dates that already have availability for this listing in the range
            existing_dates = set(
                EventSpaceAvailability.objects.filter(
                    space_listing=listing,
                    date__gte=start,
                    date__lt=end
                ).values_list("date", flat=True)
            )
            
            cursor = start
            while cursor < end:
                if cursor not in existing_dates:
                    # Create a new availability record
                    batch.append(
                        EventSpaceAvailability(
                            space_listing=listing,
                            date=cursor,
                            available_eventspace=listing.total_units,
                            price=listing.base_price,
                        )
                    )
                    
                    if len(batch) >= 1000:
                        EventSpaceAvailability.objects.bulk_create(batch, batch_size=1000, ignore_conflicts=True)
                        created += len(batch)
                        batch = []
                cursor += timedelta(days=1)
                
        if batch:
            EventSpaceAvailability.objects.bulk_create(batch, batch_size=1000, ignore_conflicts=True)
            created += len(batch)
            
        return created
    @staticmethod
    def search_available_listings(
        check_in_date,
        check_out_date,
        required_quantity,
        address_query=None,
        max_distance_km=None,
    ):
        required_days = (check_out_date - check_in_date).days

        availability_qs = (
            EventSpaceAvailability.objects
            .filter(
                date__gte=check_in_date,
                date__lt=check_out_date,
                available_eventspace__gte=required_quantity
            )
            .values("space_listing")
            .annotate(
                total_days=Count("date", distinct=True),
                min_available=Min("available_eventspace")
            )
            .filter(total_days=required_days)
        )

        available_listing_ids = [row["space_listing"] for row in availability_qs]

        listings_qs = EventSpaceListing.objects.filter(id__in=available_listing_ids)

        if address_query:
            listings_qs = listings_qs.filter(
        Q(address__city__icontains=address_query) |
        Q(address__sub_city__icontains=address_query) |
        Q(address__street_line1__icontains=address_query)
    )

        listing_info_map = {
            row["space_listing"]: row["min_available"]
            for row in availability_qs
        }

        final_listings = []
        for listing in listings_qs:
            listing.min_available_for_period = listing_info_map.get(listing.id)
            final_listings.append(listing)

        return final_listings
class GuestHouseAvailabilityService:

    @staticmethod
    def create_availability(guest_house_room, units_quantity, days=90):
        today = timezone.now().date()
        objs = []

        for i in range(1, days + 1):
            objs.append(
                GuestHouseInventory(
                    guest_house_room=guest_house_room,
                    available_rooms=units_quantity,
                    date=today + timedelta(days=i)
                )
            )

        GuestHouseInventory.objects.bulk_create(
            objs, batch_size=1000, ignore_conflicts=True
        )

    @staticmethod
    def get_available_listings(check_in_date, check_out_date, min_units=1, address_filters=None):
        required_days = (check_out_date - check_in_date).days

        qs = GuestHouseInventory.objects.filter(
            date__gte=check_in_date,
            date__lt=check_out_date,
            available_rooms__gte=min_units
        )

        aggregated_rooms = qs.values("guest_house_room").annotate(
            total_days=Count("date", distinct=True),
            min_available=Min("available_rooms")
        ).filter(total_days=required_days)
        
        room_ids = [row["guest_house_room"] for row in aggregated_rooms]
        
        
        profiles = GuestHouseProfile.objects.filter(
            rooms__id__in=room_ids, 
            is_active=True
        ).distinct()

        if address_filters:
            filter_kwargs = {}
            address_fields = ["city", "country", "region", "sub_city"]
            for key in address_fields:
                value = address_filters.get(key)               
                if value:
                    filter_kwargs[f"address__{key}__icontains"] = value

            if filter_kwargs:
                profiles = profiles.filter(**filter_kwargs)

        return profiles, aggregated_rooms

    @staticmethod
    def get_availability_matrix(guest_house_id, start_date, end_date):
        room_ids = GuestHouseRoom.objects.filter(guest_house_id=guest_house_id).values_list('id', flat=True)

        inventory_qs = GuestHouseInventory.objects.filter(
            guest_house_room_id__in=room_ids,
            date__gte=start_date,
            date__lte=end_date,
        ).values('guest_house_room_id', 'date', 'available_rooms')

        matrix = {}
        for row in inventory_qs:
            r_id = str(row['guest_house_room_id'])
            d_str = row['date'].isoformat()
            if r_id not in matrix:
                matrix[r_id] = {}
            matrix[r_id][d_str] = row['available_rooms']

        return matrix

    @staticmethod
    def validate_availability(room_infos, check_in_date, check_out_date, lock=True):
        """
        Validate availability for each room in room_infos:
        room_infos = [{"guesthouse_room": obj, "quantity": 2}, ...]
        """
        dates = [check_in_date + timedelta(days=i) for i in range((check_out_date - check_in_date).days)]
        room_ids = [r["guesthouse_room"].id for r in room_infos]

        queryset = GuestHouseInventory.objects.filter(
            guest_house_room_id__in=room_ids,
            date__in=dates
        )
        if lock:
            queryset = queryset.select_for_update()
            
        availabilities = queryset

        availability_map = {(av.guest_house_room_id, av.date): av for av in availabilities}

        for date in dates:
            for info in room_infos:
                room = info["guesthouse_room"]
                qty = info["quantity"]
                key = (room.id, date)
                av = availability_map.get(key)

                if not av:
                    raise BookingConflict(f"No availability for {room.title} on {date}")
                if av.available_rooms < qty:
                    raise BookingConflict(f"Not enough rooms for {room.title} on {date}. Available: {av.available_rooms}, Requested: {qty}")

    @staticmethod
    def update_availability(room_infos, check_in_date, check_out_date, increment=False):
        """
        Updates available_rooms:
        decrement if booking, increment if cancellation.
        """
        dates = [check_in_date + timedelta(days=i) for i in range((check_out_date - check_in_date).days)]

        with transaction.atomic():
            for date in dates:
                for info in room_infos:
                    room_id = info["guesthouse_room"].id
                    qty = info["quantity"]
                    qs = GuestHouseInventory.objects.select_for_update().filter(
                        guest_house_room_id=room_id, date=date
                    )
                    if increment:
                        qs.update(available_rooms=F("available_rooms") + qty)
                    else:
                        qs.update(available_rooms=F("available_rooms") - qty)

    @staticmethod
    def ensure_future_availability(days_ahead=180, start_date=None):
        """
        Ensure all guest house rooms have availability populated.
        """
        start = start_date or timezone.now().date()
        end = start + timedelta(days=days_ahead)
        rooms = GuestHouseRoom.objects.all()
        batch = []
        created = 0

        for room in rooms:
            existing_dates = set(
                GuestHouseInventory.objects.filter(
                    guest_house_room=room,
                    date__gte=start,
                    date__lt=end
                ).values_list("date", flat=True)
            )

            for day in range((end - start).days):
                date = start + timedelta(days=day)
                if date not in existing_dates:
                    batch.append(
                        GuestHouseInventory(
                            guest_house_room=room,
                            date=date,
                            available_rooms=room.total_units,
                            price=None
                        )
                    )

                    if len(batch) >= 1000:
                        GuestHouseInventory.objects.bulk_create(batch, batch_size=1000, ignore_conflicts=True)
                        created += len(batch)
                        batch = []

        if batch:
            GuestHouseInventory.objects.bulk_create(batch, batch_size=1000, ignore_conflicts=True)
            created += len(batch)

        return created


class GuestHouseBookingService:
    @transaction.atomic()
    @staticmethod
    def create_booking(validated_data, user=None, is_walk_in=False):
        """
        Creates a Guest House Booking, validates availability, 
        captures T&C snapshots, and updates inventory.
        """
        guest_phone = validated_data.get("guest_phone")
        if not guest_phone or not str(guest_phone).strip():
             raise ValidationError({"guest_phone": "Phone number is required for every booking."})

        items_data = validated_data.pop("items")
        terms_accepted = validated_data.pop("terms_accepted", False)
        terms_version = validated_data.pop("terms_version", "")
        payment_currency = validated_data.pop("payment_currency", "ETB")
        validated_data.pop("is_walk_in", None)

        if user:
            validated_data["renter"] = user

        # T&C Validation & Snapshot
        if items_data:
            from apps.listing.services import TermsService
            
            if len(items_data) == 0:
                raise ValidationError("Booking items are required")
            
            try:
                first_room = items_data[0]['room']
                hotel = first_room.guest_house 

                is_privileged = False

                if user and user.is_superuser:
                    is_privileged = True
                elif user and user.is_authenticated and is_walk_in:
                    from apps.listing.utils import is_user_staff_of_listing
                    if is_user_staff_of_listing(user, hotel):
                        is_privileged = True

                if is_privileged:
                     validated_data['status'] = GuestHouseBooking.RentStatus.WALK_IN

                if not terms_accepted and not is_privileged:
                     raise ValidationError({"terms_accepted": "You must accept the terms and conditions."})

                if is_privileged and not terms_accepted:
                    terms_accepted = True

                snapshot_data = TermsService.validate_and_snapshot_terms(
                    content_object=hotel,
                    terms_version=terms_version,
                    terms_accepted=terms_accepted,
                    allow_missing=is_privileged
                )
            except Exception as e:
                logger.error(f"T&C validation failed: {e}")
                raise

            from apps.listing.models import GuestHouseBookingItem
            from apps.listing.services import PriceService, StayAvailabilityService
            from django.conf import settings
            from decimal import Decimal

            booking = GuestHouseBooking(
                total_price=Decimal("0.00"),
                currency=payment_currency,
                **validated_data,
            )
            booking.save()
            
            rooms_info = []
            currencies = set()
            for item_data in items_data:
                room = item_data["room"]
                rooms_info.append({
                     "guesthouse_room": room,
                     "quantity": item_data['units_booked']
                })
                if getattr(room, "currency", None):
                    currencies.add(room.currency)

            if len(currencies) > 1:
                raise ValidationError({
                    "items": f"All guesthouse rooms must have the same currency. Found: {', '.join(sorted(currencies))}"
                })

            if currencies:
                booking_currency = currencies.pop()
            else:
                booking_currency = payment_currency or "ETB"

            GuestHouseAvailabilityService.validate_availability(
                rooms_info, booking.start_date, booking.end_date
            )

            total_price = Decimal(0)
            nights = (booking.end_date - booking.start_date).days
            
            for item_data in items_data:
                room = item_data['room']
                
                price_details = PriceService.resolve_price_details_batch(
                     room, booking.start_date, booking.end_date
                )
                
                total_room_native = sum(
                    Decimal(str(d["price_per_unit"])) for d in price_details
                )
                avg_rate_native = total_room_native / nights if nights > 0 else 0
                
                converted_rate = avg_rate_native
                if room.currency != booking_currency:
                    try:
                        converted_rate = convert_currency(avg_rate_native, room.currency, booking_currency)
                    except Exception:
                        converted_rate = avg_rate_native 

                booking_item = GuestHouseBookingItem.objects.create(
                    booking=booking,
                    room=room,
                    units_booked=item_data['units_booked'],
                    price_per_unit=converted_rate,
                )
                
                total_price += booking_item.subtotal() # Removed nights parameter, assuming subtotal handles it internally

                # Process Addons (Assuming GuestHouseBooking has addons, if not, this part needs adjustment)
                # addons_data = item_data.get('addons', [])
                # for addon_input in addons_data:
                #     offering = addon_input.get('_offering')
                #     if not offering:
                #         continue
                    
                #     # Convert Addon Price
                #     addon_price = offering.price_per_unit
                #     if offering.currency != payment_currency:
                #         try:
                #             addon_price = convert_currency(offering.price_per_unit, offering.currency, payment_currency)
                #         except Exception:
                #             addon_price = offering.price_per_unit

                #     BookingAddon.objects.create(
                #         booking_item=booking_item,
                #         offering=offering,
                #         name=offering.name,
                #         description=offering.description,
                #         category=offering.category,
                #         quantity=addon_input.get('quantity', 1),
                #         price_per_unit=addon_price,
                #         currency=payment_currency # Now matches booking
                #     )
            
            grand_total = Decimal(0)
            for item in booking.items.all():
                grand_total += item.subtotal(nights=nights)
            
            fee_rate = get_effective_platform_fee_rate(booking=booking, user=user, exclude_booking=booking)
            platform_fee = grand_total * fee_rate
            booking.currency = booking_currency
            booking.total_price = grand_total + platform_fee
            
            booking.terms_accepted = True
            booking.terms_version = snapshot_data['version']
            booking.terms_content_snapshot = snapshot_data['content_snapshot']
            booking.terms_accepted_at = snapshot_data['accepted_at']
            
            booking.save()

            GuestHouseAvailabilityService.update_availability( # Changed to GuestHouseAvailabilityService
                rooms_info, booking.start_date, booking.end_date, increment=False
            )

            return booking

    @staticmethod
    def _confirmation_phone(booking):
        return booking.guest_phone or getattr(getattr(booking, "renter", None), "phone", "")

    @staticmethod
    def _send_confirmation_sms(booking):
        phone = GuestHouseBookingService._confirmation_phone(booking)
        if not phone:
            return False

        message = (
            f"Your Mechot Marefiya guest house booking {booking.booking_reference} is confirmed "
            f"for {booking.start_date} to {booking.end_date}. Total: {booking.total_price} {booking.currency}."
        )
        try:
            send_sms(phone, message)
            return True
        except Exception as exc:
            logger.warning(
                "Could not send guesthouse booking confirmation SMS for %s: %s",
                booking.id,
                exc,
            )
            return False

    @staticmethod
    def confirm_booking(booking):
        if booking.status == booking.RentStatus.CONFIRMED:
            return booking

        if booking.status == booking.RentStatus.CANCELLED:
            raise BookingConflict(f"GuestHouseBooking {booking.id} was cancelled.")

        if not booking.terms_accepted or not booking.terms_version or not booking.terms_content_snapshot:
            logger.error(f"CRITICAL: GuestHouseBooking {booking.id} confirmed without T&C snapshot!")
            if not booking.is_legacy:
                raise ValidationError("Legal integrity check failed: Missing T&C snapshot.")

        booking.status = booking.RentStatus.CONFIRMED
        booking.save()
        
        GuestHouseBookingService._send_confirmation_sms(booking)
        
        try:
             renter = getattr(booking, 'renter', None) or getattr(booking, 'user', None)
             if renter:
                NotificationService.create_notification(
                    user=renter,
                    notification_type=Notification.NotificationType.BOOKING_CONFIRMED,
                    title="Guest House Booking Confirmed",
                    message=f"Your booking {booking.booking_reference} is confirmed.",
                    metadata={'booking_reference': booking.booking_reference, 'booking_id': str(booking.id)},
                    priority=Notification.Priority.HIGH
                )
        except Exception:
             pass

        # Notify Vendor
        try:
            gh_profile = booking.items.first().room.guest_house
            vendor_user = None
            if gh_profile.company:
                vendor_user = gh_profile.company.user
            elif gh_profile.individual_owner:
                vendor_user = gh_profile.individual_owner.staff_members.first()
            
            if vendor_user:
                NotificationService.create_notification(
                    user=vendor_user,
                    notification_type=Notification.NotificationType.NEW_BOOKING_RECEIVED,
                    title="New Guest House Booking",
                    message=f"New booking ({booking.booking_reference}) received for {gh_profile.title}.",
                    metadata={
                        'booking_reference': booking.booking_reference,
                        'booking_id': str(booking.id),
                    },
                    priority=Notification.Priority.HIGH
                )
        except Exception:
            logger.warning(f"Could not send vendor notification for GuestHouseBooking {booking.id}")

        return booking
    
    @staticmethod
    def cancel_booking(booking):
        """
        Cancel a booking and restore availability.
        Called when payment fails or user cancels.
        """
        if booking.status == booking.RentStatus.CANCELLED:
            logger.info(f"GuestHouseBooking {booking.id} is already CANCELLED.")
            return booking

        # Restore availability if booking was pending or confirmed
        if booking.status in [booking.RentStatus.PENDING, booking.RentStatus.CONFIRMED]:
            # Prepare room infos for availability service
            room_infos = [{
                "guesthouse_room": item.room,
                "quantity": item.units_booked
            } for item in booking.items.all()]
            
            # Increment availability
            GuestHouseAvailabilityService.update_availability(
                room_infos,
                booking.start_date,
                booking.end_date,
                increment=True
            )
            logger.info(f"Restored availability for GuestHouseBooking {booking.id}")

        booking.status = booking.RentStatus.CANCELLED
        booking.save()
        logger.info(f"GuestHouseBooking {booking.id} status updated to CANCELLED.")
        return booking

    @staticmethod
    def get_booking_total(booking: "GuestHouseBooking", fee_rate=None):
        if fee_rate is None:
            fee_rate = get_effective_platform_fee_rate(booking=booking)

        item_subtotals = [item.subtotal() for item in booking.items.all()]
        calculation = PriceCalculationService.calculate_totals(item_subtotals, fee_rate=fee_rate)
        return calculation["grand_total"]


class PropertyRentalAvailabilityService:
    @staticmethod
    def create_availability(property_listing, days=90, start_date=None):
        start = start_date or timezone.now().date()
        objs = []
        for i in range(1, days + 1):
            objs.append(
                PropertyRentalAvailability(
                    property_listing=property_listing,
                    date=start + timedelta(days=i),
                    available_units=1,
                    price=None,
                )
            )
        PropertyRentalAvailability.objects.bulk_create(objs, batch_size=1000, ignore_conflicts=True)

    @staticmethod
    def validate_availability(property_listing, start_date, end_date, lock=True):
        dates = [start_date + timedelta(days=i) for i in range((end_date - start_date).days)]
        queryset = PropertyRentalAvailability.objects.filter(
            property_listing=property_listing,
            date__in=dates,
        )
        if lock:
            queryset = queryset.select_for_update()

        availability_map = {availability.date: availability for availability in queryset}
        for date_value in dates:
            availability = availability_map.get(date_value)
            if not availability:
                raise BookingConflict(
                    f"Availability has not been released for {property_listing.title} on {date_value}. "
                    "Please choose closer dates."
                )
            if availability.available_units < 1:
                raise BookingConflict(f"{property_listing.title} is not available on {date_value}.")

    @staticmethod
    def update_availability(property_listing, start_date, end_date, increment=False):
        dates = [start_date + timedelta(days=i) for i in range((end_date - start_date).days)]
        with transaction.atomic():
            for date_value in dates:
                queryset = PropertyRentalAvailability.objects.select_for_update().filter(
                    property_listing=property_listing,
                    date=date_value,
                )
                if increment:
                    queryset.update(available_units=F("available_units") + 1)
                else:
                    queryset.update(available_units=F("available_units") - 1)

    @staticmethod
    def price_details(property_listing, start_date, end_date, payment_currency=None):
        dates = [start_date + timedelta(days=i) for i in range((end_date - start_date).days)]
        inventories = {
            availability.date: availability
            for availability in PropertyRentalAvailability.objects.filter(
                property_listing=property_listing,
                date__in=dates,
            )
        }
        native_currency = property_listing.currency
        target_currency = payment_currency or native_currency
        details = []
        for date_value in dates:
            availability = inventories.get(date_value)
            if availability and availability.price is not None:
                native_price = Decimal(availability.price).quantize(Decimal("0.01"))
                detail = {
                    "date": date_value,
                    "price": native_price,
                    "price_per_unit": native_price,
                    "source": "availability",
                    "rate_id": None,
                    "note": None,
                    "is_discounted": native_price < Decimal(property_listing.base_price),
                }
            else:
                detail = PriceService.resolve_price_detail(property_listing, date_value)
                detail["date"] = date_value
                native_price = Decimal(detail["price_per_unit"])

            if target_currency != native_currency:
                converted = convert_currency(native_price, native_currency, target_currency)
                detail["price"] = converted
                detail["price_per_unit"] = converted
                detail["currency"] = target_currency
            else:
                detail["currency"] = native_currency
            details.append(detail)
        return details


class PropertyRentalBookingService:
    @staticmethod
    def _build_snapshot(booking):
        listing = booking.property_listing
        return {
            "property_listing": {
                "id": str(listing.id),
                "title": listing.title,
                "description": listing.description,
                "property_type": listing.property_type,
                "base_price": str(listing.base_price),
                "currency": listing.currency,
                "address": {
                    "street_line1": listing.address.street_line1,
                    "country": listing.address.country,
                    "city": listing.address.city,
                    "sub_city": listing.address.sub_city,
                    "state": listing.address.state,
                    "postal_code": listing.address.postal_code,
                } if listing.address_id else None,
            },
            "start_date": booking.start_date.isoformat(),
            "end_date": booking.end_date.isoformat(),
            "total_price": str(booking.total_price),
            "currency": booking.currency,
        }

    @staticmethod
    def calculate_price_preview(property_listing, start_date, end_date, *, payment_currency=None, guest_phone=None, display_currency=None):
        currency = payment_currency or property_listing.currency
        price_details = PropertyRentalAvailabilityService.price_details(
            property_listing,
            start_date,
            end_date,
            payment_currency=currency,
        )
        item_subtotal = sum(Decimal(str(detail["price_per_unit"])) for detail in price_details)
        total_items = [{
            "id": str(property_listing.id),
            "title": property_listing.title,
            "units": 1,
            "price_per_unit": f"{(price_details[0]['price_per_unit'] if price_details else property_listing.base_price):.2f}",
            "subtotal": f"{item_subtotal:.2f}",
            "breakdown": price_details,
        }]
        return {
            "nights": (end_date - start_date).days,
            "items": total_items,
            **PriceCalculationService.calculate_preview_totals(
                [item_subtotal],
                currency,
                display_currency,
                items=total_items,
                fee_rate=get_effective_platform_fee_rate(phone=guest_phone),
            ),
        }

    @transaction.atomic()
    @staticmethod
    def create_booking(validated_data, user=None):
        guest_phone = validated_data.get("guest_phone")
        if not guest_phone or not str(guest_phone).strip():
            raise ValidationError({"guest_phone": "Phone number is required for every booking."})

        property_listing = validated_data["property_listing"]
        if property_listing.individual_owner_id:
            from apps.account.services import is_agreement_active

            if not is_agreement_active(property_listing.individual_owner):
                raise ValidationError("Owner has not completed compliance agreement.")
        start_date = validated_data["start_date"]
        end_date = validated_data["end_date"]
        terms_accepted = validated_data.pop("terms_accepted", False)
        terms_version = validated_data.pop("terms_version", "")
        payment_currency = validated_data.pop("payment_currency", property_listing.currency)
        validated_data.pop("otp_challenge_id", None)
        validated_data.pop("otp_code", None)
        validated_data.pop("guest_verification_token", None)

        PropertyRentalAvailabilityService.validate_availability(
            property_listing,
            start_date,
            end_date,
            lock=True,
        )

        terms_data = TermsService.validate_and_snapshot_terms(
            content_object=property_listing,
            terms_version=terms_version,
            terms_accepted=terms_accepted,
        )
        if user:
            validated_data["renter"] = user

        preview = PropertyRentalBookingService.calculate_price_preview(
            property_listing,
            start_date,
            end_date,
            payment_currency=payment_currency,
            guest_phone=validated_data.get("guest_phone") or getattr(user, "phone", None),
        )
        booking = PropertyRentalBooking.objects.create(
            total_price=Decimal(str(preview["totals"]["grand_total"])),
            currency=payment_currency,
            terms_accepted=True,
            terms_version=terms_data["version"],
            terms_accepted_at=terms_data["accepted_at"],
            terms_content_snapshot=terms_data["content_snapshot"],
            **validated_data,
        )
        booking.snapshot = PropertyRentalBookingService._build_snapshot(booking)
        booking.save(update_fields=["snapshot", "updated_at"])

        PropertyRentalAvailabilityService.update_availability(
            property_listing,
            start_date,
            end_date,
            increment=False,
        )
        return booking

    @staticmethod
    def cancel_booking(booking):
        if booking.status == booking.RentStatus.CANCELLED:
            logger.info("PropertyRentalBooking %s is already CANCELLED.", booking.id)
            return booking
        if booking.status in [booking.RentStatus.PENDING, booking.RentStatus.CONFIRMED]:
            PropertyRentalAvailabilityService.update_availability(
                booking.property_listing,
                booking.start_date,
                booking.end_date,
                increment=True,
            )
        booking.status = booking.RentStatus.CANCELLED
        booking.save(update_fields=["status", "updated_at"])
        return booking

    @staticmethod
    def confirm_booking(booking):
        if booking.status == booking.RentStatus.CONFIRMED:
            return booking
        if booking.status == booking.RentStatus.CANCELLED:
            raise BookingConflict(f"PropertyRentalBooking {booking.id} was cancelled.")

        if not booking.terms_accepted or not booking.terms_version or not booking.terms_content_snapshot:
            logger.error("CRITICAL: PropertyRentalBooking %s confirmed without T&C snapshot.", booking.id)
            if not booking.is_legacy:
                raise ValidationError("Legal integrity check failed: Missing T&C snapshot.")

        booking.status = booking.RentStatus.CONFIRMED
        booking.save(update_fields=["status", "updated_at"])
        return booking

    @staticmethod
    def get_booking_total(booking, fee_rate=None):
        if fee_rate is None:
            fee_rate = get_effective_platform_fee_rate(booking=booking)
        nights = (booking.end_date - booking.start_date).days
        item_subtotal = Decimal(booking.property_listing.base_price) * Decimal(nights)
        return PriceCalculationService.calculate_totals([item_subtotal], fee_rate=fee_rate)["grand_total"]


class CarRentalService:
    @staticmethod
    def _build_snapshot(rental: "CarRental", *, fee_rate):
        duration = (rental.end_date - rental.start_date).days or 1
        items_snapshots = []
        raw_rental_subtotal = Decimal("0.00")

        for item in rental.rental_items.all():
            item_total = item.subtotal(days=duration)
            raw_rental_subtotal += item_total
            items_snapshots.append(
                {
                    "car_listing": {
                        "id": str(item.car_listing.id),
                        "title": f"{item.car_listing.brand} {item.car_listing.model}",
                    },
                    "units_booked": item.units_rent,
                    "nights": duration,
                    "nightly_rate": f"{item.price_per_unit:.2f}",
                    "stay_total": f"{item_total:.2f}",
                    "currency": rental.currency,
                }
            )

        platform_fee = raw_rental_subtotal * fee_rate
        grand_total = raw_rental_subtotal + platform_fee
        return {
            "rental_id": str(rental.id),
            "start_date": rental.start_date.isoformat(),
            "end_date": rental.end_date.isoformat(),
            "currency": rental.currency,
            "billing": {
                "subtotal_items": f"{raw_rental_subtotal:.2f}",
                "platform_fee": f"{platform_fee:.2f}",
                "grand_total": f"{grand_total:.2f}",
            },
            "audit_items": items_snapshots,
            "snapshot_version": 3,
        }

    @transaction.atomic()
    @staticmethod
    def create_booking(validated_data, user=None):
        guest_phone = validated_data.get("guest_phone")
        if not guest_phone or not str(guest_phone).strip():
            raise ValidationError({"guest_phone": "Phone number is required for every booking."})

        rental_items_data = validated_data.pop('rental_items')
        terms_accepted = validated_data.pop("terms_accepted", False)
        terms_version = validated_data.pop("terms_version", "")

        if user:
            validated_data["renter"] = user

        # T&C Validation & Snapshot
        if rental_items_data:
            from apps.listing.services import TermsService
            try:
                # Get company from first car listing
                first_car = rental_items_data[0]["car_listing"]
                company = first_car.company
                if company:
                    tc_data = TermsService.validate_and_snapshot_terms(
                        content_object=company,
                        terms_version=terms_version,
                        terms_accepted=terms_accepted
                    )
                    validated_data['terms_content_snapshot'] = tc_data['content_snapshot']
                    validated_data['terms_accepted_at'] = tc_data['accepted_at']
                    validated_data['terms_version'] = tc_data['version']
                    validated_data['terms_accepted'] = True
            except Exception as e:
                logger.error(f"T&C validation failed for CarRental: {e}")
                raise

        # Calculate Total Price
        rental_days = (validated_data["end_date"] - validated_data["start_date"]).days or 1
        total_price = sum(
            item['units_rent'] * item['price_per_unit'] * rental_days
            for item in rental_items_data
        )
        validated_data["total_price"] = total_price

        # Create Rental Object
        from apps.listing.models import CarRental, CarRentalItem
        rental = CarRental.objects.create(**validated_data)

        currencies = set()
        for item in rental_items_data:
            car = item["car_listing"]
            if car.currency:
                currencies.add(car.currency)
        
        if len(currencies) > 1:
            raise ValidationError({
                "rental_items": f"All cars must have the same currency. Found: {', '.join(currencies)}"
            })
        
        if rental_items_data and currencies:
            rental.currency = currencies.pop()
        elif rental_items_data:
            rental.currency = "ETB"
        
        rental.save(update_fields=["currency"])

        # Create Rental Objects & Reserve Availability
        from apps.listing.services import CarAvailabilityService
        for item in rental_items_data:
            listing = item["car_listing"]
            units = item["units_rent"]

            CarRentalItem.objects.create(
                car_rental=rental, **item
            )

            # decrement daily availability
            CarAvailabilityService.reserve_daily_units(
                listing, rental.start_date, rental.end_date, units
            )

        try:
            fee_rate = get_effective_platform_fee_rate(booking=rental, user=user, exclude_booking=rental)
            rental.snapshot = CarRentalService._build_snapshot(rental, fee_rate=fee_rate)
        except Exception as e:
            logger.error(f"Snapshot creation failed for CarRental: {e}")
            
        rental.save(update_fields=['snapshot'])

        # Update Total Price (Includes 5% Platform Fee)
        fee_rate = get_effective_platform_fee_rate(booking=rental, user=user, exclude_booking=rental)
        rental.total_price = CarRentalService.get_booking_total(rental, fee_rate=fee_rate)
        rental.save(update_fields=['total_price'])

        return rental

    @staticmethod
    def get_booking_total(rental: "CarRental", fee_rate=None):
        if fee_rate is None:
            fee_rate = get_effective_platform_fee_rate(booking=rental)

        days = (rental.end_date - rental.start_date).days or 1
        item_subtotals = [item.subtotal(days=days) for item in rental.rental_items.all()]
        calculation = PriceCalculationService.calculate_totals(item_subtotals, fee_rate=fee_rate)
        return calculation["grand_total"]

    @staticmethod
    def calculate_price_preview(*, start_date, end_date, items, display_currency=None, guest_phone=None):
        nights = (end_date - start_date).days
        total_items = []
        item_subtotals = []

        currencies = {
            item["car_listing"].currency
            for item in items
            if getattr(item["car_listing"], "currency", None)
        }
        if len(currencies) > 1:
            raise ValidationError(
                {"items": f"All selected items must have the same currency. Found: {', '.join(sorted(currencies))}"}
            )
        currency = list(currencies)[0] if currencies else "ETB"

        for item in items:
            listing = item["car_listing"]
            units = item["units_rent"]

            availability = CarAvailabilityService.check_daily_availability(
                car_listing=listing,
                start_date=start_date,
                end_date=end_date,
                quantity=units,
            )
            if not availability.get("available", False):
                raise BookingConflict(
                    f"{listing.title} is not available: {availability.get('reason', 'unavailable')}"
                )

            price_details = PriceService.resolve_price_details_batch(listing, start_date, end_date)
            item_base_total = sum(Decimal(str(detail["price_per_unit"])) for detail in price_details) * units
            item_subtotals.append(item_base_total)
            total_items.append(
                {
                    "id": str(listing.id),
                    "title": listing.title,
                    "units": units,
                    "price_per_unit": f"{(price_details[0]['price_per_unit'] if price_details else listing.base_price):.2f}",
                    "subtotal": f"{item_base_total:.2f}",
                    "breakdown": price_details,
                }
            )

        return {
            "nights": nights,
            "items": total_items,
            **PriceCalculationService.calculate_preview_totals(
                item_subtotals,
                currency,
                display_currency,
                items=total_items,
                fee_rate=get_effective_platform_fee_rate(phone=guest_phone),
            ),
        }

    @staticmethod
    def _extension_fee_rate(rental: "CarRental") -> Decimal:
        snapshot = rental.snapshot if isinstance(rental.snapshot, dict) else {}
        billing = snapshot.get("billing") if isinstance(snapshot, dict) else None
        if isinstance(billing, dict):
            try:
                subtotal = Decimal(str(billing.get("subtotal_items", "0")))
                platform_fee = Decimal(str(billing.get("platform_fee", "0")))
                if subtotal > 0:
                    return (platform_fee / subtotal).quantize(Decimal("0.0001"))
            except Exception:
                pass
        return get_effective_platform_fee_rate(booking=rental)

    @staticmethod
    def _validate_extension_target(rental: "CarRental", *, new_end_date):
        if rental.status != CarRental.RentStatus.CONFIRMED:
            raise ValidationError(
                {"detail": "Only confirmed car rentals can be extended."}
            )
        if new_end_date <= rental.end_date:
            raise ValidationError(
                {"new_end_date": "New end date must be after the current end date."}
            )

    @staticmethod
    def _get_extension_items_subtotal(rental: "CarRental", *, extra_days: int) -> Decimal:
        subtotal = Decimal("0.00")
        for item in rental.rental_items.all():
            subtotal += Decimal(item.subtotal(days=extra_days))
        return subtotal

    @staticmethod
    def check_extension_availability(rental: "CarRental", *, new_end_date):
        CarRentalService._validate_extension_target(rental, new_end_date=new_end_date)

        for item in rental.rental_items.select_related("car_listing").all():
            result = CarAvailabilityService.check_daily_availability(
                car_listing=item.car_listing,
                start_date=rental.end_date,
                end_date=new_end_date,
                quantity=item.units_rent,
            )
            if not result.get("available", False):
                raise BookingConflict(
                    f"{item.car_listing.title} is not available for the requested extension: "
                    f"{result.get('reason', 'unavailable')}"
                )

    @staticmethod
    def hold_extension_availability(rental: "CarRental", *, new_end_date):
        CarRentalService.check_extension_availability(rental, new_end_date=new_end_date)
        for item in rental.rental_items.select_related("car_listing").all():
            CarAvailabilityService.reserve_daily_units(
                item.car_listing,
                rental.end_date,
                new_end_date,
                item.units_rent,
            )

    @staticmethod
    def release_extension_hold(extension_request: "CarRentalExtensionRequest"):
        if not extension_request.availability_held:
            return extension_request

        rental = extension_request.rental
        for item in rental.rental_items.select_related("car_listing").all():
            CarAvailabilityService.release_daily_units(
                item.car_listing,
                extension_request.original_end_date,
                extension_request.requested_end_date,
                item.units_rent,
            )

        extension_request.availability_held = False
        extension_request.save(update_fields=["availability_held", "updated_at"])
        return extension_request

    @staticmethod
    def expire_stale_extension_requests():
        stale_statuses = [
            CarRentalExtensionRequest.ExtensionStatus.REQUESTED,
            CarRentalExtensionRequest.ExtensionStatus.PAYMENT_INITIATED,
        ]
        stale_requests = list(
            CarRentalExtensionRequest.objects.select_related("rental")
            .filter(status__in=stale_statuses, expires_at__lte=timezone.now())
        )
        for extension_request in stale_requests:
            CarRentalService.mark_extension_request_failed(
                extension_request,
                status=CarRentalExtensionRequest.ExtensionStatus.EXPIRED,
                reason="Extension request expired before payment verification.",
            )
        return len(stale_requests)

    @staticmethod
    def calculate_extension_preview(rental: "CarRental", *, new_end_date, payment_currency=None):
        CarRentalService.expire_stale_extension_requests()
        CarRentalService.check_extension_availability(rental, new_end_date=new_end_date)

        extra_days = (new_end_date - rental.end_date).days
        fee_rate = CarRentalService._extension_fee_rate(rental)
        base_subtotal = CarRentalService._get_extension_items_subtotal(
            rental,
            extra_days=extra_days,
        )
        totals = PriceCalculationService.calculate_totals([base_subtotal], fee_rate=fee_rate)
        payment_currency = payment_currency or rental.currency or "ETB"
        payable_amount = totals["grand_total"]
        exchange_rate = Decimal("1.0")

        if payment_currency != rental.currency:
            payable_amount, exchange_rate = convert_currency(
                amount=payable_amount,
                source_currency=rental.currency or "ETB",
                target_currency=payment_currency,
                return_rate=True,
            )

        return {
            "booking_reference": rental.booking_reference,
            "current_end_date": rental.end_date,
            "new_end_date": new_end_date,
            "extra_days": extra_days,
            "extension_subtotal": base_subtotal.quantize(Decimal("0.01")),
            "platform_fee": totals["platform_fee"].quantize(Decimal("0.01")),
            "original_amount": totals["grand_total"].quantize(Decimal("0.01")),
            "original_currency": rental.currency or "ETB",
            "amount": Decimal(str(payable_amount)).quantize(Decimal("0.01")),
            "currency": payment_currency,
            "exchange_rate": Decimal(str(exchange_rate)),
            "fee_rate": fee_rate,
        }

    @staticmethod
    @transaction.atomic()
    def create_extension_request(
        rental: "CarRental",
        *,
        new_end_date,
        requested_by=None,
        payment_currency=None,
    ):
        CarRentalService.expire_stale_extension_requests()

        active_statuses = [
            CarRentalExtensionRequest.ExtensionStatus.REQUESTED,
            CarRentalExtensionRequest.ExtensionStatus.PAYMENT_INITIATED,
        ]
        existing = rental.extension_requests.filter(status__in=active_statuses).order_by("-created_at").first()
        if existing:
            raise ValidationError(
                {"detail": "There is already an active extension request for this rental."}
            )

        preview = CarRentalService.calculate_extension_preview(
            rental,
            new_end_date=new_end_date,
            payment_currency=payment_currency,
        )
        CarRentalService.hold_extension_availability(rental, new_end_date=new_end_date)

        extension_request = CarRentalExtensionRequest.objects.create(
            rental=rental,
            requested_by=requested_by,
            original_end_date=rental.end_date,
            requested_end_date=new_end_date,
            extra_days=preview["extra_days"],
            amount=preview["amount"],
            currency=preview["currency"],
            availability_held=True,
            expires_at=timezone.now()
            + timezone.timedelta(
                minutes=getattr(settings, "CAR_RENTAL_EXTENSION_REQUEST_TTL_MINUTES", 30)
            ),
            snapshot={
                "booking_reference": rental.booking_reference,
                "original_end_date": rental.end_date.isoformat(),
                "requested_end_date": new_end_date.isoformat(),
                "extra_days": preview["extra_days"],
                "extension_subtotal": f"{preview['extension_subtotal']:.2f}",
                "platform_fee": f"{preview['platform_fee']:.2f}",
                "grand_total": f"{preview['original_amount']:.2f}",
                "payment_amount": f"{preview['amount']:.2f}",
                "payment_currency": preview["currency"],
                "exchange_rate": str(preview["exchange_rate"]),
            },
        )
        return extension_request, preview

    @staticmethod
    @transaction.atomic()
    def mark_extension_request_failed(
        extension_request: "CarRentalExtensionRequest",
        *,
        status=None,
        reason=None,
    ):
        if extension_request.status == CarRentalExtensionRequest.ExtensionStatus.PAID_APPLIED:
            return extension_request

        CarRentalService.release_extension_hold(extension_request)
        extension_request.status = status or CarRentalExtensionRequest.ExtensionStatus.FAILED
        snapshot = extension_request.snapshot if isinstance(extension_request.snapshot, dict) else {}
        if reason:
            snapshot["failure_reason"] = reason
            extension_request.snapshot = snapshot
        extension_request.save(update_fields=["status", "snapshot", "updated_at"])
        return extension_request

    @staticmethod
    @transaction.atomic()
    def apply_paid_extension(extension_request: "CarRentalExtensionRequest"):
        if extension_request.status == CarRentalExtensionRequest.ExtensionStatus.PAID_APPLIED:
            return extension_request.rental

        if extension_request.is_expired:
            raise ValidationError("Car rental extension request has expired.")

        rental = CarRental.objects.select_for_update().get(id=extension_request.rental_id)
        if rental.status != CarRental.RentStatus.CONFIRMED:
            raise BookingConflict("Only confirmed car rentals can be extended.")

        if extension_request.availability_held:
            extension_request.availability_held = False

        rental.end_date = extension_request.requested_end_date
        fee_rate = CarRentalService._extension_fee_rate(rental)
        rental.total_price = CarRentalService.get_booking_total(rental, fee_rate=fee_rate)
        rental.snapshot = CarRentalService._build_snapshot(rental, fee_rate=fee_rate)
        rental.save(update_fields=["end_date", "total_price", "snapshot", "updated_at"])

        extension_request.status = CarRentalExtensionRequest.ExtensionStatus.PAID_APPLIED
        extension_request.applied_at = timezone.now()
        extension_request.save(
            update_fields=["status", "applied_at", "availability_held", "updated_at"]
        )
        return rental

    @staticmethod
    @transaction.atomic()
    def reschedule_booking(rental: "CarRental", *, start_date, end_date):
        if rental.status == CarRental.RentStatus.CANCELLED:
            raise BookingConflict("Cancelled rentals cannot be rescheduled.")

        if start_date >= end_date:
            raise ValidationError({"end_date": "End date must be after start date."})

        if start_date < date.today():
            raise ValidationError({"start_date": "Start date cannot be in the past."})

        original_start = rental.start_date
        original_end = rental.end_date

        for item in rental.rental_items.select_related("car_listing").all():
            CarAvailabilityService.release_daily_units(
                item.car_listing,
                original_start,
                original_end,
                item.units_rent,
            )

        for item in rental.rental_items.select_related("car_listing").all():
            result = CarAvailabilityService.check_daily_availability(
                car_listing=item.car_listing,
                start_date=start_date,
                end_date=end_date,
                quantity=item.units_rent,
            )
            if not result.get("available", False):
                raise BookingConflict(
                    f"{item.car_listing.title} is not available for the requested dates: {result.get('reason', 'unavailable')}"
                )

        for item in rental.rental_items.select_related("car_listing").all():
            CarAvailabilityService.reserve_daily_units(
                item.car_listing,
                start_date,
                end_date,
                item.units_rent,
            )

        rental.start_date = start_date
        rental.end_date = end_date
        fee_rate = get_effective_platform_fee_rate(booking=rental)
        rental.total_price = CarRentalService.get_booking_total(rental, fee_rate=fee_rate)
        rental.snapshot = CarRentalService._build_snapshot(rental, fee_rate=fee_rate)
        rental.save(update_fields=["start_date", "end_date", "total_price", "snapshot", "updated_at"])
        return rental

    @staticmethod
    @transaction.atomic()
    def cancel_booking(rental):
        if rental.status == rental.RentStatus.CANCELLED:
            raise BookingConflict("Rental is already cancelled.")

        rental.status = rental.RentStatus.CANCELLED
        rental.save(update_fields=["status", "updated_at"])

        for item in rental.rental_items.select_related("car_listing").all():
            CarAvailabilityService.update_availability(
                item.car_listing,
                item.units_rent,
                rental.start_date,
                rental.end_date,
                increment=True,
            )
        return rental

    @staticmethod
    def confirm_booking(rental):
        if rental.status == rental.RentStatus.CONFIRMED:
            return rental

        if rental.status == rental.RentStatus.CANCELLED:
            raise BookingConflict(f"CarRental {rental.id} was cancelled.")

        if not rental.terms_accepted or not rental.terms_version or not rental.terms_content_snapshot:
            logger.error(f"CRITICAL: CarRental {rental.id} confirmed without T&C snapshot!")
            if not rental.is_legacy:
                raise ValidationError("Legal integrity check failed: Missing T&C snapshot.")

        rental.status = rental.RentStatus.CONFIRMED
        rental.save()
        
        _send_booking_confirmation_sms_first(rental, label="car rental")
        
        try:
             renter = getattr(rental, 'renter', None) or getattr(rental, 'user', None)
             if renter:
                NotificationService.create_notification(
                    user=renter,
                    notification_type=Notification.NotificationType.BOOKING_CONFIRMED,
                    title="Car Rental Confirmed",
                    message=f"Your rental {rental.booking_reference} is confirmed.",
                    metadata={'booking_reference': rental.booking_reference, 'rental_id': str(rental.id)},
                    priority=Notification.Priority.HIGH
                )
        except Exception:
             pass

        try:
            company = rental.rental_items.first().car_listing.company
            if company and company.user:
                NotificationService.create_notification(
                    user=company.user,
                    notification_type=Notification.NotificationType.NEW_BOOKING_RECEIVED,
                    title="New Car Rental",
                    message=f"New rental ({rental.booking_reference}) received.",
                    metadata={
                        'booking_reference': rental.booking_reference,
                        'rental_id': str(rental.id),
                    },
                    priority=Notification.Priority.HIGH
                )
        except Exception:
            logger.warning(f"Could not send vendor notification for CarRental {rental.id}")

        return rental


class InventoryGridService:
    @staticmethod
    def get_availability_grid(property_id: str, property_type: str, start_date: date, days: int = 30):
        end_date = start_date + timedelta(days=days)
        dates = [start_date + timedelta(days=i) for i in range(days)]
        
        results = {
            "property_id": property_id,
            "property_type": property_type,
            "start_date": start_date,
            "days": days,
            "units": []
        }

        if property_type == 'hotel':
            hotel = get_object_or_404(HotelProfile, id=property_id)
            rooms = RoomListing.objects.filter(hotel=hotel, is_active=True)
            for room in rooms:
                availability_qs = StayAvailability.objects.filter(
                    room=room, date__range=[start_date, end_date - timedelta(days=1)]
                ).values('date', 'available_rooms')
                avail_map = {a['date']: a['available_rooms'] for a in availability_qs}
                
                prices = PriceService.resolve_price_details_batch(room, start_date, end_date)
                
                unit_days = []
                for p in prices:
                    d = p['date']
                    unit_days.append({
                        "date": d,
                        "available": avail_map.get(d, 0),
                        "price": p['price_per_unit'],
                        "source": p['source'],
                        "is_discounted": p['is_discounted']
                    })
                
                results['units'].append({
                    "id": str(room.id),
                    "title": room.title,
                    "days": unit_days
                })

        elif property_type == 'guesthouse':
            gh = get_object_or_404(GuestHouseProfile, id=property_id)
            rooms = GuestHouseRoom.objects.filter(guest_house=gh, is_active=True)
            for room in rooms:
                availability_qs = GuestHouseInventory.objects.filter(
                    guest_house_room=room, date__range=[start_date, end_date - timedelta(days=1)]
                ).values('date', 'available_rooms')
                avail_map = {a['date']: a['available_rooms'] for a in availability_qs}
                
                prices = PriceService.resolve_price_details_batch(room, start_date, end_date)
                
                unit_days = []
                for p in prices:
                    d = p['date']
                    unit_days.append({
                        "date": d,
                        "available": avail_map.get(d, 0),
                        "price": p['price_per_unit'],
                        "source": p['source'],
                        "is_discounted": p['is_discounted']
                    })
                
                results['units'].append({
                    "id": str(room.id),
                    "title": room.title,
                    "days": unit_days
                })
        
        elif property_type == 'eventspace':
            space = get_object_or_404(EventSpaceListing, id=property_id)
            
            EventSpaceAvailabilityService.ensure_availability(space, start_date, days)
            
            spaces = [space]
            for space in spaces:
                availability_qs = EventSpaceAvailability.objects.filter(
                    space_listing=space, date__range=[start_date, end_date - timedelta(days=1)]
                ).values('date', 'available_eventspace')
                avail_map = {a['date']: a['available_eventspace'] for a in availability_qs}
                
                unit_days = []
                for d in dates:
                    p = PriceService.resolve_price_detail(space, d)
                    unit_days.append({
                        "date": d,
                        "available": avail_map.get(d, 0),
                        "price": p['price_per_unit'],
                        "source": p['source'],
                        "is_discounted": p['is_discounted']
                    })
                
                results['units'].append({
                    "id": str(space.id),
                    "title": space.title,
                    "days": unit_days
                })

        return results

class WorkspaceStatusService:
    @staticmethod
    def get_workspace_stats(workspace_id: str, workspace_type: str) -> dict:
        today = timezone.localtime(timezone.now()).date()
        
        stats = {
            "arrivals_today": 0,
            "departures_today": 0,
            "in_house": 0,
            "availability_percentage": 0
        }

        if workspace_type == 'hotel':
            arrivals_qs = Booking.objects.filter(
                items__room__hotel__id=workspace_id,
                check_in_date=today,
                status__in=[Booking.BookingStatus.CONFIRMED, "checked_in"] # "checked_in" might be a string literal if not in choices
            ).distinct()
            stats["arrivals_today"] = arrivals_qs.count()

            departures_qs = Booking.objects.filter(
                items__room__hotel__id=workspace_id,
                check_out_date=today,
                status=Booking.BookingStatus.CONFIRMED
            ).distinct()
            stats["departures_today"] = departures_qs.count()

            in_house_qs = Booking.objects.filter(
                items__room__hotel__id=workspace_id,
                check_in_date__lte=today,
                check_out_date__gt=today,
                status=Booking.BookingStatus.CONFIRMED
            ).exclude(check_in_date=today).distinct() 
            stats["in_house"] = in_house_qs.count() + stats["arrivals_today"] # Everyone occupying rooms tonight.

            total_rooms = RoomListing.objects.filter(hotel__id=workspace_id, is_active=True).aggregate(
                total=sum('total_rooms')
            )['total'] or 0
            
            occupied_rooms = BookingItem.objects.filter(
                booking__items__room__hotel__id=workspace_id,
                booking__check_in_date__lte=today,
                booking__check_out_date__gt=today,
                booking__status=Booking.BookingStatus.CONFIRMED
            ).aggregate(total=sum('units_booked'))['total'] or 0

            if total_rooms > 0:
                available = max(0, total_rooms - occupied_rooms)
                stats["availability_percentage"] = int((available / total_rooms) * 100)
            else:
                stats["availability_percentage"] = 0

        elif workspace_type == 'guesthouse':
            arrivals_qs = GuestHouseBooking.objects.filter(
                items__room__guest_house__id=workspace_id,
                start_date=today,
                status=GuestHouseBooking.RentStatus.CONFIRMED
            ).distinct()
            stats["arrivals_today"] = arrivals_qs.count()

            departures_qs = GuestHouseBooking.objects.filter(
                items__room__guest_house__id=workspace_id,
                end_date=today,
                status=GuestHouseBooking.RentStatus.CONFIRMED
            ).distinct()
            stats["departures_today"] = departures_qs.count()

            in_house_qs = GuestHouseBooking.objects.filter(
                items__room__guest_house__id=workspace_id,
                start_date__lte=today,
                end_date__gt=today,
                status=GuestHouseBooking.RentStatus.CONFIRMED
            ).distinct()
            stats["in_house"] = in_house_qs.count()

            total_rooms = GuestHouseRoom.objects.filter(guest_house__id=workspace_id).aggregate(
                total=sum('total_units')
            )['total'] or 0
            
            occupied_rooms = GuestHouseBookingItem.objects.filter(
                booking__items__room__guest_house__id=workspace_id,
                booking__start_date__lte=today,
                booking__end_date__gt=today,
                booking__status=GuestHouseBooking.RentStatus.CONFIRMED
            ).aggregate(total=sum('units_booked'))['total'] or 0

            if total_rooms > 0:
                available = max(0, total_rooms - occupied_rooms)
                stats["availability_percentage"] = int((available / total_rooms) * 100)
            else:
                stats["availability_percentage"] = 0

        return stats
