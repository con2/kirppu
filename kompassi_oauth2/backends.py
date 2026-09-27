import typing

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import BaseBackend
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.utils.translation import gettext
from requests_oauthlib import OAuth2Session

User = get_user_model()


class OAuth2Message(Exception):
    pass


def user_defaults_from_kompassi(kompassi_user):
    return dict(
        (django_key, kompassi_user[kompassi_key])
        for (django_key, kompassi_key) in settings.KOMPASSI_USER_MAP_OIDC
    )


@transaction.atomic
def update_or_create(query: Q, updates: dict, creates: dict) -> tuple[User, bool]:
    try:
        # User.email is not unique, so old data might potentially return multiple objects.
        users = User.objects.filter(query)
        user_count = len(users)
        if user_count == 0:
            raise User.DoesNotExist()
        if user_count > 1:
            raise OAuth2Message(
                gettext(
                    "OAuth2 login returned multiple users. Please contact service administration."
                )
            )
        user = users[0]
        update = []
        for k, v in updates.items():
            if getattr(user, k) != v:
                setattr(user, k, v)
                update.append(k)
        if update:
            user.save(update_fields=update)
        return user, False
    except User.DoesNotExist:
        return User.objects.create(**updates, **creates), True


class KompassiOAuth2AuthenticationBackend(BaseBackend):
    NAME = "kompassi"

    def authenticate(
        self, request, oauth2_session: OAuth2Session | None = None, **kwargs
    ):
        if oauth2_session is None:
            # Not ours (password login)
            return None

        response = oauth2_session.get(settings.KOMPASSI_OIDC_USER_INFO_URL)
        response.raise_for_status()
        kompassi_user = response.json()

        oidc_sub = kompassi_user.get("sub")
        if oidc_sub is None:
            raise KeyError("No sub in OIDC")
        if kompassi_user.get("email") in (None, ""):
            raise PermissionDenied("No email in OIDC")
        if settings.KOMPASSI_OIDC_REQUIRE_VERIFIED_EMAIL and not kompassi_user.get(
            "email_verified", False
        ):
            raise OAuth2Message(
                gettext(
                    "Your email address is not verified. You need to verify it before using this service."
                )
            )

        sub_id = f"{self.NAME}-{oidc_sub}"
        defaults = user_defaults_from_kompassi(kompassi_user)
        creates = {}
        if "username" not in defaults:
            # Don't overwrite username, but populate it on create as it is a required field.
            creates["username"] = f"!{sub_id}"

        if hasattr(User, "kompassi_sub"):
            # Primarily try to match by sub value, and if that doesn't exist, by email.
            defaults["kompassi_sub"] = sub_id
            user, _ = update_or_create(
                Q(kompassi_sub=sub_id) | Q(email=kompassi_user["email"]),
                updates=defaults,
                creates=creates,
            )
        else:
            # Fallback to matching by email address.
            user, _ = update_or_create(
                Q(email=kompassi_user["email"]),
                updates=defaults,
                creates=creates,
            )

        return user

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
