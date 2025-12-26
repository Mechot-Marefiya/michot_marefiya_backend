import json
import re
import sys
from pathlib import Path
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from apps.account.models import (
    User, 
    Role, 
    CompanyProfile, 
    HotelProfile,
    Address
)
from apps.account.enums import RoleCode
from apps.listing.models import (
    RoomListing,
    Amenity,
    Facility
)
from apps.core.models import Facility as CoreFacility


class Command(BaseCommand):
    help = 'Import hotel data from JSON configuration file'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be created without actually creating records'
        )
        parser.add_argument(
            '--skip-existing',
            action='store_true',
            help='Skip hotels that already exist (based on business name)'
        )
        parser.add_argument(
            '--force-update',
            action='store_true',
            help='Update existing hotels instead of skipping them'
        )
        parser.add_argument(
            '--json-file',
            type=str,
            help='Path to JSON file (default: hotels_data.json in project root)',
            default=None
        )
        parser.add_argument(
            '--hotels',
            type=str,
            help='Comma-separated list of hotel names to import (or "all" for all)',
            default='all'
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed information about each step'
        )

    def handle(self, *args, **options):
        self.dry_run = options['dry_run']
        self.skip_existing = options['skip_existing']
        self.force_update = options['force_update']
        self.verbose = options['verbose']
        hotels_filter = options['hotels']
        
        # Determine JSON file path
        if options['json_file']:
            json_path = Path(options['json_file'])
        else:
            # Default to project root
            json_path = self.get_project_root() / 'hotels_data.json'
        
        if not json_path.exists():
            self.stdout.write(self.style.ERROR(f"JSON file not found: {json_path}"))
            self.stdout.write("Please create hotels_data.json in your project root")
            sys.exit(1)
        
        # Load hotel data
        try:
            hotel_data = self.load_hotel_data(json_path)
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error loading JSON: {str(e)}"))
            sys.exit(1)
        
        # Filter hotels if needed
        if hotels_filter != 'all':
            hotel_names = [name.strip() for name in hotels_filter.split(',')]
            hotels_to_import = [
                h for h in hotel_data 
                if h['business_name'] in hotel_names or h.get('display_name', '') in hotel_names
            ]
        else:
            hotels_to_import = hotel_data
        
        self.stdout.write(f"Loaded {len(hotels_to_import)} hotels from {json_path}")
        
        # Ensure required roles exist
        self.ensure_roles()
        
        # Process each hotel
        results = {
            'successful': 0,
            'updated': 0,
            'skipped': 0,
            'failed': 0
        }
        
        for hotel_data in hotels_to_import:
            try:
                result = self.process_hotel(hotel_data)
                results[result] += 1
            except Exception as e:
                self.stdout.write(self.style.ERROR(
                    f"Error processing {hotel_data.get('business_name')}: {str(e)}"
                ))
                results['failed'] += 1
        
        # Print summary
        self.print_summary(results, len(hotels_to_import))
    
    def get_project_root(self):
        """Get the project root directory (where manage.py is)"""
        # Go up from the management command directory
        current_dir = Path(__file__).parent
        # Go up: commands -> management -> listing -> apps -> project root
        project_root = current_dir.parent.parent.parent.parent
        return project_root
    
    def load_hotel_data(self, json_path):
        """Load and validate hotel data from JSON file"""
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Validate structure
        if 'hotels' not in data:
            raise ValueError("JSON must contain 'hotels' array")
        
        hotels = data['hotels']
        
        # Basic validation
        required_fields = ['business_name', 'type_of_property', 'address']
        for hotel in hotels:
            for field in required_fields:
                if field not in hotel:
                    raise ValueError(f"Hotel missing required field: {field}")
            
            # Set defaults
            hotel.setdefault('display_name', hotel['business_name'].title())
            hotel.setdefault('amenities', [])
            hotel.setdefault('room_types', {})
            hotel.setdefault('prices', {})
            hotel.setdefault('total_rooms', 0)
            
            # Clean phone numbers
            if 'contact_phone' in hotel:
                hotel['contact_phone'] = self.clean_phone(hotel['contact_phone'])
            if 'safety' in hotel and 'emergency_phone' in hotel['safety']:
                hotel['safety']['emergency_phone'] = self.clean_phone(
                    hotel['safety']['emergency_phone']
                )
        
        return hotels
    
    def ensure_roles(self):
        """Ensure required roles exist in the database"""
        roles_to_create = [
            {'name': 'Company', 'code': RoleCode.COMPANY.value},
            {'name': 'Admin', 'code': RoleCode.ADMIN.value},
        ]
        
        for role_data in roles_to_create:
            Role.objects.get_or_create(
                code=role_data['code'],
                defaults={'name': role_data['name']}
            )
    
    def process_hotel(self, hotel_data):
        """Process a single hotel"""
        business_name = hotel_data['business_name']
        display_name = hotel_data.get('display_name', business_name)
        
        if self.verbose:
            self.stdout.write(f"\n{'='*60}")
            self.stdout.write(f"Processing: {display_name}")
            self.stdout.write(f"{'='*60}")
        
        # Check if this is a hotel (not guesthouse)
        property_type = hotel_data.get('type_of_property', '').lower()
        if 'guest' in property_type:
            if self.verbose:
                self.stdout.write(self.style.WARNING(f"  Skipping guesthouse: {display_name}"))
            return 'skipped'
        
        # Check if hotel already exists
        existing_company = CompanyProfile.objects.filter(
            name__iexact=business_name
        ).first()
        
        if existing_company:
            if self.skip_existing and not self.force_update:
                if self.verbose:
                    self.stdout.write(self.style.WARNING(f"  Already exists, skipping: {display_name}"))
                return 'skipped'
            elif self.force_update:
                if self.verbose:
                    self.stdout.write(self.style.WARNING(f"  Already exists, updating: {display_name}"))
                return self.update_hotel(existing_company, hotel_data)
            else:
                if self.verbose:
                    self.stdout.write(self.style.WARNING(f"  Already exists: {display_name}"))
                return 'skipped'
        
        # Create new hotel
        if self.dry_run:
            self.stdout.write(self.style.SUCCESS(f"  Would create hotel: {display_name}"))
            return 'successful'
        else:
            with transaction.atomic():
                hotel = self.create_hotel(hotel_data)
                if self.verbose:
                    self.stdout.write(self.style.SUCCESS(
                        f"  Created: {hotel.company.name} "
                        f"(ID: {hotel.id}, Rooms: {hotel.room_listings.count()})"
                    ))
            return 'successful'
    
    @transaction.atomic
    def create_hotel(self, hotel_data):
        """Create a new hotel with all related records"""
        
        # 1. Create user
        email = hotel_data['email']
        owner_name = hotel_data.get('owner_manager', '')
        first_name = owner_name.split()[0] if owner_name else 'Hotel'
        last_name = ' '.join(owner_name.split()[1:]) if owner_name and len(owner_name.split()) > 1 else 'Owner'
        
        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                'first_name': first_name[:150],
                'last_name': last_name[:150],
                'is_active': True,
            }
        )
        
        if created:
            user.set_password('TempPassword123!')
            user.save()
        
        # 2. Set company role
        company_role = Role.objects.get(code=RoleCode.COMPANY.value)
        user.role = company_role
        user.save()
        
        # 3. Create address
        address_data = hotel_data['address']
        address = Address.objects.create(**address_data)
        
        # 4. Create company profile
        company = CompanyProfile.objects.create(
            user=user,
            address=address,
            name=hotel_data['business_name'],
            phone=hotel_data.get('contact_phone', '251000000000'),
            category='hotel',
            description=self.generate_company_description(hotel_data),
            status=CompanyProfile.StatusChoice.APPROVED,
            approved_at=timezone.now(),
            tin=hotel_data.get('tin'),
            business_license_number=hotel_data.get('business_license_number'),
        )
        
        # 5. Create hotel profile
        stars = self.determine_stars(hotel_data)
        
        hotel = HotelProfile.objects.create(
            company=company,
            stars=stars,
            featured=self.should_feature_hotel(hotel_data, stars)
        )
        
        # 6. Add facilities
        self.add_facilities(hotel, hotel_data)
        
        # 7. Create room listings
        self.create_rooms(hotel, hotel_data)
        
        return hotel
    
    @transaction.atomic
    def update_hotel(self, existing_company, hotel_data):
        """Update an existing hotel"""
        # For simplicity, we'll just log that update would happen
        # In a real implementation, you would update the hotel details
        self.stdout.write(self.style.WARNING(
            f"  Update functionality not implemented for {hotel_data['business_name']}"
        ))
        return 'skipped'
    
    def generate_company_description(self, hotel_data):
        """Generate a description for the company"""
        description_parts = []
        
        # Basic info
        description_parts.append(f"{hotel_data.get('display_name', hotel_data['business_name'])}")
        
        # Owner info
        if hotel_data.get('owner_manager'):
            description_parts.append(f"Managed by: {hotel_data['owner_manager']}")
        
        # Room info
        total_rooms = hotel_data.get('total_rooms', 0)
        if total_rooms:
            description_parts.append(f"Total rooms: {total_rooms}")
        
        # Facilities info
        amenities_count = len(hotel_data.get('amenities', []))
        if amenities_count:
            description_parts.append(f"Amenities: {amenities_count} included")
        
        # Add metadata note if exists
        if hotel_data.get('metadata', {}).get('notes'):
            description_parts.append(f"Note: {hotel_data['metadata']['notes']}")
        
        return ". ".join(description_parts) + "."
    
    def determine_stars(self, hotel_data):
        """Determine hotel stars based on amenities and inferred facilities"""
        amenities = hotel_data.get('amenities', [])
        
        # Extract facilities from amenities and metadata
        facilities = []
        facility_keywords = ['restaurant', 'gym', 'spa', 'laundry', 'conference', 'business', 'bar']
        
        for amenity in amenities:
            for keyword in facility_keywords:
                if keyword in amenity:
                    facilities.append(keyword)
        
        score = 0
        
        # Basic amenities (1 point each)
        basic_amenities = ['private_bathroom', 'wifi', 'television']
        for amenity in basic_amenities:
            if amenity in amenities:
                score += 1
        
        # Premium amenities (2 points each)
        premium_amenities = ['air_conditioning', 'heating', 'mini_fridge', 'safe_box', 'balcony']
        for amenity in premium_amenities:
            if amenity in amenities:
                score += 2
        
        # Service amenities (1 point each)
        service_amenities = ['daily_housekeeping', 'towels_toiletries']
        for amenity in service_amenities:
            if amenity in amenities:
                score += 1
        
        # Facilities (2 points each)
        score += len(facilities) * 2
        
        # Size bonus
        total_rooms = hotel_data.get('total_rooms', 0)
        if total_rooms > 50:
            score += 2
        elif total_rooms > 20:
            score += 1
        
        # Convert score to stars (1-5)
        if score >= 20:
            return 5
        elif score >= 15:
            return 4
        elif score >= 10:
            return 3
        elif score >= 5:
            return 2
        else:
            return 1
    
    def should_feature_hotel(self, hotel_data, stars):
        """Determine if hotel should be featured"""
        # Feature 4+ star hotels or hotels with special facilities
        if stars >= 4:
            return True
        
        # Check for premium facilities
        premium_facilities = ['spa', 'gym', 'conference_room']
        amenities = hotel_data.get('amenities', [])
        for facility in premium_facilities:
            if facility in amenities:
                return True
        
        return False
    
    def add_facilities(self, hotel, hotel_data):
        """Add facilities to hotel"""
        facilities_map = {
            'restaurant': ('Restaurant', 'fa-utensils'),
            'parking': ('Parking', 'fa-parking'),
            'gym': ('Gym', 'fa-dumbbell'),
            'spa': ('Spa', 'fa-spa'),
            'laundry': ('Laundry Service', 'fa-tshirt'),
            'conference_room': ('Conference Room', 'fa-chalkboard'),
            'business_center': ('Business Center', 'fa-briefcase'),
            'concierge': ('Concierge Service', 'fa-concierge-bell'),
            'bar': ('Bar', 'fa-glass-martini'),
        }
        
        amenities = hotel_data.get('amenities', [])
        
        for amenity_key, (facility_name, facility_icon) in facilities_map.items():
            if amenity_key in amenities:
                facility, created = CoreFacility.objects.get_or_create(
                    name=facility_name,
                    defaults={'icon': facility_icon}
                )
                hotel.facilities.add(facility)
    
    def create_rooms(self, hotel, hotel_data):
        """Create room listings for the hotel"""
        
        # Standard room configurations
        room_configs = {
            'single': {'bed_type': RoomListing.BedType.DOUBLE, 'guests': 1, 'size': 20},
            'double': {'bed_type': RoomListing.BedType.DOUBLE, 'guests': 2, 'size': 25},
            'twin': {'bed_type': RoomListing.BedType.TWIN, 'guests': 2, 'size': 25},
            'family': {'bed_type': RoomListing.BedType.MIXED, 'guests': 4, 'size': 35},
            'suite': {'bed_type': RoomListing.BedType.KING, 'guests': 2, 'size': 40},
            'semi_standard': {'bed_type': RoomListing.BedType.DOUBLE, 'guests': 2, 'size': 22},
            'semi_standard_up_scale': {'bed_type': RoomListing.BedType.DOUBLE, 'guests': 2, 'size': 26},
            'standard': {'bed_type': RoomListing.BedType.DOUBLE, 'guests': 2, 'size': 28},
            'suit': {'bed_type': RoomListing.BedType.KING, 'guests': 2, 'size': 38},
            'semi_suit': {'bed_type': RoomListing.BedType.KING, 'guests': 2, 'size': 35},
            'suit_twin': {'bed_type': RoomListing.BedType.TWIN, 'guests': 2, 'size': 38},
            'executive': {'bed_type': RoomListing.BedType.KING, 'guests': 2, 'size': 45},
        }
        
        room_types = hotel_data.get('room_types', {})
        prices = hotel_data.get('prices', {})
        
        for room_type, count in room_types.items():
            if count <= 0:
                continue
            
            # Get configuration
            config = room_configs.get(room_type, room_configs['single'])
            
            # Get price
            price_info = prices.get(room_type, {})
            base_price = self.calculate_base_price(price_info)
            
            # Create room listing
            room_title = f"{room_type.replace('_', ' ').title()} Room"
            
            room = RoomListing.objects.create(
                hotel=hotel,
                address=hotel.company.address,
                title=room_title,
                description=self.generate_room_description(room_type, hotel_data),
                base_price=base_price,
                currency=("ETB" if price_info.get('currency') == 'USD' else price_info.get('currency', 'ETB')),
                number_of_guests=config['guests'],
                total_units=count,
                bed_type=config['bed_type'],
                room_size_sqm=config['size'],
                smoking_allowed=False,
                children_allowed=True,
                refundable=True,
            )
            
            # Add amenities to room
            self.add_room_amenities(room, hotel_data.get('amenities', []))
    
    def calculate_base_price(self, price_info):
        """Calculate base price from price info"""
        min_price = price_info.get('min', 0)
        max_price = price_info.get('max', 0)
        
        # Use average if both min and max are available
        if min_price and max_price:
            base_price = (Decimal(str(min_price)) + Decimal(str(max_price))) / 2
        elif min_price:
            base_price = Decimal(str(min_price))
        elif max_price:
            base_price = Decimal(str(max_price))
        else:
            base_price = Decimal('50.00')  # Default
        
        # Convert USD to ETB if needed (simplified conversion)
        if price_info.get('currency') == 'USD':
            base_price = base_price * Decimal('55.00')
        
        return base_price
    
    def generate_room_description(self, room_type, hotel_data):
        """Generate description for a room"""
        hotel_name = hotel_data.get('display_name', hotel_data['business_name'])
        
        descriptions = {
            'single': f"Comfortable single room at {hotel_name}, perfect for solo travelers with all essential amenities.",
            'double': f"Spacious double room at {hotel_name} featuring a comfortable double bed and modern furnishings.",
            'twin': f"Twin room at {hotel_name} with two separate beds, ideal for friends, colleagues, or family members.",
            'family': f"Family room at {hotel_name} offering ample space and comfort for the whole family's stay.",
            'suite': f"Luxurious suite at {hotel_name} with premium amenities, extra space, and enhanced comfort.",
            'standard': f"Standard room at {hotel_name} providing all essential amenities for a comfortable stay.",
            'executive': f"Executive room at {hotel_name} designed for business travelers with premium features and workspace.",
        }
        
        default_desc = f"Comfortable {room_type.replace('_', ' ')} room at {hotel_name} with all necessary amenities."
        
        return descriptions.get(room_type, default_desc)
    
    def add_room_amenities(self, room, amenities):
        """Add amenities to a room listing"""
        
        amenity_map = {
            'air_conditioning': ('Air Conditioning', 'fa-snowflake'),
            'heating': ('Heating', 'fa-thermometer-half'),
            'television': ('Television', 'fa-tv'),
            'mini_fridge': ('Mini Fridge', 'fa-icebox'),
            'telephone': ('Telephone', 'fa-phone'),
            'safe_box': ('Safe Box', 'fa-lock'),
            'closet': ('Closet', 'fa-archive'),
            'private_bathroom': ('Private Bathroom', 'fa-bath'),
            'balcony': ('Balcony', 'fa-umbrella-beach'),
            'shower': ('Shower', 'fa-shower'),
            'wifi': ('WiFi', 'fa-wifi'),
            'room_key_card': ('Electronic Key Card', 'fa-key'),
            'daily_housekeeping': ('Daily Housekeeping', 'fa-broom'),
            'towels_toiletries': ('Towels & Toiletries', 'fa-toilet-paper'),
        }
        
        for amenity_key in amenities:
            if amenity_key in amenity_map:
                amenity_name, amenity_icon = amenity_map[amenity_key]
                amenity, created = Amenity.objects.get_or_create(
                    name=amenity_name,
                    defaults={'icon': amenity_icon}
                )
                room.amenities.add(amenity)
    
    def clean_phone(self, phone):
        """Clean phone number"""
        if not phone or not isinstance(phone, (str, int, float)):
            return None
        
        phone_str = str(phone).strip()
        
        # Remove non-numeric characters except +
        phone_str = re.sub(r'[^\d+]', '', phone_str)
        
        # Add country code if missing
        if phone_str and not phone_str.startswith('+') and len(phone_str) < 10:
            # Assume Ethiopian number
            if phone_str.startswith('0'):
                phone_str = '+251' + phone_str[1:]
            elif len(phone_str) == 9:
                phone_str = '+251' + phone_str
        
        return phone_str if phone_str else None
    
    def print_summary(self, results, total_hotels):
        """Print import summary"""
        self.stdout.write("\n" + "="*60)
        self.stdout.write("IMPORT SUMMARY")
        self.stdout.write("="*60)
        
        self.stdout.write(f"Total hotels in JSON: {total_hotels}")
        self.stdout.write(f"Successfully created: {results['successful']}")
        self.stdout.write(f"Updated: {results['updated']}")
        self.stdout.write(f"Skipped: {results['skipped']}")
        self.stdout.write(f"Failed: {results['failed']}")
        
        if self.dry_run:
            self.stdout.write(self.style.WARNING("\nDRY RUN - No changes were made to the database"))
        
        # Show created hotels if not verbose
        if results['successful'] > 0 and not self.verbose:
            self.stdout.write("\nCreated hotels:")
            hotels = HotelProfile.objects.order_by('-created_at')[:results['successful']]
            for hotel in hotels:
                self.stdout.write(f"  • {hotel.company.name} ({hotel.stars}★)")