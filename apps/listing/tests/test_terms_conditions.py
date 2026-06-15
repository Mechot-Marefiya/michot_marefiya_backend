import pytest
from django.core.exceptions import ValidationError as DjangoValidationError
from django.contrib.contenttypes.models import ContentType
from apps.listing.models import TermsAndConditions, Booking, EventSpaceBooking
from apps.listing.services import TermsService
from django.utils import timezone
from datetime import date, timedelta
from rest_framework import serializers

@pytest.mark.django_db
class TestTermsAndConditionsModel:
    """Test model-level behavior like auto-deactivation"""

    def test_auto_deactivation_of_previous_versions(self, hotel_profile):
        ct = ContentType.objects.get_for_model(hotel_profile)
        
        # 1. Create first active version
        v1 = TermsAndConditions.objects.create(
            content_type=ct,
            object_id=hotel_profile.id,
            version="1.0",
            content="Terms V1",
            effective_date=date.today(),
            is_active=True
        )
        assert v1.is_active is True

        # 2. Create second active version
        v2 = TermsAndConditions.objects.create(
            content_type=ct,
            object_id=hotel_profile.id,
            version="2.0",
            content="Terms V2",
            effective_date=date.today(),
            is_active=True
        )
        
        v1.refresh_from_db()
        assert v1.is_active is False
        assert v2.is_active is True

    def test_saving_inactive_version_does_not_deactivate_active_one(self, hotel_profile):
        ct = ContentType.objects.get_for_model(hotel_profile)
        
        v1 = TermsAndConditions.objects.create(
            content_type=ct,
            object_id=hotel_profile.id,
            version="1.0",
            is_active=True,
            content="V1",
            effective_date=date.today()
        )
        
        v2 = TermsAndConditions.objects.create(
            content_type=ct,
            object_id=hotel_profile.id,
            version="1.1 (draft)",
            is_active=False,
            content="Draft",
            effective_date=date.today()
        )
        
        v1.refresh_from_db()
        assert v1.is_active is True
        assert v2.is_active is False

@pytest.mark.django_db
class TestTermsService:
    """Test TermsService business logic"""

    def test_get_active_terms(self, hotel_profile):
        ct = ContentType.objects.get_for_model(hotel_profile)
        TermsAndConditions.objects.create(
            content_type=ct,
            object_id=hotel_profile.id,
            version="1.0",
            is_active=True,
            content="Active Terms",
            effective_date=date.today()
        )
        
        active_terms = TermsService.get_active_terms(hotel_profile)
        assert active_terms.version == "1.0"
        assert active_terms.content == "Active Terms"

    def test_validate_and_snapshot_terms_success(self, hotel_profile):
        ct = ContentType.objects.get_for_model(hotel_profile)
        TermsAndConditions.objects.create(
            content_type=ct,
            object_id=hotel_profile.id,
            version="1.0",
            is_active=True,
            content="Legal Content",
            effective_date=date.today()
        )
        
        snapshot = TermsService.validate_and_snapshot_terms(
            content_object=hotel_profile,
            terms_version="1.0",
            terms_accepted=True
        )
        
        assert snapshot['version'] == "1.0"
        assert snapshot['content_snapshot'] == "Legal Content"
        assert 'accepted_at' in snapshot

    def test_validate_and_snapshot_terms_fails_on_unaccepted(self, hotel_profile):
        with pytest.raises(DjangoValidationError, match="Terms and conditions must be accepted"):
            TermsService.validate_and_snapshot_terms(
                content_object=hotel_profile,
                terms_version="1.0",
                terms_accepted=False
            )

    def test_validate_and_snapshot_terms_fails_on_invalid_version(self, hotel_profile):
        with pytest.raises(DjangoValidationError, match="not found or inactive"):
            TermsService.validate_and_snapshot_terms(
                content_object=hotel_profile,
                terms_version="99.9",
                terms_accepted=True
            )

@pytest.mark.django_db
class TestTermsAPIIntegration:
    """Test API-level enforcement of T&C"""

    def test_hotel_booking_requires_terms(self, hotel_profile, company_user, address):
        from apps.listing.serializers import BookingSerializer
        
        # Create T&C
        TermsAndConditions.objects.create(
            content_object=hotel_profile,
            version="1.0",
            is_active=True,
            content="Terms Text",
            effective_date=date.today()
        )
        
        # Room setup (Simplified)
        from apps.listing.models import RoomListing
        room = RoomListing.objects.create(
            hotel=hotel_profile, 
            title="Test Room", 
            base_price=100, 
            total_units=1, 
            number_of_guests=2,
            address=address,
            room_size_sqm=25
        )

        # Missing terms_accepted
        data = {
            "check_in_date": date.today(),
            "check_out_date": str(date.today() + timedelta(days=1)),
            "items": [{"room": room.id, "units_booked": 1}],
            "guest_phone": "0911000000",
            "terms_version": "1.0",
            # "terms_accepted" missing
        }
        
        serializer = BookingSerializer(data=data)
        assert serializer.is_valid() is False
        assert "terms_accepted" in serializer.errors

    def test_hotel_booking_validation_success(self, hotel_profile, company_user, address):
        from apps.listing.serializers import BookingSerializer
        from datetime import timedelta
        
        TermsAndConditions.objects.create(
            content_object=hotel_profile,
            version="1.1",
            is_active=True,
            content="Legal Content",
            effective_date=date.today()
        )
        
        from apps.listing.models import RoomListing
        room = RoomListing.objects.create(
            hotel=hotel_profile, 
            title="Test Room", 
            base_price=100, 
            total_units=1, 
            number_of_guests=2,
            address=address,
            room_size_sqm=25
        )

        data = {
            "check_in_date": date.today(),
            "check_out_date": str(date.today() + timedelta(days=1)),
            "items": [{"room": room.id, "units_booked": 1}],
            "guest_phone": "0911000000",
            "terms_version": "1.1",
            "terms_accepted": True
        }
        
        serializer = BookingSerializer(data=data)
        assert serializer.is_valid() is True
        
    def test_eventspace_booking_requires_terms(self, hotel_profile, address):
        from apps.listing.serializers import EventSpaceBookingSerializer
        from apps.listing.models import EventSpaceListing
        from datetime import timedelta
        
        space = EventSpaceListing.objects.create(
            hotel=hotel_profile, 
            title="Ballroom", 
            base_price=500,
            number_of_guests=100,
            address=address,
            space_type="hall"
        )
        
        data = {
            "check_in_date": date.today(),
            "check_out_date": str(date.today() + timedelta(days=1)),
            "items": [{"event_space": space.id, "units_booked": 1}],
            "guest_phone": "0911000000",
            "terms_version": "1.0",
            "terms_accepted": False # Unaccepted
        }

        
        serializer = EventSpaceBookingSerializer(data=data)
        assert serializer.is_valid() is False
        assert "terms_accepted" in serializer.errors


