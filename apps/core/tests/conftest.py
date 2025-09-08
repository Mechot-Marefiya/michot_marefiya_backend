import pytest
from apps.core.models import Address


@pytest.fixture
def address():
    return Address.objects.create(
        street_line1="Wollo Sefer",
        country="Ethiopia",
        city="Addis Ababa",
        sub_city="Bole",
        state="Addis Ababa",
        postal_code="1000",
        latitude=9.012345,
        longitude=38.765432,
    )
