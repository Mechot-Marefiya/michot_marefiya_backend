# BASELINE: written from CODEBASE_MAP.md
# PRD status: verified
# Flutter contract: no
# Last updated: 2026-06-01

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.core.models import Address, CurrencyRate, Facility

pytestmark = pytest.mark.django_db


def test_address_str_representation(address):
    assert str(address) == f"{address.city} - {address.street_line1}"


def test_address_required_fields_validation():
    address = Address(city="Addis Ababa", street_line1="")
    with pytest.raises(ValidationError):
        address.full_clean()


def test_facility_str_representation():
    facility = Facility(name="Pool", icon="pool")
    assert str(facility) == "Pool"


def test_currency_rate_str_representation():
    rate = CurrencyRate(base="USD", target="ETB", rate=Decimal("120.000000"))
    assert "1 USD = 120.000000 ETB" in str(rate)


def test_currency_rate_unique_constraints():
    CurrencyRate.objects.create(base="USD", target="ETB", rate=Decimal("120.000000"))

    with pytest.raises(Exception):
        CurrencyRate.objects.create(base="USD", target="ETB", rate=Decimal("121.000000"))
