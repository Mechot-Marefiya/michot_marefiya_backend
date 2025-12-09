from config.celery import app
from apps.core.services import CurrencyService

@app.task
def fetch_daily_exchange_rates():
    try:
        CurrencyService.get_daily_exchange_rate()
        print("Successfully fetched and stored daily exchange rates.")
    except Exception as e:
        print(f"ERROR fetching exchange rates: {e}")
