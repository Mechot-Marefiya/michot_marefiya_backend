import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _


class AbstractBaseModel(models.Model):
    id = models.UUIDField(
        primary_key=True, editable=False, default=uuid.uuid4, verbose_name=_("Id")
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created At"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Updated_at"))

    class Meta:
        abstract = True


# class DataLookup(AbstractBaseModel):
#     lookup_type = models.CharField(max_length=50)
#     key = models.CharField(max_length=50)
#     value = models.CharField(max_length=255)
#     display_name = models.CharField(
#         max_length=100, blank=True
#     )
#     sort_order = models.PositiveIntegerField(default=0)
#     is_active = models.BooleanField(default=True)
#     is_default = models.BooleanField(default=False)
#     metadata = models.JSONField(default=dict, blank=True)

#     class Meta:
#         db_table = "data_lookups"
#         constraints = [
#             # Unique key within each lookup type
#             models.UniqueConstraint(
#                 fields=["lookup_type", "key"],
#                 name="unique_key_per_lookup_type"
#             ),
#             # Only one default per lookup type
#             models.UniqueConstraint(
#                 fields=["lookup_type"],
#                 condition=models.Q(is_default=True),
#                 name="one_default_per_lookup_type"
#             )
#         ]
#         indexes = [
#             models.Index(fields=["lookup_type", "is_active"]),
#             models.Index(fields=["lookup_type", "sort_order"]),
#         ]

#     def __str__(self):
#         return f"{self.lookup_type}: {self.display_name or self.key}"
