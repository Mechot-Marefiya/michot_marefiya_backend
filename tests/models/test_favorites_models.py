# BASELINE: written from CODEBASE_MAP.md
# PRD status: verified
# Flutter contract: no
# Last updated: 2026-06-01

import pytest
from django.contrib.contenttypes.models import ContentType

from apps.favorites.models import Favorite

pytestmark = pytest.mark.django_db


def test_favorite_str_representation(favorite):
    assert str(favorite).startswith("Favorite:")


def test_favorite_unique_together_constraint(auth_client, user, hotel):
    ct = ContentType.objects.get_for_model(hotel.__class__)
    Favorite.objects.create(user=user, content_type=ct, object_id=str(hotel.id))

    with pytest.raises(Exception):
        Favorite.objects.create(user=user, content_type=ct, object_id=str(hotel.id))
