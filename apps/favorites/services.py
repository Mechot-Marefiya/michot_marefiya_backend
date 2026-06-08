from typing import Set
from django.contrib.contenttypes.models import ContentType
from apps.account.models import normalize_phone_number

from .models import Favorite, GuestFavorite


def get_favorite_object_ids(user, content_type: ContentType) -> Set[str]:
    """
    Read-only helper that returns a set of Favorite.object_id (strings)
    for the given user and content_type.

    Executes exactly one DB query. Returns empty set for anonymous users.
    No side-effects.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return set()

    qs = Favorite.objects.filter(user=user, content_type=content_type).values_list("object_id", flat=True)
    return set(str(x) for x in qs)


def get_guest_favorite_object_ids(phone: str, content_type: ContentType) -> Set[str]:
    normalized_phone = normalize_phone_number(phone)
    if not normalized_phone:
        return set()

    qs = GuestFavorite.objects.filter(
        guest_phone=normalized_phone,
        linked_user__isnull=True,
        content_type=content_type,
    ).values_list("object_id", flat=True)
    return set(str(x) for x in qs)
