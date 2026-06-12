import logging

from config.celery import app
from django.db import transaction

from apps.analytics.models import AnalyticsDirtyDate
from apps.analytics.services import materialize_company_daily_metrics, precompute_admin_analytics_cache

logger = logging.getLogger(__name__)


@app.task
def process_dirty_analytics_dates(limit=500):
    dirty_rows = list(
        AnalyticsDirtyDate.objects.filter(processed=False)
        .order_by("company_id", "date")[:limit]
    )

    processed = 0
    for dirty in dirty_rows:
        try:
            with transaction.atomic():
                materialize_company_daily_metrics(dirty.company_id, dirty.date)
                dirty.processed = True
                dirty.save(update_fields=["processed", "updated_at"])
            processed += 1
        except Exception:
            logger.exception(
                "Failed to process analytics dirty date company=%s date=%s",
                dirty.company_id,
                dirty.date,
            )

    return {"processed": processed, "remaining": AnalyticsDirtyDate.objects.filter(processed=False).count()}


@app.task
def precompute_analytics_cache():
    return precompute_admin_analytics_cache()
