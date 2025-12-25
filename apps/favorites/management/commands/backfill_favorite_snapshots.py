from django.core.management.base import BaseCommand
from apps.favorites.models import Favorite
from apps.favorites.serializers import _build_snapshot_for_object
from django.utils import timezone

BATCH = 200

class Command(BaseCommand):
    help = "Backfill snapshot and snapshot_at for existing Favorite records"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Don't save changes; just report")
        parser.add_argument("--limit", type=int, default=None, help="Limit number of favorites to process")

    def handle(self, *args, **options):
        dry = options["dry_run"]
        limit = options.get("limit")
        qs = Favorite.objects.all().select_related("content_type").order_by("-created_at")
        if limit:
            qs = qs[:limit]

        total = qs.count()
        self.stdout.write(f"Processing {total} favorites (dry_run={dry})...")

        processed = 0
        updated = 0
        for f in qs.iterator():
            processed += 1
            if f.snapshot:
                continue
            try:
                ct = f.content_type
                target = f.content_object
                snapshot = {"id": str(f.object_id), "type": f"{ct.app_label}.{ct.model}"}
                if target is not None:
                    snapshot = _build_snapshot_for_object(ct, target)
                if not dry:
                    f.snapshot = snapshot
                    f.snapshot_at = timezone.now()
                    f.save(update_fields=["snapshot", "snapshot_at"])
                updated += 1
            except Exception as e:
                self.stderr.write(f"Failed for favorite {f.id}: {e}")

        self.stdout.write(f"Done. Processed={processed} Updated={updated}")
