# BASELINE: written from CODEBASE_MAP.md
# PRD status: verified
# Flutter contract: no
# Last updated: 2026-06-01

import pytest
from django.conf import settings
from apps.core.tasks import fetch_daily_exchange_rates

pytestmark = pytest.mark.django_db


def test_fetch_daily_exchange_rates_executes_successfully(monkeypatch):
    called = {"value": False}

    def fake_fetch():
        called["value"] = True

    monkeypatch.setattr("apps.core.tasks.CurrencyService.get_daily_exchange_rate", fake_fetch)

    assert fetch_daily_exchange_rates() is None
    assert called["value"] is True


def test_fetch_daily_exchange_rates_handles_failure(monkeypatch):
    def fake_fetch():
        raise RuntimeError("boom")

    monkeypatch.setattr("apps.core.tasks.CurrencyService.get_daily_exchange_rate", fake_fetch)

    assert fetch_daily_exchange_rates() is None


def test_fetch_daily_exchange_rates_beat_schedule_registered():
    assert "fetch-daily-exchange-rates-every-1-day" in settings.CELERY_BEAT_SCHEDULE
