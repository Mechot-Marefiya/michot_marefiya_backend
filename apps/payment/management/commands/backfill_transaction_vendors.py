"""
Management command to backfill vendor_company and vendor_individual fields.
Use this in production if the migration doesn't work automatically.

Usage:
    python manage.py backfill_transaction_vendors
    
Or in Docker:
    docker-compose exec api python manage.py backfill_transaction_vendors
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from apps.payment.models import PaymentTransaction
from apps.listing.models import Booking, BookingItem, GuestHouseBooking, EventSpaceBooking, CarRental


class Command(BaseCommand):
    help = 'Backfill vendor_company and vendor_individual fields for existing PaymentTransactions'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without making changes',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made\n'))
        
        # Get transactions without vendor info
        transactions = PaymentTransaction.objects.filter(
            vendor_company__isnull=True,
            vendor_individual__isnull=True
        )
        
        total = transactions.count()
        self.stdout.write(f'Found {total} transactions to process\n')
        
        if total == 0:
            self.stdout.write(self.style.SUCCESS('✅ All transactions already have vendor fields populated'))
            return
        
        updated = 0
        skipped = 0
        
        for tx in transactions:
            try:
                vendor_company = None
                vendor_individual = None
                
                # Hotel Bookings
                if tx.booking_type == 'booking':
                    items = BookingItem.objects.filter(booking_id=tx.object_id).select_related(
                        'room__hotel__company'
                    )
                    if items.exists():
                        item = items.first()
                        if item.room and item.room.hotel and item.room.hotel.company:
                            vendor_company = item.room.hotel.company
                
                # Guesthouse Bookings
                elif tx.booking_type == 'guesthouse':
                    from apps.listing.models import GuestHouseBookingItem
                    items = GuestHouseBookingItem.objects.filter(booking_id=tx.object_id).select_related(
                        'room__guest_house__company',
                        'room__guest_house__individual_owner'
                    )
                    if items.exists():
                        item = items.first()
                        if item.room and item.room.guest_house:
                            vendor_company = item.room.guest_house.company
                            vendor_individual = item.room.guest_house.individual_owner
                
                # Event Space Bookings
                elif tx.booking_type == 'eventspace':
                    from apps.listing.models import EventSpaceBookingItem
                    items = EventSpaceBookingItem.objects.filter(booking_id=tx.object_id).select_related(
                        'event_space__company',
                        'event_space__individual_owner'
                    )
                    if items.exists():
                        item = items.first()
                        if item.event_space:
                            vendor_company = item.event_space.company
                            vendor_individual = item.event_space.individual_owner
                
                # Car Rentals
                elif tx.booking_type == 'carrental':
                    from apps.listing.models import CarRentalItem
                    items = CarRentalItem.objects.filter(rental_id=tx.object_id).select_related(
                        'car_listing__company',
                        'car_listing__individual_owner'
                    )
                    if items.exists():
                        item = items.first()
                        if item.car_listing:
                            vendor_company = item.car_listing.company
                            vendor_individual = item.car_listing.individual_owner
                
                # Save if we found vendor
                if vendor_company or vendor_individual:
                    if not dry_run:
                        tx.vendor_company = vendor_company
                        tx.vendor_individual = vendor_individual
                        tx.save(update_fields=['vendor_company', 'vendor_individual'])
                    
                    updated += 1
                    vendor_name = vendor_company.name if vendor_company else f"Individual {vendor_individual.id}"
                    self.stdout.write(f'  ✓ {tx.tx_ref} → {vendor_name}')
                else:
                    skipped += 1
                    self.stdout.write(self.style.WARNING(f'  ⚠ {tx.tx_ref} - Could not resolve vendor'))
                    
            except Exception as e:
                skipped += 1
                self.stdout.write(self.style.ERROR(f'  ✗ {tx.tx_ref} - Error: {str(e)}'))
        
        self.stdout.write('\n' + '='*60)
        if dry_run:
            self.stdout.write(self.style.SUCCESS(f'\nDRY RUN COMPLETE'))
        else:
            self.stdout.write(self.style.SUCCESS(f'\n✅ Backfill complete!'))
        
        self.stdout.write(f'  Updated: {updated}')
        self.stdout.write(f'  Skipped: {skipped}')
        self.stdout.write(f'  Total:   {total}\n')
