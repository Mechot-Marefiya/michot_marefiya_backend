import random
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.account.enums import RoleCode
from apps.account.models import (
    CompanyProfile,
    HotelProfile,
    IndividualOwnerProfile,
    ListingImage,
    OtpChallenge,
    OwnerComplianceAgreement,
    Role,
)
from apps.core.models import Address, CurrencyRate, Facility
from apps.favorites.models import Favorite, GuestFavorite
from apps.listing.models import (
    AddonOffering,
    Amenity,
    Booking,
    BookingAddon,
    BookingItem,
    BookingItemPrice,
    BookingRating,
    CarAvailability,
    CarListing,
    CarRental,
    CarRentalExtensionRequest,
    CarRentalItem,
    CarSaleListing,
    ContactRevealRequest,
    EventSpaceAvailability,
    EventSpaceBooking,
    EventSpaceBookingItem,
    EventSpaceListing,
    GuestHouseBooking,
    GuestHouseBookingItem,
    GuestHouseInventory,
    GuestHouseProfile,
    GuestHouseRoom,
    PropertyContactRevealRequest,
    PropertyListing,
    PropertyRentalAvailability,
    PropertyRentalBooking,
    PropertySaleListing,
    RoomInventory,
    RoomListing,
    Season,
    SeasonalRate,
    StayAvailability,
    TermsAndConditions,
    Transaction,
)
from apps.notifications.models import (
    Notification,
    NotificationPreference,
    NotificationTemplate,
)
from apps.payment.models import PaymentPlatformConfig, PaymentTransaction
from apps.promotions.models import (
    PromotionCampaign,
    PromotionClick,
    PromotionImpression,
    PromotionPlacement,
)

User = get_user_model()


