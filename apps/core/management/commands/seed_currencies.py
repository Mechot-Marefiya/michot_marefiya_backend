from django.core.management.base import BaseCommand
from apps.core.services import CurrencyService

class Command(BaseCommand):
    help = 'Seeds the database with exchange rates from local JSON data'

    def handle(self, *args, **options):
        self.stdout.write("Seeding exchange rates...")
        try:
            rate_objs = CurrencyService.seed_from_local_json()
            if rate_objs:
                self.stdout.write(self.style.SUCCESS(f"Successfully seeded {len(rate_objs)} exchange rates."))
            else:
                self.stdout.write(self.style.WARNING("No rates were seeded. Check if rate_data.json exists."))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error seeding rates: {e}"))
