from typing import Set
from django.contrib.contenttypes.models import ContentType

from .models import Favorite


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
