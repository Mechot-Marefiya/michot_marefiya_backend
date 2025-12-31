import logging
from config.celery import app
from apps.core.services import CurrencyService

logger = logging.getLogger(__name__)

@app.task
def fetch_daily_exchange_rates():
    try:
        CurrencyService.get_daily_exchange_rate()
        logger.info("Successfully triggered daily exchange rates fetch.")
    except Exception as e:
        logger.exception(f"Unexpected error in fetch_daily_exchange_rates task: {e}")
