import os
import requests
import logging
from pprint import pprint
from pathlib import Path
from decimal import Decimal
from environ import Env
from django.db import transaction
from django.utils import timezone
from apps.core.models import CurrencyRate

logger = logging.getLogger(__name__)

env = Env()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

env.read_env(os.path.join(BASE_DIR, ".env"))


class CurrencyService:
    """
    Handles fetching and storing currency exchange rates from external
    providers such as Open Exchange Rates. Rates are stored in the database for
    consistency and quick access throughout the app.
    """

    APP_ID = env("OPEN_EXCHANGE_RATE_APP_ID", default=None)
    BASE_URL = env("OPEN_EXCHANGE_RATE_BASE_URL", default="https://openexchangerates.org/api")

    @classmethod
    def get_request_template(cls, url: str):
        params: dict = {"app_id": cls.APP_ID}

        try:
            res = requests.get(url, params=params, timeout=10)
            res.raise_for_status()
            return res.json()
        except requests.RequestException as e:
            logger.error(f"Failed to fetch exchange rates from {url}: {e}")
            raise RuntimeError(f"Failed to fetch currency data: {e}")

    @classmethod
    def get_daily_exchange_rate(cls):
        """
        Fetch the latest exchange rates and store them in the database.
        """
        url = f"{cls.BASE_URL}/latest.json"

        data = cls.get_request_template(url)
        pprint(data)
        cls.store_exchange_rates(data)

    @classmethod
    def get_currencies(cls):
        """
        Fetch the latest exchange rates and store them in the database.
        """
        url = f"{cls.BASE_URL}/currencies.json"

        data = cls.get_request_template(url)

        pprint(data)

    @staticmethod
    @transaction.atomic
    def store_exchange_rates(json_res: dict):
        base = json_res.get("base")
        rates: dict = json_res.get("rates", {})
        
        if not base or not rates:
            logger.warning("Empty or malformed exchange rate data received.")
            return []

        # Use the current date for the record (or extract from JSON if available)
        today = timezone.now().date()

        rate_objs = [
            CurrencyRate(
                base=base, 
                target=target, 
                rate=Decimal(str(rate)), 
                date=today
            )
            for target, rate in rates.items()
        ]

        # Use bulk_create with update_conflicts for idempotency and efficiency
        try:
            CurrencyRate.objects.bulk_create(
                rate_objs,
                update_conflicts=True,
                unique_fields=['base', 'target', 'date'],
                update_fields=['rate']
            )
            logger.info(f"Successfully stored {len(rate_objs)} exchange rates for {base} on {today}.")
        except Exception as e:
            logger.error(f"Failed to bulk store exchange rates: {e}")
            raise

        return rate_objs

    @classmethod
    def seed_from_local_json(cls):
        """
        Seeds the database using the local rate_data.json file.
        Useful for development when no API key is available.
        """
        import json
        json_path = BASE_DIR / "apps" / "core" / "rate_data.json"
        
        if not json_path.exists():
            print(f"File not found: {json_path}")
            return
            
        with open(json_path, 'r') as f:
            data = json.load(f)
            
        return cls.store_exchange_rates(data)


# CurrencyService.get_currencies()
