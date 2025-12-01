from django.core.exceptions import ObjectDoesNotExist
from decimal import Decimal
from datetime import date
from .models import CurrencyRate
REFERENCE_CURRENCY = 'USD'
def get_rate_to_reference(currency_code: str, rate_date: date) -> Decimal:
    """
    Finds the rate to convert 1 unit of the given currency (X) to the 
    REFERENCE_CURRENCY (USD). Returns Rate_X_to_USD.
    """
    if currency_code == REFERENCE_CURRENCY:
        return Decimal('1.0')
    try:
        rate_obj = CurrencyRate.objects.get(
            base__iexact=currency_code, 
            target__iexact=REFERENCE_CURRENCY, 
            date=rate_date
        )
        return rate_obj.rate

    except ObjectDoesNotExist:
        try:
            inverse_rate_obj = CurrencyRate.objects.get(
                base__iexact=REFERENCE_CURRENCY, 
                target__iexact=currency_code, 
                date=rate_date
            )
            if inverse_rate_obj.rate == 0:
                raise ValueError("Stored reference rate is zero, cannot calculate inverse.")
                
            return 1 / inverse_rate_obj.rate 
            
        except ObjectDoesNotExist:
            raise ObjectDoesNotExist(
                f"Reference rate not found for {currency_code} using {REFERENCE_CURRENCY} on {rate_date}."
            )
def convert_currency(amount: Decimal, source_currency: str, target_currency: str, rate_date: date = date.today()) -> Decimal:
    """
    Converts amount from source_currency to target_currency using USD triangulation.
    """
    if source_currency == target_currency:
        return amount.quantize(Decimal('0.01'))

    try:

        rate_source_to_usd = get_rate_to_reference(source_currency, rate_date)
        amount_in_usd = amount * rate_source_to_usd

        rate_target_to_usd = get_rate_to_reference(target_currency, rate_date)
        
        if rate_target_to_usd == 0:
            raise ValueError("Target currency reference rate is zero.")
            
        rate_usd_to_target = 1 / rate_target_to_usd 

        converted_amount = amount_in_usd * rate_usd_to_target
        
        return converted_amount.quantize(Decimal('0.01'))
        
    except ObjectDoesNotExist as e:
        raise ObjectDoesNotExist(str(e))
    except Exception as e:
        raise Exception(f"Triangulation failed: {e}")