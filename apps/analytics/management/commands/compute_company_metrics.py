from django.core.management.base import BaseCommand
from django.db import transaction
from datetime import date, timedelta
from decimal import Decimal

from apps.account.models import CompanyProfile
from apps.analytics.models import CompanyDailyMetrics
from apps.analytics import services


def _to_decimal(val):
    try:
        return Decimal(str(val))
    except Exception:
        return Decimal("0")


class Command(BaseCommand):
    help = "Compute daily company metrics for a date range and store them in CompanyDailyMetrics."

    def add_arguments(self, parser):
        parser.add_argument("--start", required=True, help="Start date YYYY-MM-DD")
        parser.add_argument("--end", required=True, help="End date YYYY-MM-DD")
        parser.add_argument(
            "--company",
            help="Company UUID to compute for (omit to process all companies)",
        )

    def handle(self, *args, **options):
        start = date.fromisoformat(options["start"])
        end = date.fromisoformat(options["end"])
        company_arg = options.get("company")

        if company_arg:
            companies = CompanyProfile.objects.filter(id=company_arg)
            if not companies.exists():
                self.stdout.write(self.style.ERROR(f"Company {company_arg} not found."))
                return
        else:
            companies = CompanyProfile.objects.all()

        current = start
        created = 0
        updated = 0

        while current <= end:
            for comp in companies:
                # use the service to compute overview for the single day
                metrics = services.compute_company_overview(str(comp.id), current, current)

                defaults = {
                    "revenue": _to_decimal(metrics.get("total_revenue", 0)),
                    "bookings_count": int(metrics.get("total_bookings", 0) or 0),
                    "confirmed_count": int(metrics.get("confirmed_bookings", 0) or 0),
                    "cancelled_count": int(metrics.get("cancellations", 0) or 0),
                    "avg_booking_value": _to_decimal(metrics.get("avg_booking_value", 0)),
                    "top_listings": metrics.get("top_listings", []),
                }

                with transaction.atomic():
                    obj, created_flag = CompanyDailyMetrics.objects.update_or_create(
                        company_id=comp.id,
                        date=current,
                        defaults=defaults,
                    )

                if created_flag:
                    created += 1
                else:
                    updated += 1

                self.stdout.write(
                    f"Processed company {comp.id} for {current}: created={created_flag}"
                )

            current = current + timedelta(days=1)

        self.stdout.write(self.style.SUCCESS(f"Done. created={created} updated={updated}"))
