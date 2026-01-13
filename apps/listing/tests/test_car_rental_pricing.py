from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from apps.listing.models import CarListing, CarRental, CarRentalItem
from apps.account.models import CompanyProfile, Role, RoleCode
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
            base_price=Decimal("1500.00"),
            currency="ETB",
            listing_type=CarListing.ListingTypeChoices.RENT,
            quantity=5,
            is_active=True
        )
        self.car_usd = CarListing.objects.create(
            title="Tesla Model 3",
            company=self.company_profile,
            base_price=Decimal("100.00"),
            currency="USD",
            listing_type=CarListing.ListingTypeChoices.RENT,
            quantity=2,
            is_active=True
        )

    def test_car_listing_includes_price_quote(self):
        """Verify car detail includes price_quote field when dates provided."""
        url = reverse('carlisting-detail', kwargs={'pk': self.car_etb.id})
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
        
        # We need to accept T&C, but for this test we'll skip the actual T&C obj creation 
        # and just provide valid-looking data if the service allows or mocks it.
        # Actually, let's just minimal data.
        
        data = {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "currency": "ETB",
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

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
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
