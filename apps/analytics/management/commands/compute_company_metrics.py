from django.core.management.base import BaseCommand
from django.db import transaction
from datetime import date, timedelta

from apps.account.models import CompanyProfile
from apps.analytics.models import AnalyticsDirtyDate, CompanyDailyMetrics
from apps.analytics import services


class Command(BaseCommand):
    help = "Compute daily company metrics for a date range and store them in CompanyDailyMetrics."

    def add_arguments(self, parser):
        parser.add_argument("--start", required=False, help="Start date YYYY-MM-DD")
        parser.add_argument("--end", required=False, help="End date YYYY-MM-DD")
        parser.add_argument(
            "--company",
            help="Company UUID to compute for (omit to process all companies)",
        )
        parser.add_argument(
            "--process-dirty",
            action="store_true",
            help="Process unprocessed AnalyticsDirtyDate rows instead of a date range",
        )

    def handle(self, *args, **options):
        process_dirty = options.get("process_dirty")

        start_raw = options.get("start")
        end_raw = options.get("end")

        start = date.fromisoformat(start_raw) if start_raw else None
        end = date.fromisoformat(end_raw) if end_raw else None
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

        if process_dirty:
            # Process unprocessed dirty date rows
            dirty_qs = AnalyticsDirtyDate.objects.filter(processed=False)
            if company_arg:
                dirty_qs = dirty_qs.filter(company_id=company_arg)
            if start:
                dirty_qs = dirty_qs.filter(date__gte=start)
            if end:
                dirty_qs = dirty_qs.filter(date__lte=end)

            for dirty in dirty_qs.order_by("company_id", "date"):
                comp_id = dirty.company_id
                dt = dirty.date

                with transaction.atomic():
                    created_flag = not CompanyDailyMetrics.objects.filter(
                        company_id=comp_id,
                        date=dt,
                    ).exists()
                    services.materialize_company_daily_metrics(comp_id, dt)
                    dirty.processed = True
                    dirty.save(update_fields=["processed", "updated_at"])

                if created_flag:
                    created += 1
                else:
                    updated += 1

                self.stdout.write(f"Processed dirty company {comp_id} for {dt}: created={created_flag}")

            self.stdout.write(self.style.SUCCESS(f"Done processing dirty rows. created={created} updated={updated}"))
            return

        # Non-dirty mode: require start and end
        if not start or not end:
            self.stdout.write(self.style.ERROR("--start and --end are required unless --process-dirty is used."))
            return

        if company_arg:
            companies = CompanyProfile.objects.filter(id=company_arg)
            if not companies.exists():
                self.stdout.write(self.style.ERROR(f"Company {company_arg} not found."))
                return
        else:
            companies = CompanyProfile.objects.all()

        current = start
        while current <= end:
            for comp in companies:
                with transaction.atomic():
                    created_flag = not CompanyDailyMetrics.objects.filter(
                        company_id=comp.id,
                        date=current,
                    ).exists()
                    services.materialize_company_daily_metrics(comp.id, current)

                if created_flag:
                    created += 1
                else:
                    updated += 1

                self.stdout.write(f"Processed company {comp.id} for {current}: created={created_flag}")

            current = current + timedelta(days=1)

        self.stdout.write(self.style.SUCCESS(f"Done. created={created} updated={updated}"))
