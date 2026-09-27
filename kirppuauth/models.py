from django.db import models
from django.contrib.auth.models import AbstractUser
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.utils.translation import gettext_lazy as _


class UsernameValidator(UnicodeUsernameValidator):
    # `!` should be allowed only for users from SSO that don't have username property.
    regex = r"^!?[\w.@+-]+\Z"


class User(AbstractUser):
    username_validator = UsernameValidator()
    username = models.CharField(
        _("username"),
        max_length=150,
        unique=True,
        help_text=_(
            "Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only."
        ),
        validators=[username_validator],
        error_messages={
            "unique": _("A user with that username already exists."),
        },
    )

    phone = models.CharField(max_length=64, blank=False, null=False)
    last_checked = models.DateTimeField(auto_now_add=True)
    kompassi_sub = models.CharField(max_length=256, blank=True, null=True, unique=True)
