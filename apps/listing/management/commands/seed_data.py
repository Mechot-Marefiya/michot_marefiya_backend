import random
from datetime import date, timedelta
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db import transaction, IntegrityError
from apps.account.models import (
    Role,
    CompanyProfile,
    HotelProfile,
    IndividualOwnerProfile,
    ListingImage,
)
from apps.core.models import Address, Facility
from apps.listing.models import (
    Amenity,
    CarListing,
    PropertyListing,
    GuestHouseProfile,
    GuestHouseRoom,
    GuestHouseInventory,
    RoomListing,
    StayAvailability,
    Booking,
    BookingItem,
    TermsAndConditions,
)
from apps.listing.services import StayAvailabilityService, BookingService

User = get_user_model()


class Command(BaseCommand):
    help = "Seed the database with comprehensive test data for all models."

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear existing data before seeding (WARNING: This deletes all data!)",
        )
        parser.add_argument(
            "--hotels",
            type=int,
            default=5,
            help="Number of hotels to create (default: 5)",
        )
        parser.add_argument(
            "--rooms-per-hotel",
            type=int,
            default=3,
            help="Number of room types per hotel (default: 3)",
        )
        parser.add_argument(
            "--cars",
            type=int,
            default=10,
            help="Number of cars to create (default: 10)",
        )
        parser.add_argument(
            "--properties",
            type=int,
            default=8,
            help="Number of properties to create (default: 8)",
        )
        parser.add_argument(
            "--guest-houses",
            type=int,
            default=5,
            help="Number of guest houses to create (default: 5)",
        )
        parser.add_argument(
            "--users",
            type=int,
            default=10,
            help="Number of regular users to create (default: 10)",
        )
        parser.add_argument(
            "--bookings",
            type=int,
            default=15,
            help="Number of bookings to create (default: 15)",
        )

    def handle(self, *args, **options):
        if options["clear"]:
            self.stdout.write(self.style.WARNING("Clearing existing data..."))
            self._clear_data()

        self.stdout.write(self.style.SUCCESS("Starting data seeding..."))

        with transaction.atomic():
            roles = self._ensure_roles()
            facilities = self._ensure_facilities()
            amenities = self._ensure_amenities()

            users = self._create_users(options["users"], roles)
            companies = self._create_companies(options["hotels"], roles, facilities)
            hotels = self._create_hotels(companies, facilities)
            self._ensure_terms(hotels, kind="hotel")
            rooms = self._create_rooms(hotels, amenities, options["rooms_per_hotel"])
            self._create_availability(rooms)
            bookings = self._create_bookings(users, rooms, options["bookings"])

            cars = self._create_cars(companies, options["cars"])
            properties = self._create_properties(companies, options["properties"])
            guest_houses = self._create_guest_houses(companies, amenities, options["guest_houses"])
            self._ensure_terms(guest_houses, kind="guesthouse")

        self.stdout.write(
            self.style.SUCCESS(
                f"\n✅ Seeding completed successfully!\n"
                f"   - Users: {len(users)}\n"
                f"   - Companies: {len(companies)}\n"
                f"   - Hotels: {len(hotels)}\n"
                f"   - Rooms: {len(rooms)}\n"
                f"   - Cars: {len(cars)}\n"
                f"   - Properties: {len(properties)}\n"
                f"   - Guest Houses: {len(guest_houses)}\n"
                f"   - Bookings: {len(bookings)}\n"
            )
        )

    def _clear_data(self):
        BookingItem.objects.all().delete()
        Booking.objects.all().delete()
        StayAvailability.objects.all().delete()
        RoomListing.objects.all().delete()
        GuestHouseProfile.objects.all().delete()
        GuestHouseRoom.objects.all().delete()
        GuestHouseInventory.objects.all().delete()
        PropertyListing.objects.all().delete()
        CarListing.objects.all().delete()
        HotelProfile.objects.all().delete()
        CompanyProfile.objects.all().delete()
        IndividualOwnerProfile.objects.all().delete()
        User.objects.filter(is_superuser=False).delete()
        ListingImage.objects.all().delete()
        Address.objects.all().delete()

    def _ensure_roles(self):
        roles = {}
        for code in ["user", "admin", "company"]:
            role, _ = Role.objects.get_or_create(code=code)
            if code == "user":
                role.name = "User"
            elif code == "admin":
                role.name = "Admin"
            else:
                role.name = "Company"
            role.save()
            roles[code] = role
        return roles

    def _ensure_facilities(self):
        facilities_data = [
            ("WI-FI", "mdi mdi-wifi"),
            ("Parking", "mdi mdi-parking"),
            ("Swimming Pool", "mdi mdi-pool"),
            ("Gym", "mdi mdi-dumbbell"),
            ("Restaurant", "mdi mdi-silverware-fork-knife"),
            ("Bar", "mdi mdi-glass-cocktail"),
            ("Spa", "mdi mdi-spa"),
            ("Breakfast", "mdi mdi-food"),
        ]
        facilities = []
        for name, icon in facilities_data:
            facility, _ = Facility.objects.get_or_create(name=name, defaults={"icon": icon})
            facilities.append(facility)
        return facilities

    def _ensure_amenities(self):
        amenities_data = [
            ("TV", "mdi mdi-television"),
            ("Air Conditioning", "mdi mdi-air-conditioner"),
            ("Mini Bar", "mdi mdi-fridge"),
            ("Coffee Maker", "mdi mdi-coffee-maker"),
            ("Hair Dryer", "mdi mdi-hair-dryer"),
            ("Kettle", "mdi mdi-kettle"),
            ("Wardrobe", "mdi mdi-wardrobe"),
            ("Desk", "mdi mdi-desk"),
            ("Balcony", "mdi mdi-balcony"),
            ("Safe", "mdi mdi-lock"),
            ("Iron", "mdi mdi-iron"),
            ("Shower", "mdi mdi-shower"),
            ("Bathtub", "mdi mdi-bathtub"),
            ("Phone", "mdi mdi-phone"),
            ("WI-FI", "mdi mdi-wifi"),
            ("Towels", "mdi mdi-towel"),
        ]
        amenities = []
        for name, icon in amenities_data:
            amenity, _ = Amenity.objects.get_or_create(name=name, defaults={"icon": icon})
            amenities.append(amenity)
        return amenities

    def _ensure_terms(self, objects, kind="listing"):
        created = 0
        for obj in objects:
            content_type = ContentType.objects.get_for_model(obj)
            _, was_created = TermsAndConditions.objects.get_or_create(
                content_type=content_type,
                object_id=obj.id,
                version="1.0",
                defaults={
                    "title": f"Demo {kind.title()} Terms",
                    "content": (
                        f"<p>Demo terms and conditions for {obj}.</p>"
                        "<p>These were seeded for local development.</p>"
                    ),
                    "effective_date": date.today(),
                    "is_active": True,
                },
            )
            if was_created:
                created += 1
        return created

    def _create_users(self, count, roles):
        users = []
        user_role = roles["user"]
        for i in range(count):
            email = f"user{i+1}@example.com"
            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    "first_name": f"User{i+1}",
                    "last_name": "Test",
                    "role": user_role,
                },
            )
            if created:
                user.set_password("testpass123")
                user.save()
            users.append(user)
        return users

    def _create_companies(self, count, roles, facilities):
        cities = [
            ("Addis Ababa", "Bole", "9.0054", "38.7636"),
            ("Addis Ababa", "Megenagna", "9.0123", "38.7890"),
            ("Addis Ababa", "Cazanchise", "9.0234", "38.7456"),
            ("Bahir Dar", "Central", "11.6000", "37.3833"),
            ("Hawassa", "Central", "7.0500", "38.4667"),
            ("Dire Dawa", "Central", "9.6000", "41.8500"),
            ("Mekelle", "Central", "13.4969", "39.4769"),
        ]

        companies = []
        company_role = roles["company"]

        for i in range(count):
            city, sub_city, lat, lon = random.choice(cities)
            company_name = f"Hotel Company {i+1}"
            email = f"company{i+1}@example.com"

            user, _ = User.objects.get_or_create(
                email=email,
                defaults={
                    "first_name": company_name,
                    "last_name": "Ltd",
                    "role": company_role,
                },
            )
            if not user.password:
                user.set_password("testpass123")
                user.save()

            address, _ = Address.objects.get_or_create(
                street_line1=f"{random.randint(1, 999)} Main Street",
                city=city,
                defaults={
                    "sub_city": sub_city,
                    "country": "Ethiopia",
                    "state": city,
                    "postal_code": str(random.randint(1000, 9999)),
                    "latitude": Decimal(lat),
                    "longitude": Decimal(lon),
                },
            )

            company, _ = CompanyProfile.objects.get_or_create(
                user=user,
                defaults={
                    "name": company_name,
                    "phone": f"+251{random.randint(900000000, 999999999)}",
                    "category": "hotel",
                    "description": f"Premium hospitality company in {city}",
                    "address": address,
                },
            )
            companies.append(company)
        return companies

    def _create_hotels(self, companies, facilities):
        hotel_names = [
            "Grand Addis Hotel",
            "Ethiopian Heritage Inn",
            "Blue Nile Resort",
            "Mountain View Lodge",
            "Royal Palace Hotel",
            "Sunset Paradise",
            "Golden Gate Hotel",
            "Crown Plaza Addis",
        ]

        hotels = []
        for i, company in enumerate(companies):
            hotel_name = hotel_names[i % len(hotel_names)]
            stars = random.choice([3, 4, 5])
            hotel, _ = HotelProfile.objects.get_or_create(
                company=company,
                defaults={
                    "stars": stars,
                },
            )
            hotel.facilities.set(random.sample(facilities, k=random.randint(3, 6)))
            hotels.append(hotel)
        return hotels

    def _create_rooms(self, hotels, amenities, rooms_per_hotel):
        room_types = [
            ("Standard Room", 1500, 25, 2, "twin"),
            ("Deluxe Room", 2500, 35, 2, "queen"),
            ("Executive Suite", 4500, 50, 3, "king"),
            ("Presidential Suite", 8000, 80, 4, "king"),
            ("Family Room", 3000, 40, 4, "mixed"),
            ("Single Room", 1200, 20, 1, "twin"),
        ]

        rooms = []
        for hotel in hotels:
            selected_rooms = random.sample(room_types, k=min(rooms_per_hotel, len(room_types)))
            for room_type, price, size, guests, bed_type in selected_rooms:
                address = hotel.company.address
                room, _ = RoomListing.objects.get_or_create(
                    hotel=hotel,
                    title=f"{room_type}",
                    defaults={
                        "description": f"Comfortable {room_type.lower()} with modern amenities",
                        "base_price": Decimal(price),
                        "total_units": random.randint(5, 20),
                        "number_of_guests": guests,
                        "room_size_sqm": size,
                        "bed_type": bed_type,
                        "address": address,
                        "is_active": True,
                    },
                )
                room.amenities.set(random.sample(amenities, k=random.randint(4, 8)))
                rooms.append(room)
        return rooms

    def _create_availability(self, rooms):
        today = date.today()
        # Wrap the service call in a new atomic block
        try:
            with transaction.atomic(): # <--- ADD THIS NESTED ATOMIC BLOCK
                created = StayAvailabilityService.ensure_future_availability(
                    days_ahead=180, start_date=today
                )
                self.stdout.write(
                    self.style.SUCCESS(f"Created {created} availability records.")
                )
        except IntegrityError as e:
            # The nested atomic block ensures the rollback, so catching it here
            # simply allows the outer transaction to continue without error.
            self.stdout.write(
                self.style.WARNING(
                    f"Availability seeding skipped due to IntegrityError: {e}"
                )
            )

    def _create_bookings(self, users, rooms, count):
        from apps.listing.models import StayAvailability
        
        bookings = []
        statuses = ["pending", "confirmed"]
        today = date.today()
        max_future_date = today + timedelta(days=180)
        
        attempts = 0
        max_attempts = count * 3
        
        while len(bookings) < count and attempts < max_attempts:
            attempts += 1
            try:
                user = random.choice(users)
                room = random.choice(rooms)
                
                check_in = today + timedelta(days=random.randint(1, 150))
                check_out = check_in + timedelta(days=random.randint(1, 7))
                
                if check_out > max_future_date:
                    continue
                
                hotel = room.hotel
                date_cursor = check_in
                has_availability = True
                
                while date_cursor < check_out:
                    availability = StayAvailability.objects.filter(
                        hotel=hotel,
                        room=room,
                        date=date_cursor
                    ).first()
                    
                    if not availability or availability.available_rooms < 1:
                        has_availability = False
                        break
                    date_cursor += timedelta(days=1)
                
                if not has_availability:
                    continue
                
                status = random.choice(statuses)
                units = random.randint(1, min(2, room.total_units))

                booking_data = {
                    "check_in_date": check_in,
                    "check_out_date": check_out,
                    "status": status,
                    "terms_accepted": True,
                    "terms_version": "1.0",
                    "items": [
                        {
                            "room": room,
                            "units_booked": units,
                        }
                    ],
                }

                booking = BookingService.create_booking(booking_data, user=user)
                bookings.append(booking)
            except Exception as e:
                continue

        if len(bookings) < count:
            self.stdout.write(
                self.style.WARNING(
                    f"Only created {len(bookings)} out of {count} bookings. "
                    f"Some dates may not have availability."
                )
            )
        
        return bookings

    def _create_cars(self, companies, count):
        brands = [choice[0] for choice in CarListing.CarBrandChoices.choices]
        models_map = {
            "toyota": ["Camry", "Corolla", "Land Cruiser", "RAV4", "Hilux"],
            "bmw": ["X5", "X3", "3 Series", "5 Series", "7 Series"],
            "Mercedes-Benz": ["C-Class", "E-Class", "S-Class", "GLE", "GLC"],
            "audi": ["A4", "A6", "Q5", "Q7", "A3"],
            "honda": ["Accord", "Civic", "CR-V", "Pilot"],
            "ford": ["Focus", "Fiesta", "Explorer", "Escape"],
        }

        cars = []
        for i in range(count):
            brand = random.choice(brands)
            model_list = models_map.get(brand.lower(), ["Model X", "Model Y"])
            car_model = random.choice(model_list)
            company = random.choice(companies)

            car, _ = CarListing.objects.get_or_create(
                title=f"{brand} {car_model}",
                company=company,
                defaults={
                    "description": f"Reliable {brand} {car_model} for rent",
                    "base_price": Decimal(random.randint(2000, 8000)),
                    "brand": brand,
                    "model": car_model,
                    "year": random.randint(2018, 2024),
                    "mileage": random.randint(10000, 100000),
                    "fuel_type": random.choice([c[0] for c in CarListing.FuelTypeChoices.choices]),
                    "transmission": random.choice([c[0] for c in CarListing.TransmissionChoices.choices]),
                    "condition": random.choice([c[0] for c in CarListing.ConditionChoices.choices]),
                    "is_active": True,
                },
            )
            cars.append(car)
        return cars

    def _create_properties(self, companies, count):
        property_types = [choice[0] for choice in PropertyListing.PropertyTypeChoices.choices]
        cities = ["Addis Ababa", "Bahir Dar", "Hawassa", "Dire Dawa", "Mekelle"]

        properties = []
        for i in range(count):
            prop_type = random.choice(property_types)
            city = random.choice(cities)
            company = random.choice(companies)

            address, _ = Address.objects.get_or_create(
                street_line1=f"{random.randint(1, 999)} Residential Street",
                city=city,
                defaults={
                    "sub_city": "Central",
                    "country": "Ethiopia",
                    "state": city,
                    "postal_code": str(random.randint(1000, 9999)),
                },
            )

            property_obj, _ = PropertyListing.objects.get_or_create(
                title=f"{prop_type.title()} in {city}",
                company=company,
                defaults={
                    "description": f"Beautiful {prop_type} located in {city}",
                    "base_price": Decimal(random.randint(5000, 25000)),
                    "property_type": prop_type,
                    "bedrooms": random.randint(1, 4),
                    "bathrooms": random.randint(1, 3),
                    "square_meters": Decimal(random.randint(50, 200)),
                    "is_furnished": random.choice([True, False]),
                    "address": address,
                    "is_active": True,
                },
            )
            properties.append(property_obj)
        return properties

    def _create_guest_houses(self, companies, amenities, count):
        cities = ["Addis Ababa", "Bahir Dar", "Hawassa", "Dire Dawa", "Mekelle"]
        guest_houses = []

        for i in range(count):
            city = random.choice(cities)
            company = random.choice(companies)

            address, _ = Address.objects.get_or_create(
                street_line1=f"{random.randint(1, 999)} Guest House Street",
                city=city,
                defaults={
                    "sub_city": "Central",
                    "country": "Ethiopia",
                    "state": city,
                    "postal_code": str(random.randint(1000, 9999)),
                },
            )

            guest_house, _ = GuestHouseProfile.objects.get_or_create(
                title=f"Cozy Guest House {i+1}",
                company=company,
                defaults={
                    "description": f"Comfortable guest house in {city}",
                    "base_price": Decimal(random.randint(800, 2000)),
                    "rating": Decimal(str(round(random.uniform(3.5, 5.0), 2))),
                    "address": address,
                    "is_active": True,
                },
            )
            guest_house.amenities.set(random.sample(amenities, k=random.randint(3, 6)))
            
            # Add rooms for the guesthouse
            for r_idx in range(random.randint(1, 4)):
                room, _ = GuestHouseRoom.objects.get_or_create(
                    guest_house=guest_house,
                    title=f"Room {r_idx + 1}",
                    defaults={
                        "description": "Clean and quiet room.",
                        "base_price": guest_house.base_price + Decimal(str(r_idx * 100)),
                        "total_units": random.randint(2, 5),
                        "number_of_guests": random.randint(1, 4),
                        "bed_type": random.choice(["king", "queen", "twin"]),
                        "room_size_sqm": random.randint(15, 40),
                        "currency": "ETB",
                    }
                )
                from apps.listing.services import GuestHouseAvailabilityService
                GuestHouseAvailabilityService.ensure_future_availability(start_date=date.today(), days_ahead=90)
            
            guest_houses.append(guest_house)
        return guest_houses

