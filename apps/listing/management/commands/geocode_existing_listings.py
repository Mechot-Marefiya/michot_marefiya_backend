import time

from django.core.management.base import BaseCommand, CommandError

from apps.account.models import HotelProfile
from apps.listing.models import EventSpaceListing, GuestHouseProfile, PropertyListing, PropertySaleListing, RoomListing
from apps.listing.tasks import geocode_listing_async


MODEL_MAP = {
    "hotel": HotelProfile,
    "room": RoomListing,
    "guesthouse": GuestHouseProfile,
    "property": PropertyListing,
    "event_space": EventSpaceListing,
    "property_sale": PropertySaleListing,
}


class Command(BaseCommand):
    help = "Dispatch async geocoding for existing address-bearing listings."

    def add_arguments(self, parser):
        parser.add_argument(
            "--model",
            default="all",
            choices=["all", *MODEL_MAP.keys()],
            help="Listing model to process, or all models.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=50,
            help="Number of rows to dispatch per batch.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Log which listings would be dispatched without queueing tasks.",
        )
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="Include listings that already have coordinates.",
        )

    def _iter_models(self, model_name):
        if model_name == "all":
            return MODEL_MAP.items()
        if model_name not in MODEL_MAP:
            raise CommandError(f"Unsupported model '{model_name}'.")
        return [(model_name, MODEL_MAP[model_name])]

    def _get_queryset(self, model, overwrite: bool):
        queryset = model.objects.order_by("created_at")
        if not overwrite:
            queryset = queryset.filter(latitude__isnull=True)
        if any(field.name == "address" for field in model._meta.get_fields()):
            queryset = queryset.select_related("address")
        return queryset

    def handle(self, *args, **options):
        batch_size = max(1, options["batch_size"])
        dry_run = options["dry_run"]
        overwrite = options["overwrite"]

        total_dispatched = 0
        total_skipped = 0

        for model_name, model in self._iter_models(options["model"]):
            queryset = self._get_queryset(model, overwrite=overwrite)
            total = queryset.count()
            processed = 0

            self.stdout.write(
                f"Processing {model.__name__}: {total} listing(s) queued for geocoding."
            )

            while processed < total:
                batch = list(queryset[processed:processed + batch_size])
                if not batch:
                    break

                for listing in batch:
                    address = getattr(listing, "address", None)
                    if not address:
                        total_skipped += 1
                        self.stdout.write(
                            f"Skipping {model.__name__} {listing.id}: no address relation."
                        )
                        continue

                    if dry_run:
                        self.stdout.write(
                            f"Would queue geocoding for {model.__name__} {listing.id}."
                        )
                        total_dispatched += 1
                        continue

                    geocode_listing_async.delay(
                        listing.id,
                        f"{listing._meta.app_label}.{listing._meta.model_name}",
                    )
                    total_dispatched += 1

                processed += len(batch)
                self.stdout.write(
                    f"Processed {processed} of {total} for {model.__name__}."
                )
                if processed < total:
                    time.sleep(1)

        self.stdout.write(
            self.style.SUCCESS(
                f"Dispatched {total_dispatched} geocoding task(s); skipped {total_skipped} listing(s)."
            )
        )