class Command(BaseCommand):
    help = "Seed the database with comprehensive demo data across the main business domains."

    PASSWORD = "DemoPass123!"
    DEFAULT_TERMS_VERSION = "demo-v1"

    CITY_DATA = [
        {
            "city": "Addis Ababa",
            "sub_city": "Bole",
            "state": "Addis Ababa",
            "lat": Decimal("8.980603"),
            "lng": Decimal("38.757761"),
            "area": "Airport Road",
        },
        {
            "city": "Addis Ababa",
            "sub_city": "Kazanchis",
            "state": "Addis Ababa",
            "lat": Decimal("9.022736"),
            "lng": Decimal("38.761252"),
            "area": "UNECA District",
        },
        {
            "city": "Bahir Dar",
            "sub_city": "Belay Zeleke",
            "state": "Amhara",
            "lat": Decimal("11.593640"),
            "lng": Decimal("37.390770"),
            "area": "Lake Shore",
        },
        {
            "city": "Hawassa",
            "sub_city": "Tabour",
            "state": "Sidama",
            "lat": Decimal("7.062050"),
            "lng": Decimal("38.476349"),
            "area": "Lake View",
        },
        {
            "city": "Dire Dawa",
            "sub_city": "Kezira",
            "state": "Dire Dawa",
            "lat": Decimal("9.593060"),
            "lng": Decimal("41.866111"),
            "area": "Central Market",
        },
        {
            "city": "Mekelle",
            "sub_city": "Hawelti",
            "state": "Tigray",
            "lat": Decimal("13.496667"),
            "lng": Decimal("39.475278"),
            "area": "University Axis",
        },
    ]

    HOTEL_NAMES = [
        "Holiday Addis Ababa",
        "Sheraton Addis",
        "Haile Resort",
        "Radisson Blu",
    ]

    GUEST_HOUSE_NAMES = [
        "Wubet Pension",
        "Yordanos Pension",
        "Alem Pension",
        "Taitu Pension",
    ]

    EVENT_SPACE_NAMES = [
        ("Skyline Ballroom", "conference_hall"),
        ("Taitu Meeting Loft", "meeting_room"),
        ("Unity Convention Hall", "auditorium"),
    ]

    ROOM_TYPES = [
        ("Standard Twin", Decimal("2200.00"), 26, 2, "twin"),
        ("Deluxe Queen", Decimal("3200.00"), 34, 2, "queen"),
        ("Family Suite", Decimal("5100.00"), 48, 4, "mixed"),
        ("Executive King", Decimal("6200.00"), 42, 2, "king"),
    ]

    GUEST_ROOM_TYPES = [
        ("Single Courtyard Room", Decimal("1400.00"), 18, 1, "twin"),
        ("Double Garden Room", Decimal("1900.00"), 24, 2, "double"),
        ("Family Annex Room", Decimal("2600.00"), 31, 4, "mixed"),
    ]

    CAR_CATALOG = [
        ("toyota", "Corolla", Decimal("3000.00"), "automatic", "petrol", "used"),
        ("honda", "Civic", Decimal("3200.00"), "automatic", "petrol", "used"),
        ("hyundai", "Tucson", Decimal("4000.00"), "automatic", "petrol", "used"),
        ("toyota", "Land Cruiser V8", Decimal("9000.00"), "automatic", "diesel", "used"),
        ("lexus", "LX 570", Decimal("11000.00"), "automatic", "petrol", "used"),
        ("mercedes-benz", "S-Class", Decimal("12000.00"), "automatic", "hybrid", "used"),
    ]

    SALE_CAR_CATALOG = [
        ("mercedes-benz", "S-Class", Decimal("12000000.00"), "automatic", "hybrid", "used"),
        ("range rover", "Autobiography", Decimal("15000000.00"), "automatic", "petrol", "used"),
        ("bmw", "7 Series", Decimal("11000000.00"), "automatic", "petrol", "used"),
    ]

    SALE_PROPERTY_TYPES = [
        ("house", Decimal("9500000.00")),
        ("commercial", Decimal("16500000.00")),
        ("land", Decimal("6000000.00")),
        ("villa", Decimal("24000000.00")),
    ]

    PROPERTY_RENTAL_PRESETS = [
        (
            "condo",
            "Luxury Condominium",
            Decimal("2000.00"),
            "Luxury Lane",
            "Addis Ababa",
            "Addis Ababa",
            "A modern condominium with premium amenities and city views.",
            True,
            "+251-911-123-456",
        ),
        (
            "condo",
            "Cozy Condominium",
            Decimal("1000.00"),
            "Cozy Road",
            "Adama",
            "Oromia",
            "A cozy condominium perfect for singles or couples.",
            False,
            "+251-911-234-567",
        ),
        (
            "apartment",
            "Family Apartment",
            Decimal("1500.00"),
            "Central Avenue",
            "Bahir Dar",
            "Amhara",
            "A spacious apartment for longer city stays.",
            True,
            "+251-911-345-678",
        ),
        (
            "villa",
            "Garden Villa",
            Decimal("2500.00"),
            "Garden Heights",
            "Hawassa",
            "Sidama",
            "A quiet villa with lake-city access and a private garden feel.",
            True,
            "+251-911-456-789",
        ),
    ]

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete existing demo/app data in project apps before seeding.",
        )
        parser.add_argument(
            "--seed",
            type=int,
            default=20260616,
            help="Random seed for deterministic demo data generation.",
        )
        parser.add_argument(
            "--days",
            type=int,
            default=45,
            help="How many future days of availability/inventory to seed.",
        )
        parser.add_argument(
            "--users",
            type=int,
            default=14,
            help="How many regular customer users to seed.",
        )

    def handle(self, *args, **options):
        self.random = random.Random(options["seed"])
        self.days = options["days"]
        self.today = timezone.localdate()
        self.now = timezone.now()
        self.summary = {}

        if options["clear"]:
            self.stdout.write(self.style.WARNING("Clearing existing seeded business data..."))
            self._clear_data()

        self.stdout.write(self.style.SUCCESS("Building comprehensive demo data..."))

        with transaction.atomic():
            roles = self._ensure_roles()
            admin_user = self._ensure_admin_user(roles["admin"])
            facilities = self._ensure_facilities()
            amenities = self._ensure_amenities()
            self._ensure_currency_rates()
            self._ensure_notification_templates()
            self._ensure_payment_platform_config()

            users = self._create_customer_users(options["users"], roles["user"])
            company_bundle = self._create_company_owners(roles["company"], admin_user)
            individual_bundle = self._create_individual_owners(roles["individual_owner"], admin_user)
            self._create_front_desk_users(roles["front_desk"], company_bundle)

            hotels = self._create_hotels(company_bundle, admin_user, facilities)
            rooms = self._create_room_listings(hotels, amenities)
            self._create_room_inventory(rooms)
            self._create_stay_availability(rooms)
            hotel_terms = self._ensure_terms(hotels, "hotel")
            event_spaces = self._create_event_spaces(hotels, amenities, admin_user)
            event_terms = self._ensure_terms(event_spaces, "event space")
            addons = self._create_addons(hotels)
            seasons = self._create_seasons(company_bundle, individual_bundle)
            self._create_seasonal_rates(seasons, hotels, rooms)

            guest_houses = self._create_guest_houses(company_bundle, individual_bundle, amenities, facilities, admin_user)
            guest_house_terms = self._ensure_terms(guest_houses, "guest house")
            guest_house_rooms = self._create_guest_house_rooms(guest_houses, amenities)
            self._create_guest_house_inventory(guest_house_rooms)

            cars = self._create_cars(company_bundle, individual_bundle, admin_user)
            self._create_car_availability(cars)
            car_terms = self._ensure_terms(cars, "car rental")
            car_sales = self._create_car_sale_listings(company_bundle, individual_bundle, admin_user)

            properties = self._create_rental_properties(company_bundle, individual_bundle, admin_user)
            self._create_property_rental_availability(properties)
            property_terms = self._ensure_terms(properties, "property rental")
            property_sales = self._create_property_sale_listings(company_bundle, individual_bundle, admin_user)

            hotel_bookings = self._create_hotel_bookings(users, rooms, addons, hotel_terms)
            guest_bookings = self._create_guest_house_bookings(users, guest_house_rooms, guest_house_terms)
            event_bookings = self._create_event_bookings(users, event_spaces, event_terms)
            car_rentals = self._create_car_rentals(users, cars, car_terms)
            property_bookings = self._create_property_rental_bookings(users, properties, property_terms)

            hotel_transactions = self._create_hotel_payment_records(hotel_bookings)
            guest_transactions = self._create_guest_house_payment_records(guest_bookings)
            event_transactions = self._create_event_payment_records(event_bookings)
            car_transactions = self._create_car_rental_payment_records(car_rentals)
            property_transactions = self._create_property_rental_payment_records(property_bookings)

            reveal_requests = self._create_contact_reveal_requests(users, car_sales, property_sales)
            reveal_transactions = self._create_contact_reveal_payment_records(reveal_requests)

            self._create_favorites(users, hotels, guest_houses, cars, properties, event_spaces)
            self._create_notifications(
                admin_user,
                users,
                hotel_bookings,
                guest_bookings,
                event_bookings,
                car_rentals,
                property_bookings,
                reveal_requests,
            )
            self._create_promotions(admin_user, hotels, cars, properties, event_spaces)
            self._create_sample_otps(users)
            self._finalize_summary_counts()

        summary_lines = [
            f"admin login: admin@demo.michot / {self.PASSWORD}",
            f"customer login sample: guest1@demo.michot / {self.PASSWORD}",
            f"company login sample: company1@demo.michot / {self.PASSWORD}",
            f"front desk login sample: frontdesk1@demo.michot / {self.PASSWORD}",
        ]

        self.stdout.write(self.style.SUCCESS("Demo seeding completed successfully."))
        for key, value in self.summary.items():
            self.stdout.write(f"  - {key}: {value}")
        for line in summary_lines:
            self.stdout.write(f"  - {line}")

    def _bump(self, key, amount):
        self.summary[key] = self.summary.get(key, 0) + amount

    def _clear_data(self):
        models_in_delete_order = [
            PromotionClick,
            PromotionImpression,
            PromotionPlacement,
            PromotionCampaign,
            Favorite,
            GuestFavorite,
            Notification,
            NotificationPreference,
            NotificationTemplate,
            PaymentTransaction,
            PaymentPlatformConfig,
            Transaction,
            BookingRating,
            BookingAddon,
            BookingItemPrice,
            BookingItem,
            Booking,
            EventSpaceBookingItem,
            EventSpaceBooking,
            GuestHouseBookingItem,
            GuestHouseBooking,
            CarRentalExtensionRequest,
            CarRentalItem,
            CarRental,
            PropertyRentalBooking,
            ContactRevealRequest,
            PropertyContactRevealRequest,
            TermsAndConditions,
            SeasonalRate,
            Season,
            StayAvailability,
            RoomInventory,
            EventSpaceAvailability,
            GuestHouseInventory,
            CarAvailability,
            PropertyRentalAvailability,
            AddonOffering,
            EventSpaceListing,
            RoomListing,
            GuestHouseRoom,
            GuestHouseProfile,
            PropertySaleListing,
            PropertyListing,
            CarSaleListing,
            CarListing,
            HotelProfile,
            OwnerComplianceAgreement,
            CompanyProfile,
            IndividualOwnerProfile,
            ListingImage,
            OtpChallenge,
            CurrencyRate,
            Facility,
            Amenity,
            Address,
        ]

        for model in models_in_delete_order:
            model.objects.all().delete()

        User.objects.filter(is_superuser=False).delete()

    def _ensure_roles(self):
        labels = {
            RoleCode.USER.value: "User",
            RoleCode.ADMIN.value: "Admin",
            RoleCode.COMPANY.value: "Company",
            RoleCode.INDIVIDUAL_OWNER.value: "Individual Owner",
            RoleCode.FRONT_DESK.value: "Front Desk",
        }
        roles = {}
        for code, name in labels.items():
            role, _ = Role.objects.update_or_create(code=code, defaults={"name": name})
            roles[code] = role
        self._bump("roles", len(roles))
        return roles

    def _ensure_admin_user(self, admin_role):
        user, created = User.objects.get_or_create(
            email="admin@demo.michot",
            defaults={
                "first_name": "Demo",
                "last_name": "Admin",
                "role": admin_role,
                "is_staff": True,
                "is_superuser": True,
                "phone": "0900000100",
            },
        )
        changed = False
        if user.role_id != admin_role.id:
            user.role = admin_role
            changed = True
        if not user.is_staff:
            user.is_staff = True
            changed = True
        if not user.is_superuser:
            user.is_superuser = True
            changed = True
        if created or not user.check_password(self.PASSWORD):
            user.set_password(self.PASSWORD)
            changed = True
        if changed:
            user.save()
        self._bump("admin_users", 1)
        return user

    def _ensure_facilities(self):
        facility_data = [
            ("Wi-Fi", "wifi"),
            ("Parking", "parking"),
            ("Swimming Pool", "pool"),
            ("Gym", "dumbbell"),
            ("Spa", "spa"),
            ("Restaurant", "silverware-fork-knife"),
            ("Airport Shuttle", "car-side"),
            ("Laundry", "tshirt-crew"),
            ("24h Front Desk", "desk"),
        ]
        facilities = []
        for name, icon in facility_data:
            facility, _ = Facility.objects.get_or_create(name=name, defaults={"icon": icon})
            facilities.append(facility)
        self._bump("facilities", len(facilities))
        return facilities

    def _ensure_amenities(self):
        amenity_data = [
            ("Air Conditioning", "air-conditioner"),
            ("Television", "television"),
            ("Desk", "desk"),
            ("Hot Shower", "shower"),
            ("Balcony", "balcony"),
            ("Mini Fridge", "fridge"),
            ("Coffee Set", "coffee-maker"),
            ("Workspace Wi-Fi", "wifi"),
            ("Sound System", "speaker"),
            ("Projector", "projector"),
            ("Wardrobe", "wardrobe"),
            ("Towels", "towel"),
        ]
        amenities = []
        for name, icon in amenity_data:
            amenity, _ = Amenity.objects.get_or_create(name=name, defaults={"icon": icon})
            amenities.append(amenity)
        self._bump("amenities", len(amenities))
        return amenities

    def _ensure_currency_rates(self):
        rates = [
            ("USD", "ETB", Decimal("131.250000")),
            ("EUR", "ETB", Decimal("143.870000")),
            ("GBP", "ETB", Decimal("169.220000")),
            ("ETB", "USD", Decimal("0.007619")),
        ]
        count = 0
        for base, target, rate in rates:
            CurrencyRate.objects.update_or_create(
                base=base,
                target=target,
                date=self.today,
                defaults={"rate": rate},
            )
            count += 1
        self._bump("currency_rates", count)

    def _ensure_notification_templates(self):
        templates = []
        for code, label in Notification.NotificationType.choices:
            template, _ = NotificationTemplate.objects.update_or_create(
                notification_type=code,
                defaults={
                    "title_template": f"{label} update",
                    "message_template": f"{label} notification for {{user_name}}",
                    "email_subject_template": f"[Michot] {label}",
                    "email_body_template": f"Hello {{user_name}}, this is your {label.lower()} alert.",
                    "email_html_template": f"<p>Hello {{user_name}}, this is your <strong>{label}</strong> alert.</p>",
                    "sms_template": f"{label}: {{short_ref}}",
                    "push_title_template": label,
                    "push_body_template": f"{label} recorded for {{short_ref}}",
                    "required_variables": ["user_name", "short_ref"],
                },
            )
            templates.append(template)
        self._bump("notification_templates", len(templates))
        return templates

    def _ensure_payment_platform_config(self):
        PaymentPlatformConfig.objects.exclude(name="default").update(is_active=False)
        config, _ = PaymentPlatformConfig.objects.update_or_create(
            name="default",
            defaults={
                "is_active": True,
                "default_split_type": PaymentPlatformConfig.SplitType.PERCENTAGE,
                "default_split_value": Decimal("0.0500"),
                "default_car_sale_reveal_fee": Decimal("150.00"),
                "default_property_sale_reveal_fee": Decimal("250.00"),
            },
        )
        self._bump("payment_platform_configs", 1)
        return config

    def _create_customer_users(self, count, user_role):
        users = []
        for index in range(count):
            user, created = User.objects.get_or_create(
                email=f"guest{index + 1}@demo.michot",
                defaults={
                    "first_name": f"Guest{index + 1}",
                    "last_name": "Demo",
                    "role": user_role,
                    "phone": f"0912{index + 100000:06d}",
                    "location_permission_granted": True,
                    "last_known_lat": self.CITY_DATA[index % len(self.CITY_DATA)]["lat"],
                    "last_known_lng": self.CITY_DATA[index % len(self.CITY_DATA)]["lng"],
                    "location_updated_at": self.now - timedelta(days=index % 7),
                    "phone_verified_at": self.now - timedelta(days=30),
                },
            )
            updates = []
            if user.role_id != user_role.id:
                user.role = user_role
                updates.append("role")
            if created or not user.check_password(self.PASSWORD):
                user.set_password(self.PASSWORD)
                updates.append("password")
            if updates:
                user.save()
            NotificationPreference.objects.update_or_create(
                user=user,
                defaults={
                    "email_preferences": {"bookings": True, "payments": True, "marketing": index % 2 == 0},
                    "in_app_preferences": {"bookings": True, "payments": True, "promotions": True},
                    "sms_preferences": {"bookings": True, "otp": True},
                    "push_preferences": {"bookings": True, "reveal": True},
                    "email_enabled": True,
                    "sms_enabled": index % 3 == 0,
                    "push_enabled": True,
                },
            )
            users.append(user)
        self._bump("customer_users", len(users))
        self._bump("notification_preferences", len(users))
        return users

    def _create_company_owners(self, company_role, admin_user):
        companies = []
        company_users = []
        for index, hotel_name in enumerate(self.HOTEL_NAMES, start=1):
            city = self.CITY_DATA[(index - 1) % len(self.CITY_DATA)]
            owner_user, _ = User.objects.get_or_create(
                email=f"company{index}@demo.michot",
                defaults={
                    "first_name": hotel_name.split()[0],
                    "last_name": "Hospitality",
                    "role": company_role,
                    "phone": f"0922{index + 100000:06d}",
                    "phone_verified_at": self.now - timedelta(days=60),
                },
            )
            if not owner_user.check_password(self.PASSWORD):
                owner_user.set_password(self.PASSWORD)
                owner_user.save()

            address = self._create_address(city, f"{12 + index} {city['area']} Business Center")
            company, _ = CompanyProfile.objects.update_or_create(
                user=owner_user,
                defaults={
                    "name": f"{hotel_name} PLC",
                    "phone": f"0922{index + 200000:06d}",
                    "category": CompanyProfile.CategoryChoice.HOTEL,
                    "description": f"{hotel_name} hospitality company serving {city['city']}.",
                    "address": address,
                    "status": CompanyProfile.StatusChoice.APPROVED,
                    "approved_at": self.now - timedelta(days=90 - index),
                    "approved_by": admin_user,
                    "split_type": CompanyProfile.SplitTypeChoice.PERCENTAGE,
                    "split_value": Decimal("0.0500"),
                    "split_config_active": True,
                    "chapa_subaccount_id": f"demo-subaccount-company-{index}",
                    "tin": f"1000{index:04d}",
                    "business_license_number": f"BLN-CO-{index:04d}",
                },
            )
            owner_user.company = company
            owner_user.save(update_fields=["company"])
            companies.append(company)
            company_users.append(owner_user)

        self._bump("company_users", len(company_users))
        self._bump("companies", len(companies))
        return {"companies": companies, "users": company_users}

    def _create_individual_owners(self, owner_role, admin_user):
        owners = []
        owner_users = []
        names = [("Samuel", "Bekele"), ("Helen", "Fikru"), ("Abel", "Wolde")]
        for index, (first_name, last_name) in enumerate(names, start=1):
            city = self.CITY_DATA[(index + 1) % len(self.CITY_DATA)]
            owner_user, _ = User.objects.get_or_create(
                email=f"owner{index}@demo.michot",
                defaults={
                    "first_name": first_name,
                    "last_name": last_name,
                    "role": owner_role,
                    "phone": f"0933{index + 100000:06d}",
                    "phone_verified_at": self.now - timedelta(days=45),
                },
            )
            if not owner_user.check_password(self.PASSWORD):
                owner_user.set_password(self.PASSWORD)
                owner_user.save()

            address = self._create_address(city, f"{35 + index} {city['area']} Residential Lane")
            owner, _ = IndividualOwnerProfile.objects.update_or_create(
                phone=f"0933{index + 200000:06d}",
                defaults={
                    "first_name": first_name,
                    "last_name": last_name,
                    "address": address,
                    "national_id_number": 7000000000 + index,
                    "split_type": IndividualOwnerProfile.SplitTypeChoice.PERCENTAGE,
                    "split_value": Decimal("0.0400"),
                    "split_config_active": True,
                    "chapa_subaccount_id": f"demo-subaccount-owner-{index}",
                },
            )
            owner_user.individual_owner = owner
            owner_user.save(update_fields=["individual_owner"])
            owner_users.append(owner_user)
            owners.append(owner)

            OwnerComplianceAgreement.objects.update_or_create(
                owner=owner,
                agreement_version="2026.1",
                defaults={
                    "status": OwnerComplianceAgreement.Status.SIGNED,
                    "signed_at": self.now - timedelta(days=30 - index),
                    "signed_by_admin": admin_user,
                    "note": "Seeded compliance agreement for demo owner onboarding.",
                },
            )

        self._bump("individual_owner_users", len(owner_users))
        self._bump("individual_owners", len(owners))
        self._bump("owner_compliance_agreements", len(owners))
        return {"owners": owners, "users": owner_users}

    def _create_front_desk_users(self, front_desk_role, company_bundle):
        users = []
        for index, company in enumerate(company_bundle["companies"], start=1):
            user, _ = User.objects.get_or_create(
                email=f"frontdesk{index}@demo.michot",
                defaults={
                    "first_name": "Front",
                    "last_name": f"Desk{index}",
                    "role": front_desk_role,
                    "company": company,
                    "phone": f"0944{index + 100000:06d}",
                    "phone_verified_at": self.now - timedelta(days=20),
                },
            )
            user.role = front_desk_role
            user.company = company
            if not user.check_password(self.PASSWORD):
                user.set_password(self.PASSWORD)
            user.save()
            users.append(user)
        self._bump("front_desk_users", len(users))
        return users

    def _create_hotels(self, company_bundle, admin_user, facilities):
        hotels = []
        for index, company in enumerate(company_bundle["companies"], start=1):
            city = self.CITY_DATA[(index - 1) % len(self.CITY_DATA)]
            address = self._create_address(city, f"{60 + index} {city['area']} Hotel Avenue")
            hotel_slug = self.HOTEL_NAMES[index - 1].lower().replace(" ", "").replace("-", "")
            hotel, _ = HotelProfile.objects.update_or_create(
                company=company,
                defaults={
                    "name": self.HOTEL_NAMES[index - 1],
                    "description": (
                        f"{self.HOTEL_NAMES[index - 1]} blends business-ready comfort, warm hospitality, "
                        f"and local cuisine in {city['city']}."
                    ),
                    "phone": company.phone,
                    "website": f"https://{hotel_slug}.com",
                    "address": address,
                    "is_active": True,
                    "is_verified": True,
                    "verified_at": self.now - timedelta(days=10),
                    "verified_by": admin_user,
                    "verification_note": "Seeded as verified hotel.",
                    "stars": 5 if index == 2 else 4,
                    "featured": index <= 2,
                    "latitude": city["lat"],
                    "longitude": city["lng"],
                    "formatted_address": f"{address.street_line1}, {city['sub_city']}, {city['city']}",
                },
            )
            hotel.facilities.set(self.random.sample(facilities, k=min(5, len(facilities))))
            self._attach_demo_image(hotel, f"hotel-{index}", is_primary=True)
            hotels.append(hotel)

        for front_desk_user, hotel in zip(User.objects.filter(role__code=RoleCode.FRONT_DESK.value).order_by("email"), hotels):
            content_type = ContentType.objects.get_for_model(hotel)
            front_desk_user.workspace_content_type = content_type
            front_desk_user.workspace_object_id = hotel.id
            front_desk_user.save(update_fields=["workspace_content_type", "workspace_object_id"])

        self._bump("hotels", len(hotels))
        return hotels

    def _create_room_listings(self, hotels, amenities):
        rooms = []
        for hotel in hotels:
            for index, (title, base_price, size, guests, bed_type) in enumerate(self.ROOM_TYPES, start=1):
                room, _ = RoomListing.objects.update_or_create(
                    hotel=hotel,
                    title=title,
                    defaults={
                        "description": (
                            f"{title} at {hotel.name} with city views, a calm work-friendly layout, "
                            f"and modern finishes for leisure or business stays."
                        ),
                        "base_price": base_price + Decimal(index * 150),
                        "currency": "ETB",
                        "total_units": 4 + index,
                        "number_of_guests": guests,
                        "bed_type": bed_type,
                        "room_size_sqm": size,
                        "smoking_allowed": False,
                        "children_allowed": index != 1,
                        "refundable": index % 2 == 1,
                        "address": hotel.address,
                        "is_active": True,
                        "is_verified": True,
                        "verified_at": hotel.verified_at,
                        "verified_by": hotel.verified_by,
                        "booking_forward_window_days": 90,
                        "latitude": hotel.latitude,
                        "longitude": hotel.longitude,
                        "formatted_address": hotel.formatted_address,
                    },
                )
                room.amenities.set(self.random.sample(amenities, k=min(6, len(amenities))))
                self._attach_demo_image(room, f"room-{hotel.id}-{index}", is_primary=True)
                rooms.append(room)
        self._bump("hotel_rooms", len(rooms))
        return rooms

    def _create_room_inventory(self, rooms):
        created = 0
        for room in rooms:
            for offset in range(self.days):
                RoomInventory.objects.update_or_create(
                    room_listing=room,
                    date=self.today + timedelta(days=offset),
                    defaults={
                        "price": room.base_price + Decimal((offset % 5) * 100),
                    },
                )
                created += 1
        self._bump("room_inventory_records", created)

    def _create_stay_availability(self, rooms):
        created = 0
        for room in rooms:
            for offset in range(self.days):
                StayAvailability.objects.update_or_create(
                    hotel=room.hotel,
                    room=room,
                    date=self.today + timedelta(days=offset),
                    defaults={"available_rooms": max(room.total_units - (offset % 2), 1)},
                )
                created += 1
        self._bump("stay_availability_records", created)

    def _create_event_spaces(self, hotels, amenities, admin_user):
        spaces = []
        for hotel in hotels:
            for index, (title, space_type) in enumerate(self.EVENT_SPACE_NAMES, start=1):
                address = self._create_address(
                    self._city_for_address(hotel.address.city),
                    f"{100 + index} {hotel.address.sub_city or 'Central'} Events Wing",
                )
                space, _ = EventSpaceListing.objects.update_or_create(
                    hotel=hotel,
                    title=f"{hotel.name} {title}",
                    defaults={
                        "description": f"{title} for corporate events, weddings, and private gatherings.",
                        "base_price": Decimal("12000.00") + Decimal(index * 2000),
                        "currency": "ETB",
                        "address": address,
                        "number_of_guests": 40 * index,
                        "total_units": 1 + (index // 2),
                        "space_type": space_type,
                        "floor_area_sqm": 120 * index,
                        "is_active": True,
                        "is_verified": True,
                        "verified_at": self.now - timedelta(days=7),
                        "verified_by": admin_user,
                        "booking_forward_window_days": 120,
                        "latitude": hotel.latitude,
                        "longitude": hotel.longitude,
                        "formatted_address": hotel.formatted_address,
                    },
                )
                space.amenities.set(self.random.sample(amenities, k=min(5, len(amenities))))
                self._attach_demo_image(space, f"event-space-{hotel.id}-{index}", is_primary=True)
                spaces.append(space)

                for offset in range(self.days):
                    EventSpaceAvailability.objects.update_or_create(
                        space_listing=space,
                        date=self.today + timedelta(days=offset),
                        defaults={
                            "price": space.base_price + Decimal((offset % 4) * 500),
                            "available_eventspace": max(space.total_units - (offset % 2), 1),
                        },
                    )

        self._bump("event_spaces", len(spaces))
        self._bump("event_space_availability_records", len(spaces) * self.days)
        return spaces

    def _create_addons(self, hotels):
        addon_specs = [
            ("Breakfast Buffet", "meal", Decimal("650.00"), "per_person", "food"),
            ("Airport Pickup", "transport", Decimal("1800.00"), "per_booking", "car"),
            ("Extra Bed", "amenity", Decimal("900.00"), "per_night", "bed"),
        ]
        addons = []
        for hotel in hotels:
            for order, (name, category, price, pricing_type, icon) in enumerate(addon_specs, start=1):
                addon, _ = AddonOffering.objects.update_or_create(
                    hotel=hotel,
                    name=name,
                    defaults={
                        "description": f"{name} for guests staying at {hotel.name}.",
                        "category": category,
                        "price_per_unit": price,
                        "currency": "ETB",
                        "pricing_type": pricing_type,
                        "is_active": True,
                        "max_quantity_per_booking": 5 if pricing_type != "per_booking" else 1,
                        "requires_inventory": False,
                        "daily_capacity": None,
                        "icon": icon,
                        "display_order": order,
                    },
                )
                addons.append(addon)
        self._bump("addon_offerings", len(addons))
        return addons

    def _create_seasons(self, company_bundle, individual_bundle):
        seasons = []
        company = company_bundle["companies"][0]
        owner = individual_bundle["owners"][0]
        season_data = [
            ("Peak Holiday", self.today, self.today + timedelta(days=30), company, None, "High demand city-center inventory"),
            ("Conference Window", self.today + timedelta(days=31), self.today + timedelta(days=60), company, None, "Corporate season"),
            ("Owner Festival Season", self.today, self.today + timedelta(days=25), None, owner, "Owner-managed local holiday pricing"),
        ]
        for name, start_date, end_date, company_ref, owner_ref, notes in season_data:
            season, _ = Season.objects.update_or_create(
                name=name,
                company=company_ref,
                individual_owner=owner_ref,
                defaults={
                    "start_date": start_date,
                    "end_date": end_date,
                    "recurring": False,
                    "active": True,
                    "notes": notes,
                },
            )
            seasons.append(season)
        self._bump("seasons", len(seasons))
        return seasons

    def _create_seasonal_rates(self, seasons, hotels, rooms):
        created = 0
        for season in seasons:
            if season.company:
                target_hotel = hotels[0]
                target_room = next(room for room in rooms if room.hotel_id == target_hotel.id)
                SeasonalRate.objects.update_or_create(
                    season=season,
                    hotel=target_hotel,
                    room=target_room,
                    company=season.company,
                    defaults={
                        "price_override": target_room.base_price + Decimal("750.00"),
                        "multiplier": None,
                        "priority": 10,
                        "active": True,
                        "days_of_week": [4, 5, 6],
                        "min_stay": 2,
                    },
                )
                created += 1
            if season.individual_owner:
                SeasonalRate.objects.update_or_create(
                    season=season,
                    individual_owner=season.individual_owner,
                    defaults={
                        "price_override": None,
                        "multiplier": Decimal("1.1200"),
                        "priority": 5,
                        "active": True,
                        "days_of_week": [3, 4, 5],
                        "min_stay": 1,
                    },
                )
                created += 1
        self._bump("seasonal_rates", created)

    def _create_guest_houses(self, company_bundle, individual_bundle, amenities, facilities, admin_user):
        guest_houses = []
        owners = [
            ("company", company_bundle["companies"][0]),
            ("company", company_bundle["companies"][1]),
            ("individual", individual_bundle["owners"][0]),
            ("individual", individual_bundle["owners"][1]),
        ]

        for index, (owner_kind, owner) in enumerate(owners, start=1):
            city = self.CITY_DATA[(index + 1) % len(self.CITY_DATA)]
            address = self._create_address(city, f"{140 + index} {city['area']} Guest Compound")
            defaults = {
                "title": self.GUEST_HOUSE_NAMES[index - 1],
                "description": (
                    f"{self.GUEST_HOUSE_NAMES[index - 1]} is a clean, welcoming stay in {city['city']} "
                    f"with friendly service and practical comfort for budget travelers."
                ),
                "base_price": Decimal("1000.00") + Decimal(index * 120),
                "currency": "ETB",
                "address": address,
                "phone": f"0955{index + 200000:06d}",
                "website": f"https://{self.GUEST_HOUSE_NAMES[index - 1].lower().replace(' ', '').replace('-', '')}.com",
                "rating": Decimal(f"3.{7 + (index % 3)}"),
                "is_active": True,
                "is_verified": True,
                "verified_at": self.now - timedelta(days=12),
                "verified_by": admin_user,
                "booking_forward_window_days": 60,
                "latitude": city["lat"],
                "longitude": city["lng"],
                "formatted_address": f"{address.street_line1}, {city['city']}",
            }
            if owner_kind == "company":
                guest_house, _ = GuestHouseProfile.objects.update_or_create(
                    title=self.GUEST_HOUSE_NAMES[index - 1],
                    company=owner,
                    defaults={**defaults, "individual_owner": None},
                )
            else:
                guest_house, _ = GuestHouseProfile.objects.update_or_create(
                    title=self.GUEST_HOUSE_NAMES[index - 1],
                    individual_owner=owner,
                    defaults={**defaults, "company": None},
                )

            guest_house.amenities.set(self.random.sample(amenities, k=min(5, len(amenities))))
            guest_house.facility.set(self.random.sample(facilities, k=min(4, len(facilities))))
            self._attach_demo_image(guest_house, f"guest-house-{index}", is_primary=True)
            guest_houses.append(guest_house)

        self._bump("guest_houses", len(guest_houses))
        return guest_houses

    def _create_guest_house_rooms(self, guest_houses, amenities):
        rooms = []
        for guest_house in guest_houses:
            for index, (title, price, size, guests, bed_type) in enumerate(self.GUEST_ROOM_TYPES, start=1):
                room, _ = GuestHouseRoom.objects.update_or_create(
                    guest_house=guest_house,
                    title=title,
                    defaults={
                        "description": (
                            f"{title} at {guest_house.title} with simple comfort, reliable Wi-Fi, "
                            f"and short-stay convenience."
                        ),
                        "base_price": price + Decimal(index * 100),
                        "currency": "ETB",
                        "number_of_guests": guests,
                        "total_units": 2 + index,
                        "bed_type": bed_type,
                        "room_size_sqm": size,
                        "is_active": True,
                        "is_verified": True,
                        "verified_at": guest_house.verified_at,
                        "verified_by": guest_house.verified_by,
                        "booking_forward_window_days": 60,
                        "latitude": guest_house.latitude,
                        "longitude": guest_house.longitude,
                        "formatted_address": guest_house.formatted_address,
                    },
                )
                room.amenities.set(self.random.sample(amenities, k=min(5, len(amenities))))
                self._attach_demo_image(room, f"guest-room-{guest_house.id}-{index}", is_primary=True)
                rooms.append(room)
        self._bump("guest_house_rooms", len(rooms))
        return rooms

    def _create_guest_house_inventory(self, rooms):
        created = 0
        for room in rooms:
            for offset in range(self.days):
                GuestHouseInventory.objects.update_or_create(
                    guest_house_room=room,
                    date=self.today + timedelta(days=offset),
                    defaults={
                        "available_rooms": max(room.total_units - (offset % 2), 1),
                        "price": room.base_price + Decimal((offset % 3) * 80),
                    },
                )
                created += 1
        self._bump("guest_house_inventory_records", created)

    def _create_cars(self, company_bundle, individual_bundle, admin_user):
        cars = []
        owner_refs = (
            [("company", company) for company in company_bundle["companies"][:3]]
            + [("individual", owner) for owner in individual_bundle["owners"]]
        )
        for index, owner_ref in enumerate(owner_refs, start=1):
            brand, model_name, base_price, transmission, fuel_type, condition = self.CAR_CATALOG[(index - 1) % len(self.CAR_CATALOG)]
            city = self.CITY_DATA[index % len(self.CITY_DATA)]
            defaults = {
                "title": f"{brand.title()} {model_name}",
                "description": (
                    f"Well-kept {model_name} for airport transfers, daily mobility, and comfortable city travel."
                ),
                "base_price": base_price,
                "currency": "ETB",
                "brand": brand,
                "model": model_name,
                "year": 2019 + (index % 6),
                "mileage": 18000 + (index * 6000),
                "fuel_type": fuel_type,
                "transmission": transmission,
                "listing_type": CarListing.ListingTypeChoices.RENT,
                "rental_mode": CarListing.RentalModeChoices.WITHOUT_DRIVER if index % 2 == 0 else CarListing.RentalModeChoices.WITH_DRIVER,
                "car_class": CarListing.CarClassChoices.LUXURY if index % 3 == 0 else CarListing.CarClassChoices.NORMAL,
                "condition": condition,
                "requires_code_3": index % 2 == 0,
                "requires_business_license": index % 4 == 0,
                "pre_rental_requirements": "Government ID required. Driver must present a valid license at pickup.",
                "quantity": 1 + (index % 2),
                "seats": 4 + (index % 4),
                "is_active": True,
                "is_verified": True,
                "verified_at": self.now - timedelta(days=9),
                "verified_by": admin_user,
                "booking_forward_window_days": 30,
                "latitude": city["lat"],
                "longitude": city["lng"],
                "formatted_address": f"{city['area']}, {city['city']}",
            }
            if owner_ref[0] == "company":
                car, _ = CarListing.objects.update_or_create(
                    title=f"{brand.title()} {model_name}",
                    company=owner_ref[1],
                    defaults={**defaults, "individual_owner": None},
                )
            else:
                car, _ = CarListing.objects.update_or_create(
                    title=f"{brand.title()} {model_name}",
                    individual_owner=owner_ref[1],
                    defaults={**defaults, "company": None},
                )
            self._attach_demo_image(car, f"car-{index}", is_primary=True)
            cars.append(car)

        self._bump("car_rental_listings", len(cars))
        return cars

    def _create_car_availability(self, cars):
        created = 0
        for car in cars:
            for offset in range(self.days):
                CarAvailability.objects.update_or_create(
                    car_listing=car,
                    date=self.today + timedelta(days=offset),
                    defaults={"available_units": max(car.quantity - (offset % 2), 1)},
                )
                created += 1
        self._bump("car_availability_records", created)

    def _create_car_sale_listings(self, company_bundle, individual_bundle, admin_user):
        listings = []
        owners = [
            ("company", company_bundle["companies"][2]),
            ("company", company_bundle["companies"][3]),
            ("individual", individual_bundle["owners"][0]),
        ]
        for index, owner_ref in enumerate(owners, start=1):
            brand, model_name, base_price, transmission, fuel_type, condition = self.SALE_CAR_CATALOG[index - 1]
            city = self.CITY_DATA[(index + 2) % len(self.CITY_DATA)]
            defaults = {
                "description": (
                    f"Luxury {model_name} for private sale with verified ownership records, "
                    f"clean presentation, and immediate viewing availability."
                ),
                "base_price": base_price,
                "currency": "ETB",
                "brand": brand,
                "model": model_name,
                "year": 2020 + (index - 1),
                "mileage": 12000 + (index * 7000),
                "fuel_type": fuel_type,
                "transmission": transmission,
                "condition": condition,
                "car_class": CarListing.CarClassChoices.NORMAL,
                "seats": 5,
                "seller_contact_name": f"Seller {index}",
                "seller_phone": f"0966{index + 200000:06d}",
                "seller_email": f"seller{index}@demo.michot",
                "reveal_fee": Decimal("150.00"),
                "is_active": True,
                "is_verified": True,
                "verified_at": self.now - timedelta(days=4),
                "verified_by": admin_user,
                "booking_forward_window_days": 365,
                "latitude": city["lat"],
                "longitude": city["lng"],
                "formatted_address": f"{city['area']}, {city['city']}",
            }
            title = f"{brand.title()} {model_name} for Sale"
            if owner_ref[0] == "company":
                listing, _ = CarSaleListing.objects.update_or_create(
                    title=title,
                    company=owner_ref[1],
                    defaults={**defaults, "individual_owner": None},
                )
            else:
                listing, _ = CarSaleListing.objects.update_or_create(
                    title=title,
                    individual_owner=owner_ref[1],
                    defaults={**defaults, "company": None},
                )
            self._attach_demo_image(listing, f"car-sale-{index}", is_primary=True)
            listings.append(listing)
        self._bump("car_sale_listings", len(listings))
        return listings

    def _create_rental_properties(self, company_bundle, individual_bundle, admin_user):
        properties = []
        owners = [
            ("company", company_bundle["companies"][0]),
            ("company", company_bundle["companies"][1]),
            ("individual", individual_bundle["owners"][1]),
            ("individual", individual_bundle["owners"][2]),
        ]
        for index, owner_ref in enumerate(owners, start=1):
            property_type, preset_title, price, street_name, city_name, state_name, description, furnished, _phone = self.PROPERTY_RENTAL_PRESETS[
                (index - 1) % len(self.PROPERTY_RENTAL_PRESETS)
            ]
            city = next((city for city in self.CITY_DATA if city["city"] == city_name and city["state"] == state_name), self.CITY_DATA[0])
            address = self._create_address(city, f"{200 + index} {street_name}")
            defaults = {
                "description": description,
                "base_price": price,
                "currency": "ETB",
                "address": address,
                "property_type": property_type,
                "bedrooms": 3 if property_type == "condo" else 2 + index,
                "bathrooms": 1 + (index % 2),
                "square_meters": Decimal(95 + (index * 18)),
                "is_furnished": furnished,
                "is_active": True,
                "is_verified": True,
                "verified_at": self.now - timedelta(days=8),
                "verified_by": admin_user,
                "booking_forward_window_days": 90,
                "latitude": city["lat"],
                "longitude": city["lng"],
                "formatted_address": f"{address.street_line1}, {city['city']}",
            }
            if owner_ref[0] == "company":
                property_listing, _ = PropertyListing.objects.update_or_create(
                    title=preset_title,
                    company=owner_ref[1],
                    defaults={**defaults, "individual_owner": None},
                )
            else:
                property_listing, _ = PropertyListing.objects.update_or_create(
                    title=preset_title,
                    individual_owner=owner_ref[1],
                    defaults={**defaults, "company": None},
                )
            self._attach_demo_image(property_listing, f"property-rent-{index}", is_primary=True)
            properties.append(property_listing)
        self._bump("property_rental_listings", len(properties))
        return properties

    def _create_property_rental_availability(self, properties):
        created = 0
        for property_listing in properties:
            for offset in range(self.days):
                PropertyRentalAvailability.objects.update_or_create(
                    property_listing=property_listing,
                    date=self.today + timedelta(days=offset),
                    defaults={
                        "available_units": 1,
                        "price": property_listing.base_price + Decimal((offset % 4) * 200),
                    },
                )
                created += 1
        self._bump("property_rental_availability_records", created)

    def _create_property_sale_listings(self, company_bundle, individual_bundle, admin_user):
        listings = []
        owners = [
            ("company", company_bundle["companies"][2]),
            ("individual", individual_bundle["owners"][0]),
            ("individual", individual_bundle["owners"][2]),
        ]
        for index, owner_ref in enumerate(owners, start=1):
            property_type, price = self.SALE_PROPERTY_TYPES[(index - 1) % len(self.SALE_PROPERTY_TYPES)]
            city = self.CITY_DATA[(index + 4) % len(self.CITY_DATA)]
            address = self._create_address(city, f"{260 + index} {city['area']} Ownership Block")
            defaults = {
                "description": (
                    f"Verified {property_type} listing suitable for owner-occupied living or investment purchase."
                ),
                "base_price": price,
                "currency": "ETB",
                "address": address,
                "property_type": property_type,
                "bedrooms": 0 if property_type == "land" else 3 + index,
                "bathrooms": 0 if property_type == "land" else 2 + (index % 2),
                "square_meters": Decimal(180 + (index * 70)),
                "land_size_square_meters": Decimal(300 + (index * 90)),
                "is_furnished": property_type not in {"land", "commercial"},
                "seller_contact_name": f"Property Seller {index}",
                "seller_phone": f"0977{index + 200000:06d}",
                "seller_email": f"propertyseller{index}@demo.michot",
                "reveal_fee": Decimal("250.00"),
                "is_active": True,
                "is_verified": True,
                "verified_at": self.now - timedelta(days=6),
                "verified_by": admin_user,
                "booking_forward_window_days": 365,
                "latitude": city["lat"],
                "longitude": city["lng"],
                "formatted_address": f"{address.street_line1}, {city['city']}",
            }
            title = f"{property_type.title()} Sale {index}"
            if owner_ref[0] == "company":
                listing, _ = PropertySaleListing.objects.update_or_create(
                    title=title,
                    company=owner_ref[1],
                    defaults={**defaults, "individual_owner": None},
                )
            else:
                listing, _ = PropertySaleListing.objects.update_or_create(
                    title=title,
                    individual_owner=owner_ref[1],
                    defaults={**defaults, "company": None},
                )
            self._attach_demo_image(listing, f"property-sale-{index}", is_primary=True)
            listings.append(listing)
        self._bump("property_sale_listings", len(listings))
        return listings

    def _ensure_terms(self, objects, label):
        terms_map = {}
        created = 0
        for obj in objects:
            content_type = ContentType.objects.get_for_model(obj)
            terms, was_created = TermsAndConditions.objects.update_or_create(
                content_type=content_type,
                object_id=obj.id,
                version=self.DEFAULT_TERMS_VERSION,
                defaults={
                    "title": f"{label.title()} Terms",
                    "content": (
                        f"<h1>{label.title()} Terms</h1>"
                        f"<p>These demo terms apply to {obj} and were seeded for realistic test flows.</p>"
                        "<p>Bookings are subject to availability, platform verification, and payment confirmation.</p>"
                    ),
                    "effective_date": self.today - timedelta(days=30),
                    "is_active": True,
                },
            )
            terms_map[obj.id] = terms
            if was_created:
                created += 1
        self._bump("terms_and_conditions", len(terms_map))
        return terms_map

    def _create_hotel_bookings(self, users, rooms, addons, hotel_terms):
        bookings = []
        selected_rooms = rooms[:8]
        for index, room in enumerate(selected_rooms, start=1):
            user = users[(index - 1) % len(users)]
            check_in = self.today + timedelta(days=2 + index)
            nights = 1 + (index % 3)
            check_out = check_in + timedelta(days=nights)
            units = 1 if room.total_units == 1 else min(2, room.total_units)
            status = Booking.BookingStatus.CONFIRMED if index % 4 != 0 else Booking.BookingStatus.PENDING
            term = hotel_terms[room.hotel_id]
            booking = Booking.objects.create(
                user=user,
                check_in_date=check_in,
                check_out_date=check_out,
                total_price=Decimal("0.00"),
                currency="ETB",
                status=status,
                guest_first_name=user.first_name,
                guest_last_name=user.last_name,
                guest_email=user.email,
                guest_phone=user.phone or f"0919{index + 100000:06d}",
                special_requests="Late arrival after 9 PM." if index % 2 == 0 else "High floor if available.",
                snapshot={
                    "hotel_name": room.hotel.name,
                    "room_name": room.title,
                    "city": room.address.city,
                },
                terms_accepted=True,
                terms_version=term.version,
                terms_accepted_at=self.now - timedelta(days=index),
                terms_content_snapshot=term.content,
            )
            booking_item = BookingItem.objects.create(
                booking=booking,
                room=room,
                units_booked=units,
                price_per_unit=room.base_price,
                snapshot={
                    "room_title": room.title,
                    "room_size_sqm": room.room_size_sqm,
                    "bed_type": room.bed_type,
                },
            )

            total = Decimal("0.00")
            for day_offset in range(nights):
                item_price = room.base_price + Decimal((day_offset + index) % 3 * 120)
                BookingItemPrice.objects.create(
                    booking_item=booking_item,
                    date=check_in + timedelta(days=day_offset),
                    price_per_unit=item_price,
                    units=units,
                )
                total += item_price * units

            hotel_addons = [addon for addon in addons if addon.hotel_id == room.hotel_id][:2]
            for addon in hotel_addons:
                quantity = 1 if addon.pricing_type == AddonOffering.PricingType.PER_BOOKING else units
                BookingAddon.objects.create(
                    booking_item=booking_item,
                    offering=addon,
                    name=addon.name,
                    description=addon.description,
                    category=addon.category,
                    quantity=quantity,
                    price_per_unit=addon.price_per_unit,
                    currency=addon.currency,
                )
                total += addon.price_per_unit * quantity

            booking.total_price = total
            booking.save(update_fields=["total_price", "updated_at"])

            if booking.status == Booking.BookingStatus.CONFIRMED:
                self._reduce_stay_availability(room, check_in, check_out, units)
                BookingRating.objects.create(
                    booking=booking,
                    rating=4 + (index % 2),
                    comment="Smooth check-in and clean room setup.",
                )

            Transaction.objects.create(
                booking=booking,
                provider="Chapa",
                provider_payment_id=f"txn-hotel-{booking.booking_reference.lower()}",
                amount=booking.total_price,
                currency=booking.currency,
                status=Transaction.PaymentStatus.PAID if booking.status == Booking.BookingStatus.CONFIRMED else Transaction.PaymentStatus.PENDING,
            )
            bookings.append(booking)

        self._bump("hotel_bookings", len(bookings))
        self._bump("hotel_booking_items", len(bookings))
        return bookings

    def _create_guest_house_bookings(self, users, rooms, guest_house_terms):
        bookings = []
        for index, room in enumerate(rooms[:6], start=1):
            user = users[(index + 2) % len(users)]
            start_date = self.today + timedelta(days=3 + index)
            end_date = start_date + timedelta(days=1 + (index % 3))
            days = (end_date - start_date).days
            term = guest_house_terms[room.guest_house_id]
            booking = GuestHouseBooking.objects.create(
                renter=user,
                start_date=start_date,
                end_date=end_date,
                total_price=room.base_price * days,
                currency="ETB",
                status=GuestHouseBooking.RentStatus.CONFIRMED if index % 3 else GuestHouseBooking.RentStatus.PENDING,
                guest_first_name=user.first_name,
                guest_last_name=user.last_name,
                guest_email=user.email,
                guest_phone=user.phone or f"0918{index + 100000:06d}",
                special_requests="Quiet courtyard side room.",
                snapshot={"guest_house": room.guest_house.title, "room": room.title},
                terms_accepted=True,
                terms_version=term.version,
                terms_accepted_at=self.now - timedelta(days=index),
                terms_content_snapshot=term.content,
            )
            GuestHouseBookingItem.objects.create(
                booking=booking,
                room=room,
                units_booked=1,
                price_per_unit=room.base_price,
            )
            if booking.status == GuestHouseBooking.RentStatus.CONFIRMED:
                self._reduce_guest_house_inventory(room, start_date, end_date, 1)
            bookings.append(booking)
        self._bump("guest_house_bookings", len(bookings))
        self._bump("guest_house_booking_items", len(bookings))
        return bookings

    def _create_event_bookings(self, users, spaces, event_terms):
        bookings = []
        event_types = [choice[0] for choice in EventSpaceBooking.EventType.choices if choice[0] != EventSpaceBooking.EventType.WALK_IN]
        for index, space in enumerate(spaces[:5], start=1):
            user = users[(index + 4) % len(users)]
            check_in = self.today + timedelta(days=5 + index)
            check_out = check_in + timedelta(days=1)
            term = event_terms[space.id]
            booking = EventSpaceBooking.objects.create(
                user=user,
                check_in_date=check_in,
                check_out_date=check_out,
                total_price=space.base_price,
                currency="ETB",
                status=EventSpaceBooking.BookingStatus.CONFIRMED if index % 2 else EventSpaceBooking.BookingStatus.PENDING,
                guest_first_name=user.first_name,
                guest_last_name=user.last_name,
                guest_email=user.email,
                guest_phone=user.phone or f"0917{index + 100000:06d}",
                special_requests="Need theatre seating and projector setup.",
                snapshot={"event_space": space.title, "hotel": space.hotel.name},
                event_type=event_types[index % len(event_types)],
                terms_accepted=True,
                terms_version=term.version,
                terms_accepted_at=self.now - timedelta(days=index),
                terms_content_snapshot=term.content,
            )
            EventSpaceBookingItem.objects.create(
                booking=booking,
                event_space=space,
                units_booked=1,
                price_per_unit=space.base_price,
            )
            if booking.status == EventSpaceBooking.BookingStatus.CONFIRMED:
                self._reduce_event_space_availability(space, check_in, 1)
            bookings.append(booking)
        self._bump("event_space_bookings", len(bookings))
        self._bump("event_space_booking_items", len(bookings))
        return bookings

    def _create_car_rentals(self, users, cars, car_terms):
        rentals = []
        for index, car in enumerate(cars[:5], start=1):
            user = users[(index + 6) % len(users)]
            start_date = self.today + timedelta(days=1 + index)
            end_date = start_date + timedelta(days=2 + (index % 3))
            days = (end_date - start_date).days
            unit_price = car.base_price
            term = car_terms[car.id]
            rental = CarRental.objects.create(
                renter=user,
                start_date=start_date,
                end_date=end_date,
                total_price=unit_price * days,
                currency="ETB",
                status=CarRental.RentStatus.CONFIRMED if index % 2 else CarRental.RentStatus.PENDING,
                guest_first_name=user.first_name,
                guest_last_name=user.last_name,
                guest_email=user.email,
                guest_phone=user.phone or f"0916{index + 100000:06d}",
                special_requests="Pickup near the airport branch.",
                renter_driver_license_number=f"DL-{index:04d}-2026",
                renter_code_3_license_number=f"C3-{index:04d}" if car.requires_code_3 else "",
                renter_business_license_number=f"BIZ-{index:04d}" if car.requires_business_license else "",
                snapshot={"car": car.title, "owner": self._owner_name_for_listing(car)},
                terms_accepted=True,
                terms_version=term.version,
                terms_accepted_at=self.now - timedelta(days=index),
                terms_content_snapshot=term.content,
            )
            CarRentalItem.objects.create(
                car_rental=rental,
                car_listing=car,
                units_rent=1,
                price_per_unit=unit_price,
            )
            if rental.status == CarRental.RentStatus.CONFIRMED:
                self._reduce_car_availability(car, start_date, end_date, 1)

            if index % 2 == 1:
                extra_days = 1 + (index % 2)
                CarRentalExtensionRequest.objects.create(
                    rental=rental,
                    requested_by=user,
                    original_end_date=end_date,
                    requested_end_date=end_date + timedelta(days=extra_days),
                    extra_days=extra_days,
                    amount=unit_price * extra_days,
                    currency="ETB",
                    status=CarRentalExtensionRequest.ExtensionStatus.PAID_APPLIED if rental.status == CarRental.RentStatus.CONFIRMED else CarRentalExtensionRequest.ExtensionStatus.REQUESTED,
                    tx_ref=f"EXT-CAR-{index:04d}",
                    availability_held=rental.status == CarRental.RentStatus.CONFIRMED,
                    expires_at=self.now + timedelta(hours=24),
                    applied_at=self.now - timedelta(hours=2) if rental.status == CarRental.RentStatus.CONFIRMED else None,
                    snapshot={"car_title": car.title, "base_end_date": str(end_date)},
                )
            rentals.append(rental)
        self._bump("car_rentals", len(rentals))
        self._bump("car_rental_items", len(rentals))
        return rentals

    def _create_property_rental_bookings(self, users, properties, property_terms):
        bookings = []
        for index, property_listing in enumerate(properties[:4], start=1):
            user = users[(index + 8) % len(users)]
            start_date = self.today + timedelta(days=8 + index)
            end_date = start_date + timedelta(days=3 + (index % 3))
            days = (end_date - start_date).days
            term = property_terms[property_listing.id]
            booking = PropertyRentalBooking.objects.create(
                property_listing=property_listing,
                renter=user,
                start_date=start_date,
                end_date=end_date,
                total_price=property_listing.base_price * days,
                currency="ETB",
                status=PropertyRentalBooking.RentStatus.CONFIRMED if index % 2 else PropertyRentalBooking.RentStatus.PENDING,
                guest_first_name=user.first_name,
                guest_last_name=user.last_name,
                guest_email=user.email,
                guest_phone=user.phone or f"0915{index + 100000:06d}",
                special_requests="Need early utility handover and Wi-Fi details.",
                snapshot={"property": property_listing.title, "owner": self._owner_name_for_listing(property_listing)},
                terms_accepted=True,
                terms_version=term.version,
                terms_accepted_at=self.now - timedelta(days=index),
                terms_content_snapshot=term.content,
            )
            if booking.status == PropertyRentalBooking.RentStatus.CONFIRMED:
                self._reduce_property_availability(property_listing, start_date, end_date)
            bookings.append(booking)
        self._bump("property_rental_bookings", len(bookings))
        return bookings

    def _create_hotel_payment_records(self, bookings):
        return self._create_payment_transactions_for_objects(
            bookings,
            booking_type="booking",
            owner_getter=lambda booking: booking.items.first().room.hotel.company,
            amount_getter=lambda booking: booking.total_price,
            email_label="hotel",
            include_legacy_booking=True,
        )

    def _create_guest_house_payment_records(self, bookings):
        return self._create_payment_transactions_for_objects(
            bookings,
            booking_type="guesthouse",
            owner_getter=lambda booking: booking.items.first().room.guest_house.company or booking.items.first().room.guest_house.individual_owner,
            amount_getter=lambda booking: booking.total_price,
            email_label="guesthouse",
        )

    def _create_event_payment_records(self, bookings):
        return self._create_payment_transactions_for_objects(
            bookings,
            booking_type="eventspace",
            owner_getter=lambda booking: booking.items.first().event_space.hotel.company,
            amount_getter=lambda booking: booking.total_price,
            email_label="eventspace",
        )

    def _create_car_rental_payment_records(self, rentals):
        transactions = self._create_payment_transactions_for_objects(
            rentals,
            booking_type="carrental",
            owner_getter=lambda rental: rental.rental_items.first().car_listing.company or rental.rental_items.first().car_listing.individual_owner,
            amount_getter=lambda rental: rental.total_price,
            email_label="carrental",
        )
        for index, extension in enumerate(CarRentalExtensionRequest.objects.order_by("created_at"), start=1):
            PaymentTransaction.objects.update_or_create(
                tx_ref=extension.tx_ref or f"EXTPAY-{index:04d}",
                defaults={
                    "content_type": ContentType.objects.get_for_model(extension),
                    "object_id": extension.id,
                    "booking_type": "carrental_extension",
                    "amount": extension.amount,
                    "currency": extension.currency,
                    "status": PaymentTransaction.PaymentStatus.SUCCESS if extension.status == CarRentalExtensionRequest.ExtensionStatus.PAID_APPLIED else PaymentTransaction.PaymentStatus.PENDING,
                    "payment_method": "telebirr",
                    "metadata": {"source": "seed", "extension_for": extension.rental.booking_reference},
                    "commission_rate": Decimal("0.0500"),
                    "commission_amount": (extension.amount * Decimal("0.05")).quantize(Decimal("0.01")),
                    "vendor_payout_amount": (extension.amount * Decimal("0.95")).quantize(Decimal("0.01")),
                    "payout_status": PaymentTransaction.PayoutStatus.PAID if extension.status == CarRentalExtensionRequest.ExtensionStatus.PAID_APPLIED else PaymentTransaction.PayoutStatus.PENDING,
                },
            )
        return transactions

    def _create_property_rental_payment_records(self, bookings):
        return self._create_payment_transactions_for_objects(
            bookings,
            booking_type="propertyrental",
            owner_getter=lambda booking: booking.property_listing.company or booking.property_listing.individual_owner,
            amount_getter=lambda booking: booking.total_price,
            email_label="propertyrental",
            include_tax=True,
        )

    def _create_contact_reveal_requests(self, users, car_sales, property_sales):
        requests = []
        for index, listing in enumerate(car_sales, start=1):
            user = users[(index + 1) % len(users)]
            reveal = ContactRevealRequest.objects.create(
                listing=listing,
                buyer=user,
                status=ContactRevealRequest.RevealStatus.PAID_REVEALED if index % 2 else ContactRevealRequest.RevealStatus.PAYMENT_INITIATED,
                amount=listing.reveal_fee,
                currency=listing.currency,
                buyer_note="Interested in immediate inspection.",
                buyer_phone=user.phone or f"0914{index + 100000:06d}",
                tx_ref=f"CONTACT-CAR-{index:04d}",
                expires_at=self.now + timedelta(hours=12),
                unlocked_at=self.now - timedelta(hours=1) if index % 2 else None,
                contact_snapshot={
                    "seller_contact_name": listing.seller_contact_name,
                    "seller_phone": listing.seller_phone,
                    "seller_email": listing.seller_email,
                },
            )
            requests.append(reveal)

        for index, listing in enumerate(property_sales, start=1):
            user = users[(index + 4) % len(users)]
            reveal = PropertyContactRevealRequest.objects.create(
                listing=listing,
                buyer=user,
                status=PropertyContactRevealRequest.RevealStatus.PAID_REVEALED if index % 2 else PropertyContactRevealRequest.RevealStatus.REQUESTED,
                amount=listing.reveal_fee,
                currency=listing.currency,
                buyer_note="Would like to schedule a site visit.",
                buyer_phone=user.phone or f"0913{index + 100000:06d}",
                tx_ref=f"CONTACT-PROP-{index:04d}",
                expires_at=self.now + timedelta(hours=24),
                unlocked_at=self.now - timedelta(hours=2) if index % 2 else None,
                contact_snapshot={
                    "seller_contact_name": listing.seller_contact_name,
                    "seller_phone": listing.seller_phone,
                    "seller_email": listing.seller_email,
                },
            )
            requests.append(reveal)

        self._bump("contact_reveal_requests", len(requests))
        return requests

    def _create_contact_reveal_payment_records(self, requests):
        for request in requests:
            status = (
                PaymentTransaction.PaymentStatus.SUCCESS
                if request.status in {
                    ContactRevealRequest.RevealStatus.PAID_REVEALED,
                    PropertyContactRevealRequest.RevealStatus.PAID_REVEALED,
                }
                else PaymentTransaction.PaymentStatus.PENDING
            )
            PaymentTransaction.objects.update_or_create(
                tx_ref=request.tx_ref,
                defaults={
                    "content_type": ContentType.objects.get_for_model(request),
                    "object_id": request.id,
                    "booking_type": "contact_reveal",
                    "amount": request.amount,
                    "currency": request.currency,
                    "status": status,
                    "payment_method": "chapa",
                    "metadata": {"source": "seed", "listing_title": str(request.listing)},
                    "commission_rate": Decimal("0.0000"),
                    "commission_amount": Decimal("0.00"),
                    "vendor_payout_amount": request.amount,
                    "payout_status": PaymentTransaction.PayoutStatus.NOT_APPLICABLE,
                },
            )
    def _create_payment_transactions_for_objects(
        self,
        objects,
        *,
        booking_type,
        owner_getter,
        amount_getter,
        email_label,
        include_legacy_booking=False,
        include_tax=False,
    ):
        transactions = []
        content_type_cache = {}
        for index, obj in enumerate(objects, start=1):
            model = obj.__class__
            content_type = content_type_cache.setdefault(model, ContentType.objects.get_for_model(model))
            owner = owner_getter(obj)
            amount = amount_getter(obj)
            commission_rate = Decimal("0.0500")
            commission_amount = (amount * commission_rate).quantize(Decimal("0.01"))
            vendor_payout = (amount - commission_amount).quantize(Decimal("0.01"))
            tax_amount = None
            tax_rate = None
            tax_status = None
            if include_tax:
                tax_rate = Decimal("0.1500")
                tax_amount = (amount * tax_rate).quantize(Decimal("0.01"))
                tax_status = PaymentTransaction.TaxLiabilityStatus.APPLICABLE

            tx, _ = PaymentTransaction.objects.update_or_create(
                tx_ref=f"{email_label.upper()}-PAY-{index:04d}-{getattr(obj, 'booking_reference', index)}",
                defaults={
                    "content_type": content_type,
                    "object_id": obj.id,
                    "booking_type": booking_type,
                    "booking": obj if include_legacy_booking and isinstance(obj, Booking) else None,
                    "amount": amount,
                    "currency": getattr(obj, "currency", "ETB"),
                    "status": PaymentTransaction.PaymentStatus.SUCCESS if getattr(obj, "status", "") in {"confirmed", "paid_applied"} else PaymentTransaction.PaymentStatus.PENDING,
                    "chapa_transaction_id": f"chapa-{booking_type}-{index:04d}",
                    "payment_method": "card",
                    "metadata": {"source": "seed", "booking_reference": getattr(obj, "booking_reference", "")},
                    "commission_rate": commission_rate,
                    "commission_amount": commission_amount,
                    "vendor_payout_amount": vendor_payout,
                    "tax_amount": tax_amount,
                    "tax_rate": tax_rate,
                    "tax_liability_status": tax_status,
                    "payout_status": PaymentTransaction.PayoutStatus.PAID if getattr(obj, "status", "") in {"confirmed", "paid_applied"} else PaymentTransaction.PayoutStatus.PENDING,
                    "vendor_company": owner if isinstance(owner, CompanyProfile) else None,
                    "vendor_individual": owner if isinstance(owner, IndividualOwnerProfile) else None,
                },
            )
            transactions.append(tx)

        if transactions:
            first = transactions[0]
            first.dispute_status = PaymentTransaction.DisputeStatus.OPEN
            first.dispute_note = "Seeded dispute for admin transaction-monitor demos."
            first.dispute_opened_at = self.now - timedelta(hours=8)
            first.save(update_fields=["dispute_status", "dispute_note", "dispute_opened_at", "updated_at"])

        return transactions

    def _create_favorites(self, users, hotels, guest_houses, cars, properties, event_spaces):
        listings = hotels[:2] + guest_houses[:2] + cars[:2] + properties[:2] + event_spaces[:1]
        favorites_created = 0
        for index, listing in enumerate(listings, start=1):
            user = users[index % len(users)]
            content_type = ContentType.objects.get_for_model(listing)
            Favorite.objects.update_or_create(
                user=user,
                content_type=content_type,
                object_id=str(listing.id),
                defaults={
                    "snapshot": self._favorite_snapshot(listing),
                    "snapshot_at": self.now - timedelta(days=index),
                },
            )
            GuestFavorite.objects.update_or_create(
                guest_phone=f"0999{index + 200000:06d}",
                content_type=content_type,
                object_id=str(listing.id),
                defaults={
                    "linked_user": user if index % 2 else None,
                    "snapshot": self._favorite_snapshot(listing),
                    "snapshot_at": self.now - timedelta(days=index),
                },
            )
            favorites_created += 1
        self._bump("favorites", Favorite.objects.count())
        self._bump("guest_favorites", GuestFavorite.objects.count())
        return favorites_created

    def _create_notifications(
        self,
        admin_user,
        users,
        hotel_bookings,
        guest_bookings,
        event_bookings,
        car_rentals,
        property_bookings,
        reveal_requests,
    ):
        notifications = []
        for user in users[:6]:
            notifications.append(
                Notification.objects.create(
                    user=user,
                    notification_type=Notification.NotificationType.BOOKING_CREATED,
                    title="Booking Created",
                    message=f"A new booking record was created for {user.first_name}.",
                    metadata={"source": "seed"},
                    delivered_in_app=True,
                    delivered_email=True,
                    email_sent_at=self.now - timedelta(days=1),
                    priority=Notification.Priority.MEDIUM,
                )
            )

        for booking in hotel_bookings[:3]:
            notifications.append(
                Notification.objects.create(
                    user=booking.user,
                    notification_type=Notification.NotificationType.PAYMENT_SUCCESS,
                    title="Payment Confirmed",
                    message=f"Payment confirmed for booking {booking.booking_reference}.",
                    metadata={"booking_reference": booking.booking_reference},
                    delivered_in_app=True,
                    delivered_email=True,
                    delivered_push=True,
                    email_sent_at=self.now - timedelta(hours=5),
                    push_sent_at=self.now - timedelta(hours=5),
                    priority=Notification.Priority.HIGH,
                )
            )

        notifications.append(
            Notification.objects.create(
                user=admin_user,
                notification_type=Notification.NotificationType.NEW_COMPANY_REGISTRATION,
                title="New Company Registration",
                message="New owner records are available in the demo environment.",
                metadata={"count": 4},
                delivered_in_app=True,
                priority=Notification.Priority.LOW,
            )
        )

        reveal_target = next((request for request in reveal_requests if getattr(request, "buyer", None)), None)
        if reveal_target:
            notifications.append(
                Notification.objects.create(
                    user=reveal_target.buyer,
                    notification_type=Notification.NotificationType.CONTACT_REVEAL_UNLOCKED,
                    title="Seller Contact Unlocked",
                    message=f"Contact details unlocked for {reveal_target.listing.title}.",
                    metadata={"tx_ref": reveal_target.tx_ref},
                    delivered_in_app=True,
                    delivered_email=True,
                    delivered_sms=True,
                    email_sent_at=self.now - timedelta(hours=2),
                    sms_sent_at=self.now - timedelta(hours=2),
                    priority=Notification.Priority.HIGH,
                )
            )

        self._bump("notifications", len(notifications))

    def _create_promotions(self, admin_user, hotels, cars, properties, event_spaces):
        campaign = PromotionCampaign.objects.create(
            name="Summer Discovery Push",
            advertiser=admin_user,
            status=PromotionCampaign.Status.ACTIVE,
            starts_at=self.now - timedelta(days=2),
            ends_at=self.now + timedelta(days=30),
            budget=Decimal("150000.00"),
        )
        targets = [
            (PromotionPlacement.SlotType.HOME_BANNER, hotels[0], "hotel"),
            (PromotionPlacement.SlotType.SEARCH_TOP, cars[0], "vehicle"),
            (PromotionPlacement.SlotType.FEATURED_LISTING, properties[0], "property"),
            (PromotionPlacement.SlotType.CATEGORY_BANNER, event_spaces[0], "event"),
        ]
        placements = []
        for index, (slot_type, obj, category) in enumerate(targets, start=1):
            placement = PromotionPlacement.objects.create(
                campaign=campaign,
                slot_type=slot_type,
                content_type=ContentType.objects.get_for_model(obj),
                object_id=obj.id,
                target_category=category,
                display_order=index,
                is_active=True,
            )
            placements.append(placement)
            PromotionImpression.objects.create(
                placement=placement,
                user=admin_user if index % 2 else None,
                ip_address=f"197.156.9.{10 + index}",
            )
            PromotionClick.objects.create(
                placement=placement,
                user=admin_user,
                ip_address=f"197.156.9.{20 + index}",
            )
        self._bump("promotion_campaigns", 1)
        self._bump("promotion_placements", len(placements))
        self._bump("promotion_impressions", len(placements))
        self._bump("promotion_clicks", len(placements))

    def _create_sample_otps(self, users):
        challenges = []
        for index, user in enumerate(users[:3], start=1):
            challenge = OtpChallenge.objects.create(
                user=user,
                phone=user.phone or f"0900{index + 100000:06d}",
                purpose=OtpChallenge.Purpose.LOGIN if index == 1 else OtpChallenge.Purpose.GUEST_HOTEL_BOOKING,
                code_hash=f"seeded-code-hash-{index}",
                expires_at=self.now + timedelta(minutes=5 * index),
                consumed_at=self.now - timedelta(minutes=10) if index == 1 else None,
                attempts=index - 1,
                max_attempts=5,
                sent_at=self.now - timedelta(minutes=15),
            )
            challenges.append(challenge)
        self._bump("otp_challenges", len(challenges))
        return challenges

    def _finalize_summary_counts(self):
        self.summary["listing_images"] = ListingImage.objects.count()
        self.summary["payment_transactions"] = PaymentTransaction.objects.count()
        self.summary["listing_transactions"] = Transaction.objects.count()
        self.summary["booking_ratings"] = BookingRating.objects.count()
        self.summary["car_rental_extension_requests"] = CarRentalExtensionRequest.objects.count()

    def _create_address(self, city_data, street):
        address, _ = Address.objects.get_or_create(
            street_line1=street,
            city=city_data["city"],
            defaults={
                "country": "Ethiopia",
                "sub_city": city_data["sub_city"],
                "state": city_data["state"],
                "postal_code": f"{self.random.randint(1000, 9999)}",
                "latitude": city_data["lat"],
                "longitude": city_data["lng"],
                "google_place_id": f"demo-place-{city_data['city'].lower().replace(' ', '-')}-{abs(hash(street)) % 10000}",
            },
        )
        return address

    def _city_for_address(self, city_name):
        for city in self.CITY_DATA:
            if city["city"] == city_name:
                return city
        return self.CITY_DATA[0]

    def _attach_demo_image(self, obj, slug, *, is_primary):
        content_type = ContentType.objects.get_for_model(obj)
        image_name = f"{slug}.gif"
        image = ContentFile(self._gif_bytes(), name=image_name)
        ListingImage.objects.update_or_create(
            content_type=content_type,
            object_id=obj.id,
            alt_text=f"{obj} cover image",
            defaults={"image": image, "is_primary": is_primary},
        )

    def _gif_bytes(self):
        return (
            b"GIF89a\x01\x00\x01\x00\x80\x00\x00"
            b"\x2f\x74\xa8\xff\xff\xff\x21\xf9\x04"
            b"\x01\x00\x00\x00\x00\x2c\x00\x00\x00"
            b"\x00\x01\x00\x01\x00\x00\x02\x02\x44"
            b"\x01\x00\x3b"
        )

    def _reduce_stay_availability(self, room, check_in, check_out, units):
        date_cursor = check_in
        while date_cursor < check_out:
            StayAvailability.objects.filter(
                hotel=room.hotel,
                room=room,
                date=date_cursor,
            ).update(available_rooms=max(0, room.total_units - units))
            date_cursor += timedelta(days=1)

    def _reduce_guest_house_inventory(self, room, start_date, end_date, units):
        date_cursor = start_date
        while date_cursor < end_date:
            inventory = GuestHouseInventory.objects.get(guest_house_room=room, date=date_cursor)
            inventory.available_rooms = max(inventory.available_rooms - units, 0)
            inventory.save(update_fields=["available_rooms", "updated_at"])
            date_cursor += timedelta(days=1)

    def _reduce_event_space_availability(self, space, check_in, units):
        availability = EventSpaceAvailability.objects.get(space_listing=space, date=check_in)
        availability.available_eventspace = max(availability.available_eventspace - units, 0)
        availability.save(update_fields=["available_eventspace", "updated_at"])

    def _reduce_car_availability(self, car, start_date, end_date, units):
        date_cursor = start_date
        while date_cursor < end_date:
            availability = CarAvailability.objects.get(car_listing=car, date=date_cursor)
            availability.available_units = max(availability.available_units - units, 0)
            availability.save(update_fields=["available_units", "updated_at"])
            date_cursor += timedelta(days=1)

    def _reduce_property_availability(self, property_listing, start_date, end_date):
        date_cursor = start_date
        while date_cursor < end_date:
            availability = PropertyRentalAvailability.objects.get(property_listing=property_listing, date=date_cursor)
            availability.available_units = 0
            availability.save(update_fields=["available_units", "updated_at"])
            date_cursor += timedelta(days=1)

    def _owner_name_for_listing(self, listing):
        owner = getattr(listing, "company", None) or getattr(listing, "individual_owner", None)
        return str(owner) if owner else ""

    def _favorite_snapshot(self, listing):
        return {
            "title": getattr(listing, "title", getattr(listing, "name", str(listing))),
            "price": str(getattr(listing, "base_price", "")),
            "currency": getattr(listing, "currency", "ETB"),
            "location": getattr(listing, "formatted_address", "") or getattr(getattr(listing, "address", None), "city", ""),
            "type": listing.__class__.__name__,
        }
