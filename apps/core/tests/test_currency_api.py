import pytest
from django.urls import reverse
from rest_framework import status
from apps.core.models import CurrencyRate
from datetime import date, timedelta
from decimal import Decimal

@pytest.mark.django_db
class TestCurrencyRatesAPI:
    def test_get_rates_latest_date(self, client):
        # Create test rates
        today = date.today()
        CurrencyRate.objects.create(base="USD", target="ETB", rate=Decimal("150.0"), date=today)
        CurrencyRate.objects.create(base="USD", target="EUR", rate=Decimal("0.9"), date=today)
        
        url = reverse("currencies-rates")
        response = client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        data = response.data
        assert data["ETB"] == 150.0
        assert data["EUR"] == 0.9
        assert data["USD"] == 1.0

    def test_get_rates_filters_by_latest_date(self, client):
        today = date.today()
        yesterday = today - timedelta(days=1)
        
        # Use GBP to avoid collision with ETB/EUR from previous test if DB isn't cleared
        CurrencyRate.objects.create(base="USD", target="GBP", rate=Decimal("0.7"), date=yesterday)
        CurrencyRate.objects.create(base="USD", target="GBP", rate=Decimal("0.8"), date=today)
        
        url = reverse("currencies-rates")
        response = client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        data = response.data
        assert data["GBP"] == 0.8 # Should be today's rate

    def test_get_rates_empty(self, client):
        url = reverse("currencies-rates")
        response = client.get(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND
