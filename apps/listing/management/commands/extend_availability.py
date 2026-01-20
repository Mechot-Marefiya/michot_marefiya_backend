from datetime import datetime
from django.core.management.base import BaseCommand
from apps.listing.services import StayAvailabilityService, GuestHouseAvailabilityService


class Command(BaseCommand):
    help = "Ensure stay availability extends into the future."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=180,
            help="Number of days ahead to ensure availability."
        )
        parser.add_argument(
            "--start-date",
            type=str,
            default=None,
            help="Optional start date (YYYY-MM-DD)."
        )

    def handle(self, *args, **options):
        start_date = options["start_date"]
        if start_date:
            start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
        created_hotel = StayAvailabilityService.ensure_future_availability(
            days_ahead=options["days"],
            start_date=start_date
        )
        created_gh = GuestHouseAvailabilityService.ensure_future_availability(
            days_ahead=options["days"],
            start_date=start_date
        )
        self.stdout.write(
            self.style.SUCCESS(f"Created {created_hotel} hotel and {created_gh} guesthouse availability rows.")
        )

