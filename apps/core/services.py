from pprint import pprint
import requests
import os
from pathlib import Path
from environ import Env
from apps.core.models import CurrencyRate

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

    APP_ID = env("OPEN_EXCHANGE_RATE_APP_ID")
    BASE_URL = env("OPEN_EXCHANGE_RATE_BASE_URL")

    @classmethod
    def get_request_template(cls, url: str):
        params: dict = {"app_id": cls.APP_ID}

        try:
            res = requests.get(url, params=params, timeout=10)
            res.raise_for_status()
            return res.json()
            # pprint(data)
            # return {"status": "success", "base": data.get("base"), "count": len(data.get("rates", {}))}
        except requests.RequestException as e:
            raise RuntimeError(f"Failed to fetch data: {e}")

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
    def store_exchange_rates(json_res: dict):
        base = json_res.get("base")
        rates: dict = json_res.get("rates", {})

        rate_objs = [
            CurrencyRate(base=base, target=target, rate=rate)
            for target, rate in rates.items()
        ]

        CurrencyRate.objects.bulk_create(rate_objs)

        return rate_objs


# CurrencyService.get_currencies()
