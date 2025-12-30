from django.core.exceptions import ObjectDoesNotExist
from decimal import Decimal
from datetime import date
from .models import CurrencyRate
REFERENCE_CURRENCY = 'USD'
def get_rate_to_reference(currency_code: str, rate_date: date) -> Decimal:
    """
    Finds the rate to convert 1 unit of the given currency (X) to the 
    REFERENCE_CURRENCY (USD). Returns Rate_X_to_USD.
    
    Prioritizes the rate for the specific date, but falls back to the latest 
    available rate if that's missing (production robustness).
    """
    if currency_code == REFERENCE_CURRENCY:
        return Decimal('1.0')
    
    # Try to find exactly for the date, or fallback to latest
    # Base to Reference
    rate_obj = CurrencyRate.objects.filter(
        base__iexact=currency_code, 
        target__iexact=REFERENCE_CURRENCY
    ).order_by('-date').first()

    if rate_obj:
        return rate_obj.rate

    # Try inverse: Reference to Base
    inverse_rate_obj = CurrencyRate.objects.filter(
        base__iexact=REFERENCE_CURRENCY, 
        target__iexact=currency_code
    ).order_by('-date').first()

    if inverse_rate_obj:
        if inverse_rate_obj.rate == 0:
            raise ValueError(f"Stored rate for {REFERENCE_CURRENCY} to {currency_code} is zero.")
            
        # Return 1 / Rate_USD_to_X = Rate_X_to_USD
        return Decimal('1.0') / inverse_rate_obj.rate 
        
    raise ObjectDoesNotExist(
        f"No exchange rate found for {currency_code} (Base) and {REFERENCE_CURRENCY} (Target)."
    )
def convert_currency(amount: Decimal, source_currency: str, target_currency: str, rate_date: date = date.today()) -> Decimal:
    """
    Converts amount from source_currency to target_currency using USD triangulation.
    """
    if not amount:
        return Decimal('0.00')
        
    # Ensure amount is Decimal
    if not isinstance(amount, Decimal):
        try:
            amount = Decimal(str(amount))
        except (TypeError, ValueError):
            return Decimal('0.00')

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

def get_display_currency(request) -> str:
    """
    Extracts display currency from request query parameters or headers.
    Returns the currency code (e.g., 'USD') or None if not specified.
    Safely strips quotes and whitespace.
    """
    if not request:
        return None
        
    currency = (
        request.query_params.get('display_currency') or 
        request.query_params.get('?display_currency') or # Handle malformed URL typo
        request.headers.get('X-Display-Currency') or
        request.query_params.get('X-Display-Currency') # Common mistake
    )
    
    if currency:
        return currency.strip(' "\'').upper()
        
    return None