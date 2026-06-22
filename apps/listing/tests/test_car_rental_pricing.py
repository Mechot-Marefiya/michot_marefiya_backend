from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from apps.listing.models import CarListing, CarRental, CarRentalItem, TermsAndConditions
from apps.account.enums import RoleCode
from apps.account.models import CompanyProfile, Role
from apps.core.models import Address
from apps.listing.services import CarAvailabilityService
from decimal import Decimal
from datetime import date, timedelta
import uuid

User = get_user_model()

class CarRentalPricingTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        
        # Create Roles
        self.company_role, _ = Role.objects.get_or_create(
            name="Company", code=RoleCode.COMPANY.value
        )
        self.user_role, _ = Role.objects.get_or_create(
            name="User", code=RoleCode.USER.value
        )

        # Create Company User
        self.company_user = User.objects.create_user(
            email="car_company@example.com",
            password="password123",
            first_name="Car",
            last_name="Rental",
            role=self.company_role
        )
        self.company_profile = CompanyProfile.objects.create(
            user=self.company_user,
            name="Eco Ride",
            address=Address.objects.create(
                street_line1="Bole Road",
                city="Addis Ababa",
                country="Ethiopia",
            ),
            status=CompanyProfile.StatusChoice.APPROVED
        )

        # Create Regular User
        self.user = User.objects.create_user(
            email="customer@example.com",
            password="password123",
            first_name="John",
            last_name="Doe",
            role=self.user_role
        )
        self.client.force_authenticate(user=self.user)

        # Create Car Listings
        self.car_etb = CarListing.objects.create(
            title="Toyota Corolla",
            company=self.company_profile,
            brand=CarListing.CarBrandChoices.TOYOTA,
            model="Corolla",
            year=2022,
            mileage=10000,
            fuel_type=CarListing.FuelTypeChoices.PETROL,
            transmission=CarListing.TransmissionChoices.AUTOMATIC,
            base_price=Decimal("1500.00"),
            currency="ETB",
            listing_type=CarListing.ListingTypeChoices.RENT,
            rental_mode=CarListing.RentalModeChoices.WITH_DRIVER,
            with_driver_base_price=Decimal("1500.00"),
            without_driver_base_price=Decimal("1800.00"),
            car_class=CarListing.CarClassChoices.NORMAL,
            condition=CarListing.ConditionChoices.USED,
            quantity=5,
            seats=4,
            is_active=True
        )
        self.car_usd = CarListing.objects.create(
            title="Tesla Model 3",
            company=self.company_profile,
            brand=CarListing.CarBrandChoices.TOYOTA,
            model="Model 3",
            year=2023,
            mileage=5000,
            fuel_type=CarListing.FuelTypeChoices.ELECTRIC,
            transmission=CarListing.TransmissionChoices.AUTOMATIC,
            base_price=Decimal("100.00"),
            currency="USD",
            listing_type=CarListing.ListingTypeChoices.RENT,
            rental_mode=CarListing.RentalModeChoices.WITH_DRIVER,
            with_driver_base_price=Decimal("100.00"),
            without_driver_base_price=Decimal("120.00"),
            car_class=CarListing.CarClassChoices.LUXURY,
            condition=CarListing.ConditionChoices.USED,
            quantity=2,
            seats=4,
            is_active=True
        )
        CarAvailabilityService.create_availability(self.car_etb)
        CarAvailabilityService.create_availability(self.car_usd)
        TermsAndConditions.objects.create(
            content_type=ContentType.objects.get_for_model(self.company_profile),
            object_id=self.company_profile.id,
            version="1.0",
            title="Terms",
            content="Standard terms",
            effective_date=date.today(),
            is_active=True,
        )

    def test_car_listing_includes_price_quote(self):
        """Verify car detail includes price_quote field when dates provided."""
        url = reverse('cars-detail', kwargs={'pk': self.car_etb.id})
        check_in = date.today() + timedelta(days=5)
        check_out = check_in + timedelta(days=3)
        
        response = self.client.get(url, {
            'check_in': check_in.isoformat(),
            'check_out': check_out.isoformat()
        })
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('price_quote', response.data)
        quote = response.data['price_quote']
        self.assertEqual(quote['currency'], 'ETB')
        self.assertEqual(Decimal(quote['subtotal']), Decimal("4500.00")) # 1500 * 3
        self.assertEqual(Decimal(quote['platform_fee']), Decimal("225.00")) # 4500 * 0.05
        self.assertEqual(Decimal(quote['total']), Decimal("4725.00"))

    def test_car_rental_includes_platform_fee(self):
        """Verify car rental adds 5% platform fee to total_price."""
        url = reverse('carrental-list')
        start_date = date.today() + timedelta(days=1)
        end_date = start_date + timedelta(days=2)

        prior_rental = CarRental.objects.create(
            renter=self.user,
            start_date=date.today() - timedelta(days=5),
            end_date=date.today() - timedelta(days=3),
            total_price=Decimal("1500.00"),
            currency="ETB",
            status=CarRental.RentStatus.CONFIRMED,
            guest_first_name="John",
            guest_last_name="Doe",
            guest_email="customer@example.com",
            guest_phone="0911555001",
            booking_reference=f"C-{uuid.uuid4().hex[:6].upper()}",
            terms_accepted=True,
            terms_version="1.0",
            terms_content_snapshot="Standard terms",
            terms_accepted_at=timezone.now(),
        )
        CarRentalItem.objects.create(
            car_rental=prior_rental,
            car_listing=self.car_etb,
            units_rent=1,
            price_per_unit=Decimal("1500.00"),
        )
        
        # We need to accept T&C, but for this test we'll skip the actual T&C obj creation 
        # and just provide valid-looking data if the service allows or mocks it.
        # Actually, let's just minimal data.
        
        data = {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "currency": "ETB",
            "guest_phone": "0911555001",
            "rental_items": [
                {
                    "car_listing": self.car_etb.id,
                    "units_rent": 1,
                    "price_per_unit": 1500.00 # Base price for 2 days = 3000
                }
            ],
            "terms_accepted": True,
            "terms_version": "1.0"
        }
        
        # To bypass T&C validation error, we might need to create a T&C obj or the service might fail.
        # Let's see if it fails.
        response = self.client.post(url, data, format='json')
        
        if response.status_code == status.HTTP_400_BAD_REQUEST and "terms_version" in response.data:
            # Create T&C
            from apps.listing.models import TermsAndConditions
            from django.contrib.contenttypes.models import ContentType
            ct = ContentType.objects.get_for_model(self.company_profile)
            TermsAndConditions.objects.create(
                content_type=ct,
                object_id=self.company_profile.id,
                version="1.0",
                title="Terms",
                content="Standard terms",
                is_active=True
            )
            response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        rental_id = response.data['id']
        rental = CarRental.objects.get(id=rental_id)
        
        # 1500 * 2 days = 3000
        # 3000 + 5% = 3150
        self.assertEqual(rental.total_price, Decimal("3150.00"))

    def test_car_currency_validation(self):
        """Verify mixed currency prevents car rental creation."""
        url = reverse('carrental-list')
        start_date = date.today() + timedelta(days=1)
        end_date = start_date + timedelta(days=2)
        
        data = {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "guest_phone": "0911555002",
            "rental_items": [
                {"car_listing": self.car_etb.id, "units_rent": 1, "price_per_unit": 1500},
                {"car_listing": self.car_usd.id, "units_rent": 1, "price_per_unit": 100}
            ],
            "terms_accepted": True,
            "terms_version": "1.0"
        }
        
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("rental_items", response.data)
        self.assertIn("same currency", str(response.data["rental_items"]))

    def test_without_driver_requires_code_3_and_business_license(self):
        """Verify self-drive rentals enforce Code 3 and business-license requirements when configured."""
        self.car_etb.requires_code_3 = True
        self.car_etb.requires_business_license = True
        self.car_etb.pre_rental_requirements = "Provide Code 3 and business license."
        self.car_etb.save(
            update_fields=[
                "requires_code_3",
                "requires_business_license",
                "pre_rental_requirements",
                "updated_at",
            ]
        )

        url = reverse('carrental-list')
        start_date = date.today() + timedelta(days=1)
        end_date = start_date + timedelta(days=2)

        base_payload = {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "guest_phone": "0911555003",
            "rental_items": [
                {
                    "car_listing": self.car_etb.id,
                    "units_rent": 1,
                    "selected_rental_mode": CarListing.RentalModeChoices.WITHOUT_DRIVER,
                }
            ],
            "terms_accepted": True,
            "terms_version": "1.0",
            "renter_driver_license_number": "DL-12345",
        }

        response = self.client.post(url, base_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("renter_code_3_license_number", response.data)

        payload_with_code_3 = {
            **base_payload,
            "renter_code_3_license_number": "C3-12345",
        }
        response = self.client.post(url, payload_with_code_3, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("renter_business_license_number", response.data)

        valid_payload = {
            **payload_with_code_3,
            "renter_business_license_number": "BL-12345",
        }
        response = self.client.post(url, valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        rental = CarRental.objects.get(id=response.data["id"])
        self.assertEqual(rental.renter_driver_license_number, "DL-12345")
        self.assertEqual(rental.renter_code_3_license_number, "C3-12345")
        self.assertEqual(rental.renter_business_license_number, "BL-12345")
        self.assertEqual(
            rental.rental_items.first().selected_rental_mode,
            CarListing.RentalModeChoices.WITHOUT_DRIVER,
        )

    def test_car_rental_preview_uses_selected_rental_mode_price(self):
        url = reverse("carrental-price-preview")
        start_date = date.today() + timedelta(days=2)
        end_date = start_date + timedelta(days=3)

        response = self.client.post(
            url,
            {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "items": [
                    {
                        "car_listing": self.car_etb.id,
                        "units_rent": 1,
                        "selected_rental_mode": CarListing.RentalModeChoices.WITHOUT_DRIVER,
                    }
                ],
                "guest_phone": "0911555004",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        preview_item = response.data["items"][0]
        self.assertEqual(
            preview_item["selected_rental_mode"],
            CarListing.RentalModeChoices.WITHOUT_DRIVER,
        )
        self.assertEqual(Decimal(preview_item["price_per_unit"]), Decimal("1800.00"))
        self.assertEqual(Decimal(preview_item["subtotal"]), Decimal("5400.00"))
