from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext_lazy as _

from apps.account.managers import CustomUserManager
from apps.core.models import AbstractBaseModel


class User(AbstractUser, AbstractBaseModel):
    email = models.EmailField(verbose_name=_("Email"), unique=True)

    username = None

    USERNAME_FIELD = "email"

    REQUIRED_FIELDS = []

    objects = CustomUserManager()

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")
        ordering = ("-created_at",)
        db_table = "users"

    def __str__(self) -> str:
        return self.email
