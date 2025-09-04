import datetime
from decimal import Decimal
import enum
import random
import string
import typing
import warnings

from django.core.exceptions import ValidationError, ImproperlyConfigured
from django.core.validators import MinLengthValidator, MinValueValidator, RegexValidator
from django.db import models, transaction, IntegrityError
from django.db.models import F, Sum, Q
import django.http
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.utils.module_loading import import_string
from django.conf import settings

from .utils import model_dict_fn, format_datetime, short_description, datetime_iso_human

from .util import (
    number_to_hex,
    hex_to_number,
    b32_encode,
    b32_decode,
    pack,
    unpack,
    shorten_text,
)


# Settings safety check.
if settings.KIRPPU_AUTO_CLERK and not settings.DEBUG:
    raise ImproperlyConfigured("Automatic clerk code usage may not be used in production!")

User = settings.AUTH_USER_MODEL


def decimal_to_transport(value):
    # round(): Database provides a rounded value anyway, so use the same
    # to avoid having different value for database-rows and in-memory-rows (provision pre-calculation).
    return int(round(value * Item.FRACTION))


class UserAdapterBase(object):
    """
    Base version of UserAdapter. This can be (optionally) subclassed somewhere else which can then be set
    to be used by system via `settings.KIRPPU_USER_ADAPTER`.
    """
    @classmethod
    def phone(cls, user):
        return user.phone

    @classmethod
    def phone_query(cls, rhs, fn=None):
        fn = "" if fn is None else ("__" + fn)
        return {"phone" + fn: rhs}

    @classmethod
    def is_clerk(cls, user, event):
        return hasattr(user, "clerk_set") and user.clerk_set.filter(event=event).exists()

    @classmethod
    def print_name(cls, user):
        last_name_part = user.last_name[:1]
        if last_name_part and last_name_part != user.last_name:
            last_name_part += "."
        name = u"{0} {1}".format(user.first_name, last_name_part).strip()
        if len(name) == 0:
            return user.username
        return name.title()

    @classmethod
    def full_name(cls, user):
        return user.get_full_name()


# The actual class is found by string in settings.
UserAdapter: UserAdapterBase = import_string(settings.KIRPPU_USER_ADAPTER)


class Person(models.Model):
    """
    Abstract person that is not User.
    """
    first_name = models.CharField(_('first name'), max_length=30, blank=True)
    last_name = models.CharField(_('last name'), max_length=30, blank=True)
    email = models.EmailField(_('email address'), blank=True)
    phone = models.CharField(max_length=64, blank=True, null=False)

    def full_name(self):
        return u"{first_name} {last_name}".format(first_name=self.first_name, last_name=self.last_name).strip()

    def __str__(self):
        e = list(filter(lambda i: i != "", (self.full_name(), self.email, self.phone)))
        if e:
            return str(e[0])
        return "(id=%d)" % self.id


def _validate_provision_function(fn):
    if fn is None:
        return

    from .provision import Provision
    try:
        Provision.run_function(fn, Item.objects.none())
    except Exception as e:
        raise ValidationError(e)


class Event(models.Model):
    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=250)
    home_page = models.URLField(blank=True)
    start_date = models.DateField()
    end_date = models.DateField()

    registration_end = models.DateTimeField(null=True, blank=True)
    registration_disabled = models.BooleanField(
        default=True,
        help_text=_(
            "When set, registration is disabled even if registration end is set."
            " If not set, registration is enabled until registration end if that is set."
        ),
    )
    checkout_active = models.BooleanField(default=False)
    mobile_view_visible = models.BooleanField(default=False)
    multiple_vendors_per_user = models.BooleanField(default=False)
    age_restricted_items = models.BooleanField(default=True)
    use_boxes = models.BooleanField(default=True)
    provision_function = models.TextField(
        blank=True,
        null=True,
        help_text=_("Lisp function body that gets sold_and_compensated queryset as"
                    " a global and must return a null or decimal number."),
        validators=[
            _validate_provision_function,
        ],
    )
    max_brought_items = models.IntegerField(
        blank=True,
        null=True,
        help_text=_("Amount of unsold Items a Vendor can have in the Event. If blank, no limit is imposed."),
        validators=[MinValueValidator(1)],
    )
    box_as_single_brought_item = models.BooleanField(
        default=False,
        help_text=_("Should a box be considered a single item when counting max brought"
                    " items instead of considering its contents individually."),
    )
    min_box_size = models.PositiveSmallIntegerField(null=False, default=1)

    # Link to another database.
    source_db = models.CharField(blank=True, max_length=250, null=True, unique=True)

    VISIBILITY_VISIBLE = 0
    VISIBILITY_NOT_LISTED = 1
    VISIBILITY = (
        (VISIBILITY_VISIBLE, _("Visible")),
        (VISIBILITY_NOT_LISTED, _("Not listed in front page")),
    )
    visibility = models.SmallIntegerField(choices=VISIBILITY, default=VISIBILITY_VISIBLE)
    access_signup = models.BooleanField(default=False)
    access_signup_token = models.CharField(blank=True, default="", max_length=128)

    def __str__(self):
        return self.name

    def require_default_db(self):
        if self.source_db or self._remote_event is not None:
            raise django.http.Http404()

    @classmethod
    def from_db(cls, db, field_names, values):
        instance = super().from_db(db, field_names, values)
        instance._db_alias = db
        return instance

    _db_alias = None  # assigned in Event.from_db
    _remote_event = None  # assigned in get_real_event.

    def get_absolute_url(self):
        return reverse("kirppu:vendor_view", kwargs={"event_slug": self.slug})

    def get_real_event(self) -> typing.Union["Event", "RemoteEvent"]:
        """Get actual instance for remote Event, or self if this is not a remote Event."""
        assert self._db_alias == "default"  # Recursion should not be allowed.

        if self._remote_event is not None:
            return self._remote_event

        event = None
        if self.source_db:
            if ":" in self.source_db:
                db, name = self.source_db.split(":")
                event = RemoteEvent.objects.using(db).get(slug=name)
            else:
                # Assumption based on 0029_apply_default_event.
                event = RemoteEvent.objects.using(self.source_db).get(slug="default")
            self._remote_event = event
        else:
            event = self

        return event

    def get_real_database_alias(self):
        if self.source_db:
            if ":" in self.source_db:
                db, _ = self.source_db.split(":")
            else:
                db = self.source_db
            return db
        else:
            return self._db_alias

    def get_user_query(self, user):
        if self.source_db:
            return {"user__username": user.username}
        else:
            assert self._db_alias == "default"
            return {"user": user}

    @staticmethod
    def get_source_event_list():
        dbs = settings.KIRPPU_EXTRA_DATABASES
        events = settings.KIRPPU_EXTRA_EVENTS
        event_dbs = set(events.values())
        result = []
        for db in dbs:
            if db not in event_dbs:
                result.append(db)
        for event, db in events.items():
            result.append(db + ":" + event)
        return result


class RemoteEvent(Event):
    """Event instance from "EXTRA_DATABASES"."""
    class Meta:
        proxy = True

    def get_absolute_url(self):
        raise ValueError("Remote event cannot be referred.")

    def get_real_database_alias(self):
        return self._db_alias

    def get_real_event(self) -> "RemoteEvent":
        self._remote_event = self
        return self

    def get_user_query(self, user):
        return {"user__username": user.username}


class EventPermission(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)

    can_manage_event = models.BooleanField(default=False)
    can_see_clerk_codes = models.BooleanField(default=False)
    can_see_statistics = models.BooleanField(default=False)
    can_see_accounting = models.BooleanField(default=False)
    can_register_items_outside_registration = models.BooleanField(default=False)
    can_perform_overseer_actions = models.BooleanField(default=False)
    can_switch_sub_vendor = models.BooleanField(default=False)
    can_create_sub_vendor = models.BooleanField(default=False)

    _short_mapping = (
        (can_manage_event, "Manage"),
        (can_see_clerk_codes, "CCodes"),
        (can_see_statistics, "STAT"),
        (can_see_accounting, "ACC"),
        (can_register_items_outside_registration, "REG"),
        (can_perform_overseer_actions, "OVER"),
        (can_switch_sub_vendor, "SubSw"),
        (can_create_sub_vendor, "SubCr"),
    )

    class Meta:
        unique_together = (("event", "user"),)

    def __str__(self):
        return "{} / {}".format(self.event, self.user)

    @short_description(_("Permissions"))
    def combination(self):
        enabled_names = list(
            value
            for key, value in self._short_mapping
            if getattr(self, key.name)
        )
        if not enabled_names:
            return "----"
        return ", ".join(enabled_names)

    @classmethod
    def get(cls, event: Event, user):
        if user.is_authenticated:
            try:
                # TODO: What to do if both default proxy and external event define permissions?
                return cls.objects.get(event=event, user=user)
            except cls.DoesNotExist:
                args = dict(event=event, user=user)
        else:
            args = dict(event=event)

        # Create a dummy EventPermission from defaults.
        fields = cls._meta.get_fields()
        for field in fields:
            if not field.is_relation and field.default != models.fields.NOT_PROVIDED:
                args[field.name] = field.default
        return cls(**args)


class ClerkPrefetchManager(models.Manager):
    """Manager for "default" use so that admin doesn't need to always fetch user information separately."""
    def get_queryset(self):
        return super().get_queryset().select_related("user")


class Clerk(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    user = models.ForeignKey(User, blank=True, null=True, on_delete=models.CASCADE)
    access_key = models.CharField(
        max_length=128,
        null=True,
        blank=True,
        verbose_name=_(u"Access key value"),
        help_text=_(u"Access code assigned to the clerk. 14 hexlets."),
        validators=[RegexValidator("^[0-9a-fA-F]{14}$", message="Must be 14 hex chars.")]
    )

    prefetch_manager = ClerkPrefetchManager()
    objects = models.Manager()

    class Meta:
        default_manager_name = "prefetch_manager"
        constraints = (
            # user may be null if access_key is set in case of "unbound Clerk object".
            # access_key may be null if the clerk object has been disabled for user.
            models.constraints.CheckConstraint(
                condition=models.Q(user__isnull=False) | models.Q(access_key__isnull=False),
                name="required_values",
            ),
            models.constraints.UniqueConstraint(
                fields=["access_key"],
                name="unique_access_key",
            ),
            # Only one Clerk per Event.
            models.constraints.UniqueConstraint(
                fields=["event", "user"],
                name="unique_event_clerk"
            ),
        )
        permissions = (
            ("oversee", "Can perform overseer actions"),
        )

    def __str__(self):
        if self.user is not None:
            return str(self.user)
        else:
            return self.access_code

    def __repr__(self):
        if self.user is not None:
            return "<Clerk: %s>" % str(self.user)
        else:
            return "<Clerk id=%s, code=%s...>" % (self.id, self.access_code[:5])

    def as_dict(self):
        return {
            "user": str(self.user),
            "print": UserAdapter.print_name(self.user),
        }

    def get_code(self):
        """
        Get access card code for this Clerk.

        Format of the code:
            zeros:       4 bits
            access_key: 56 bits
            checksum:    4 bits
            -------------------
            total:      64 bits

        :return: Clerk code.
        :rtype: str
        """
        if self.access_key in ("", None):
            return ""
        access_key = hex_to_number(self.access_key)
        return b32_encode(
            pack([
                (4, 0),
                (56, access_key),
            ], checksum_bits=4),
            length=8
        )

    @property
    def access_code(self):
        if self.access_key is not None:
            return self.get_code()
        return ""

    @property
    def access_code_str(self):
        if self.is_valid_code:
            return self.get_code()
        return "----------------"

    @classmethod
    def by_code(cls, code: str, include_unbound: bool = False, **query):
        """
        Return the Clerk instance with the given hex code.

        :param code: Raw code string from access card.
        :param include_unbound: If `True`, unbound Clerk object is returned. Otherwise, a `None` is returned.
        :return: The corresponding Clerk or None if access token is invalid.
        :rtype: Clerk | None
        :raises: ValueError if not a valid Clerk access code.
        """
        try:
            zeros, access_key = unpack(
                b32_decode(code, length=8),
                [4, 56],
                checksum_bits=4,
            )
        except TypeError:
            raise ValueError("Not a Clerk code")

        if zeros != 0:
            raise ValueError("Not a Clerk code")

        if access_key < 100000:
            # "Valid" key, but disabled.
            raise ValueError("Clerk disabled")
        access_key_hex = number_to_hex(access_key, 56)
        try:
            clerk = cls.objects.get(access_key=access_key_hex, **query)
        except cls.DoesNotExist:
            return None
        if not include_unbound and clerk.user is None:
            return None
        return clerk

    @property
    def is_valid_code(self):
        return self.access_key is not None and int(self.access_key, 16) >= 100000

    @property
    @short_description(_("Is enabled?"))
    def is_enabled(self):
        return self.is_valid_code and self.user is not None

    def generate_access_key(self, disabled=False):
        """
        Generate new access token for this Clerk. This will automatically overwrite old value.

        :return: The newly generated token.
        """
        if disabled:
            self.access_key = None
            return None
        key = None
        i_min = 100000
        i_max = 2 ** 56 - 1
        while key is None or Clerk.objects.filter(access_key=key).exists():
            key = random.randint(i_min, i_max)
            key = number_to_hex(key, 56)
        self.access_key = key
        return key

    def save(self, *args, **kwargs):
        # Ensure a value on access_key.
        if self.access_key is None and self.user is None:
            self.generate_access_key()
        super(Clerk, self).save(*args, **kwargs)

    @classmethod
    def generate_empty_clerks(cls, event, count=1, commit=True):
        """
        Generate unbound Clerks, i.e. Clerks that have access-code but no user.
        These Clerks can be "moved" to existing clerks so that the real Clerk will start
        using the access key from unbound one.

        This allows access codes to be pre-populated and printed to cards, which then can be
        taken easily to use in case of need without needing to create the card then.

        :param count: Count of unbound Clerks to generate, default 1.
        :type count: int
        :param commit: If `True` the item(s) are saved instead of just returned in a list.
        :type commit: bool
        :return: List of generated rows.
        :rtype: list[Clerk]
        """
        ids = []
        for _ in range(count):
            item = cls(event=event)
            item.generate_access_key()
            if commit:
                item.save()
            ids.append(item)
        return ids


class AccessSignup(models.Model):
    class Target(int, enum.Enum):
        def __new__(cls, value: int, label):
            obj = int.__new__(cls, value)
            obj._value_ = value
            obj.label = label
            return obj
        CLERK = 1, _("Clerk")
        OVERSEER = 2, _("Overseer")
        STATS = 3, _("Statistics")
        ACCOUNTING = 4, _("Accounting")

    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    creation_time = models.DateTimeField()
    update_time = models.DateTimeField()
    resolution_time = models.DateTimeField(null=True)
    resolution_accepted = models.BooleanField(default=False)
    # Comma-separated list of Target values.
    target_set = models.CharField(max_length=255)
    message = models.TextField(max_length=500)

    def __str__(self):
        return "%s / %s" % (self.event.name, self.user.username)

    def save(self, no_update_time: bool = False, **kwargs):
        now = timezone.now()
        if self.creation_time is None:
            self.creation_time = now
        updates = kwargs.pop("update_fields", None)
        if not no_update_time:
            self.update_time = now
            if updates is not None:
                updates = list(updates)
                updates.append("update_time")
        super().save(update_fields=updates, **kwargs)

    class Meta:
        unique_together = (
            ("event", "user"),
        )


class Vendor(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    person = models.ForeignKey(Person, null=True, blank=True, on_delete=models.CASCADE)
    terms_accepted = models.DateTimeField(null=True)
    mobile_view_visited = models.BooleanField(default=False)
    event = models.ForeignKey(Event, on_delete=models.CASCADE)

    class Meta:
        unique_together = (
            ("user", "person", "event"),
        )
        permissions = (
            ("can_switch_sub_vendor", "Can switch to created sub-Vendors"),
            ("can_create_sub_vendor", "Can create new sub-Vendors"),
        )

    def __repr__(self):
        return '<Vendor: {0}>'.format(str(self.user) + (
            (" / " + str(self.person)) if self.person is not None else ""))

    def __str__(self):
        return self.printable_name + " id=" + str(self.id)

    @property
    def printable_name(self) -> str:
        return str(self.user) if self.person is None else str(self.person)

    @classmethod
    def get_vendor(cls, request, event: typing.Union[Event, RemoteEvent]):
        """
        Get the Vendor for the given user.

        :param request: Request object, or object with `session` (dict with user_id-key and value)
         and `user` (User instance) attributes.
        :param event: Event to get Vendor from. Should be the actual event (and not one that has source_db set).
        :return: A Vendor, or None.
        :rtype: Vendor|None
        """
        if event.multiple_vendors_per_user and "vendor_id" in request.session:
            match = {"id": request.session["vendor_id"]}
        else:
            match = event.get_user_query(request.user)
            match["person__isnull"] = True
        try:
            database = event.get_real_database_alias()
            source_event = event.get_real_event()
            if source_event != event:
                warnings.warn("Wrong event given to get_vendor", stacklevel=2)
            return cls.objects.using(database).get(event=source_event, **match)
        except cls.DoesNotExist:
            return None

    @classmethod
    def get_or_create_vendor(cls, request, event):
        """
        If `create` is truthy and a vendor does not exist, one is implicitly created.

        :return:
        """
        if event.multiple_vendors_per_user and "vendor_id" in request.session:
            match = {"id": request.session["vendor_id"]}
            multi = True
        else:
            match = {"user": request.user, "person__isnull": True}
            multi = False

        try:
            return cls.objects.get(event=event, **match)
        except cls.DoesNotExist:
            if multi:
                raise ValueError("Cannot automatically create user in multi-vendor environment")
            return cls.objects.create(event=event, user=request.user)

    @classmethod
    def has_accepted(cls, request, event):
        vendor = cls.get_vendor(request, event)
        if not vendor:
            return False
        return vendor.terms_accepted is not None

    _base_dict = model_dict_fn(
        'id',
        terms_accepted=lambda self: format_datetime(self.terms_accepted) if self.terms_accepted is not None else None,
    )
    _dict_by_user = model_dict_fn(
        username=lambda self: self.user.username,
        name=lambda self: "%s %s" % (self.user.first_name, self.user.last_name),
        missing_name=lambda self: self.user.first_name.strip() == "" or self.user.last_name.strip() == "",
        email=lambda self: self.user.email,
        phone=lambda self: UserAdapter.phone(self.user),
        __extend=_base_dict
    )
    _dict_by_person = model_dict_fn(
        owner=lambda self: self.user.username,
        name=lambda self: self.person.full_name(),
        missing_name=lambda self: self.user.first_name.strip() == "" or self.user.last_name.strip() == "",
        email=lambda self: self.person.email,
        phone=lambda self: self.person.phone,
        __extend=_base_dict
    )

    def as_dict(self):
        if self.person is not None:
            return self._dict_by_person()
        return self._dict_by_user()


def validate_positive(value):
    if value < 0.0:
        raise ValidationError(_(u"Value cannot be negative"))


# Monetary account, not related to user.
class Account(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    name = models.CharField(max_length=256)
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal(0))
    allow_negative_balance = models.BooleanField(default=False)

    def __str__(self):
        return "{self.name} ({self.event}): {self.balance}".format(self=self)

    @property
    def balance_cents(self):
        return decimal_to_transport(self.balance)

    @property
    def name_balance(self):
        currency = settings.KIRPPU_CURRENCY["raw"]
        value = currency[0] + str(self.balance) + currency[1]
        return "{} ({})".format(self.name, value)

    as_dict = model_dict_fn(
        "id",
        "name",
        "balance_cents",
        "allow_negative_balance",
    )

    class Meta:
        constraints = [
            models.CheckConstraint(condition=(
                models.Q(allow_negative_balance=True) | models.Q(balance__gte=0)
            ), name="balance_negativity")
        ]


class Box(models.Model):

    description = models.CharField(max_length=256)
    representative_item = models.ForeignKey("Item", on_delete=models.CASCADE, related_name="+")
    box_number = models.IntegerField(blank=True, null=True, db_index=True)
    bundle_size = models.IntegerField(default=1, help_text="How many items are sold in a bundle")

    def __str__(self):
        if self.box_number is None:
            return "id={id} ({description})".format(id=self.id, description=self.description)
        else:
            return "#{box_number} (id={id}) ({description})".format(
                box_number=self.box_number,
                id=self.id,
                description=self.description
            )

    as_public_dict = model_dict_fn(
        "description",
        "bundle_size",
        box_id="pk",
        item_price=lambda self: str(self.get_price_fmt()),
        item_count=lambda self: self.get_item_count(),
        item_type=lambda self: self.get_item_type_for_display(),
        item_adult=lambda self: self.get_item_adult(),
    )

    as_dict = model_dict_fn(
        "box_number",
        item_price=lambda self: self._get_representative_item().price_cents,
        __extend=as_public_dict
    )

    # Functions to determine common state for box item_set states.
    # ResultState : Callable(item_set->state_set)
    ITEM_SET_REDUCED_STATE = {
        "AD": lambda s: s == {"AD"},
        "BR": lambda s: s == {"BR"},
        "ST": lambda s: "ST" in s,
        "SO": lambda s: "SO" in s and "ST" not in s,
        "CO": lambda s: "CO" in s and "ST" not in s and "SO" not in s and "RE" not in s,
        "RE": lambda s: "RE" in s and "ST" not in s and "SO" not in s,
    }

    @property
    def code(self):
        return self.representative_item.code

    def get_vendor(self):
        """
        Gets the vendor of the box

        :return: Vendor object
        :rtype: Vendor
        """
        first_item = self._get_representative_item()
        return first_item.vendor

    def get_vendor_id(self):
        """
        Gets the vendor id of the box

        :return: Vendor
        :rtype: Decimal
        """
        first_item = self._get_representative_item()
        return first_item.vendor.id

    def get_items(self):
        """
        Gets items in the box.

        :return: List of Item of objects
        :rtype: Array
        """
        items = Item.objects.filter(box=self.id, hidden=False)
        return items

    def get_representative_item(self):
        return self._get_representative_item()

    @short_description(_("Price"))
    def get_price(self):
        return self._get_representative_item().price

    def get_price_fmt(self):
        """
        Gets the price of the items in the box

        :return: Price
        :rtype: Decimal
        """
        first_item = self._get_representative_item()
        return first_item.price_fmt

    @short_description(_("Item count"))
    def get_item_count(self):
        """
        Gets the number of items in the box.

        :return: Number of items in the box.
        :rtype: Decimal
        """
        item_count = Item.objects.filter(box=self.id).exclude(hidden=True).count()
        return item_count

    def get_item_type(self):
        """
        Gets the type of the items in the box.

        :return: Number of items in the box.
        :rtype: Decimal
        """
        first_item = self._get_representative_item()
        return first_item.itemtype

    @short_description(_("Item type"))
    def get_item_type_for_display(self):
        """
        Gets the type of the items in the box for display purpose

        :return: Number of items in the box.
        :rtype: Decimal
        """
        first_item = self._get_representative_item()
        return first_item.get_itemtype_display()

    def get_item_adult(self):
        """
        Gets the adult status of the items in the box

        :return: Number of items in the box.
        :rtype: Decimal
        """
        first_item = self._get_representative_item()
        return first_item.adult

    @short_description(_("Adult material"))
    def get_item_adult_for_display(self):
        return self._get_representative_item().get_adult_display()

    def is_hidden(self):
        """
        Checks if this box is hidden.

        The box is hidden if all the items within the box are hidden.

        :return: True if the box is hidden
        :rtype: bool
        """
        return self._get_representative_item().hidden

    def set_hidden(self, value):
        Item.objects.filter(box=self).update(hidden=value)

    def is_printed(self):
        """
        Checks if this box is printed.

        The box is printed if all the items within the box are printed.

        :return: True if the box is printed
        :rtype: bool
        """
        return self._get_representative_item().printed

    def set_printed(self, value):
        Item.objects.filter(box=self).update(printed=value)

    def _get_representative_item(self):
        return self.representative_item

    def assign_box_number(self):
        if self.box_number is None:
            with transaction.atomic():
                box_state = (
                    Box.objects
                       .filter(representative_item__vendor__event=self.representative_item.vendor.event)
                       .aggregate(last_number=models.Max("box_number"))
                )
                new_number = (box_state["last_number"] or 0) + 1

                self.box_number = new_number
                self.save(update_fields=["box_number"])

    @classmethod
    def new(cls, **kwargs):
        """
        Construct new Box and Item and generate its barcode.

        :param kwargs: Item Constructor arguments
        :return: New stored Box object with calculated code.
        :rtype: Box
        """
        with transaction.atomic():
            item_title = kwargs.pop("name")
            description = kwargs.pop("description")
            count = kwargs.pop("count")
            bundle_size = kwargs.pop("bundle_size")

            representative_item = Item.new(
                name=item_title,
                **kwargs
            )
            obj = cls(
                description=description,
                representative_item=representative_item,
                bundle_size=bundle_size,
            )
            obj.full_clean()
            obj.save()

            representative_item.box = obj
            representative_item.save(
                update_fields=["box"],
            )

            # Create rest of the items for the box.
            for i in range(count - 1):
                Item.new(
                    name=item_title,
                    box=obj,
                    no_code=True,
                    **kwargs
                )

        return obj


class ItemType(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    order = models.IntegerField()
    title = models.CharField(max_length=255)

    class Meta:
        unique_together = (
            ("event", "order"),
        )

    def __str__(self):
        return self.title + " id=" + str(self.id)

    def __repr__(self):
        return u"ItemType(order={order}, title={title})".format(
            order=self.order,
            title=repr(self.title)
        )

    @classmethod
    def as_tuple(cls, event):
        query = cls.objects.filter(event=event)
        return query.order_by("order").values_list("id", "title")


class Item(models.Model):
    ADVERTISED = "AD"
    BROUGHT = "BR"
    STAGED = "ST"
    SOLD = "SO"
    MISSING = "MI"
    RETURNED = "RE"
    COMPENSATED = "CO"

    STATE = (
        (ADVERTISED, _(u"Advertised")),
        (BROUGHT, _(u"Brought to event")),
        (STAGED, _(u"Staged for selling")),
        (SOLD, _(u"Sold")),
        (MISSING, _(u"Missing")),
        (RETURNED, _(u"Returned to vendor")),
        (COMPENSATED, _(u"Compensated to vendor")),
    )

    TYPE_TINY = "tiny"
    TYPE_SHORT = "short"
    TYPE_LONG = "long"
    TYPE = (
        (TYPE_TINY, _(u"Tiny price tag")),
        (TYPE_SHORT, _(u"Short price tag")),
        (TYPE_LONG, _(u"Long price tag")),
    )

    ADULT_YES = "yes"
    ADULT_NO = "no"
    ADULT = (
        (ADULT_YES, _(u"Item allowed only to adult shoppers, contains porn etc.")),
        (ADULT_NO, _(u"Item allowed to all shoppers")),
    )

    # Count of digits after decimal separator.
    FRACTION_LEN = 2

    # Denominator, a power of 10, for representing numbers with FRACTION_LEN digits.
    FRACTION = 10 ** FRACTION_LEN

    # Number "one", represented with precision defined by FRACTION(_LEN).
    Q_EXP = Decimal(FRACTION).scaleb(-FRACTION_LEN)

    CODE_BITS = 40

    code = models.CharField(
        max_length=16,
        blank=True,
        null=True,
        db_index=True,
        unique=True,
        help_text=_(u"Barcode content of the product"),
    )
    name = models.CharField(max_length=256, blank=True)
    price = models.DecimalField(max_digits=8, decimal_places=2, validators=[validate_positive])
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE)
    state = models.CharField(
        choices=STATE,
        max_length=8,
        default=ADVERTISED
    )
    type = models.CharField(
        choices=TYPE,
        max_length=8,
        default=TYPE_SHORT
    )
    itemtype = models.ForeignKey(ItemType, on_delete=models.CASCADE)
    adult = models.CharField(
        choices=ADULT,
        max_length=8,
        default=ADULT_NO
    )
    abandoned = models.BooleanField(default=False)

    # Has the user marked this item as printed?
    # Affects whether the item is shown in print view or not.
    printed = models.BooleanField(default=False)

    # Affects whether the item is shown at all.
    hidden = models.BooleanField(default=False)
    box = models.ForeignKey(Box, on_delete=models.CASCADE, blank=True, null=True)

    lost_property = models.BooleanField(
        default=False,
        help_text=_(u"Forgotten or lost property/item"),
    )

    class Meta:
        permissions = (
            ("register_override", _("Can register items after registration is closed")),
        )

    def __str__(self):
        if self.box_id is None:
            code_or_box = self.code
        else:
            code_or_box = f"box {self.box.box_number or '?'}"
            if self.code:
                code_or_box += " / " + self.code
        return f"{self.name} ({code_or_box})"

    as_dict = model_dict_fn(
        "code",
        "name",
        "state",
        "abandoned",
        "hidden",
        price="price_cents",
        vendor="vendor_id",
        state_display="get_state_display",
        itemtype="itemtype_id",
        itemtype_display="get_itemtype_display",
        adult=lambda self: self.adult == Item.ADULT_YES,
    )

    as_public_dict = model_dict_fn(
        "vendor_id",
        "code",
        "name",
        "type",
        "adult",
        "is_locked",
        price=lambda self: str(self.price_fmt).replace(".", ","),
    )

    def get_itemtype_display(self):
        return self.itemtype.title

    @property
    def price_cents(self):
        return decimal_to_transport(self.price)

    @property
    def price_fmt(self):
        """
        Get Item price formatted human-printable:
        If the value is exact integer, returned value contains only the integer part.
        Else, the value precision is as defined with FRACTION variable.

        :return: Decimal object formatted for humans.
        :rtype: Decimal
        """
        return self.price_fmt_for(self.price)

    @staticmethod
    def price_fmt_for(value: Decimal) -> Decimal:
        # If value is exact integer, return only the integer part.
        int_value = value.to_integral_value()
        if int_value == value:
            return int_value
        # Else, display digits with precision from FRACTION*.
        return value.quantize(Item.Q_EXP)

    @classmethod
    def new(cls, *args, no_code: bool = False, **kwargs):
        """
        Construct new Item and generate its barcode.

        :param args: Item Constructor arguments.
        :param kwargs: Item Constructor arguments.
        :param no_code: If True, no code will be generated for the Item.
        :return: New stored Item object with calculated code.
        :rtype: Item
        """
        obj = cls(*args, **kwargs)
        if not no_code:
            obj.code = Item.gen_barcode()
        obj.full_clean()
        obj.save()

        ItemStateLog.objects.create(item=obj, old_state="", new_state=obj.state)

        return obj

    @classmethod
    def gen_barcode(cls):
        """
        Generate new random barcode for item.

        Format of the code:
            random:     36 bits
            checksum:    4 bits
            -------------------
            total:      40 bits


        :return: The newly generated code.
        :rtype: str
        """
        checksum_bits = 4
        data_bits = cls.CODE_BITS - checksum_bits
        key = None
        i_max = 2 ** data_bits - 1
        while key is None or Item.objects.filter(code=key).exists():
            key = b32_encode(
                pack([
                    (data_bits, random.randint(1, i_max)),
                ], checksum_bits=checksum_bits)
            )
        return key

    def is_locked(self):
        return self.state != Item.ADVERTISED

    @staticmethod
    def get_item(**kwargs):
        """
        Get Item by barcode.

        :rtype: Item
        :raise Item.DoesNotExist: If no Item matches the code.
        """
        return Item.objects.annotate(vendor_event=F("vendor__event__id")).get(**kwargs)

    @staticmethod
    def get_item_for_update(**kwargs):
        return Item.objects.annotate(vendor_event=F("vendor__event__id")).select_for_update().get(**kwargs)

    @classmethod
    def is_item_barcode(cls, text):
        """
        Do a simple test whether given string could be a Item barcode.

        :param text: String to test.
        :type text: str
        :return: True if the string could be a (full) barcode. False if not.
        :rtype: bool
        """
        return text.isalnum() and text.isupper() and len(text) == cls.CODE_BITS / 5

    @classmethod
    def get_brought_count(cls, event: Event, vendor: Vendor):
        if event.box_as_single_brought_item:
            return Item.objects.filter(vendor=vendor, state=Item.BROUGHT).filter(
                Q(box__isnull=True) | Q(box__representative_item__id=F("pk"))).count()
        else:
            return Item.objects.filter(vendor=vendor, state=Item.BROUGHT).count()


class UIText(models.Model):
    def __str__(self):
        return self.identifier

    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    identifier = models.CharField(
        max_length=16,
        help_text=_(u"Identifier of the textitem")
    )
    text = models.CharField(
        blank=True,
        max_length=16384,
        help_text=_(u"Textitem in UI")
    )

    class Meta:
        unique_together = (("event", "identifier"),)

    @property
    def text_excerpt(self):
        return shorten_text(self.text)

    @classmethod
    def get_text(cls, event, identifier, default=None):
        try:
            return UIText.objects.values_list("text", flat=True).get(event=event, identifier=identifier)
        except UIText.DoesNotExist:
            return default

    def get_absolute_url(self):
        return reverse("kirppu:vendor_view", kwargs={"event_slug": self.event.slug}) + f"?preview={self.id}"


class Counter(models.Model):
    PRIVATE_KEY_ALPHABET = string.ascii_letters + string.digits

    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    identifier = models.CharField(
        max_length=32,
        blank=True,
        null=False,
        help_text=_(u"Registration identifier of the counter")
    )
    name = models.CharField(
        max_length=64,
        blank=True,
        null=False,
        help_text=_(u"Common name of the counter")
    )
    private_key = models.CharField(
        max_length=32,
        blank=True,
        null=True,
        default=None,
        unique=True,
    )
    default_store_location = models.ForeignKey(
        Account,
        on_delete=models.CASCADE,
        help_text=_("Where the cash will be stored to and received from when using this counter."),
    )

    def clean_fields(self, exclude=None):
        super().clean_fields(exclude=exclude)
        if (exclude is None or "default_store_location" not in exclude) \
                and self.default_store_location.event != self.event:
            msg = _("Counter and default_store_location must be in same Event.")
            if exclude and "default_store_location" in exclude:
                raise ValidationError(msg)
            else:
                raise ValidationError({
                    "default_store_location": msg,
                })

    def assign_private_key(self, for_lock=False):
        length = self._meta.get_field("private_key").max_length

        if for_lock:
            # Make space for lock character.
            length -= 1

        retries = -1
        while retries < 10:
            retries += 1
            candidate = "".join(random.choice(self.PRIVATE_KEY_ALPHABET) for _ in range(length))
            if for_lock:
                candidate = "!" + candidate

            if Counter.objects.filter(private_key=candidate).exists():
                continue
            self.private_key = candidate
            try:
                self.save(update_fields=("private_key",))
            except IntegrityError:
                pass
            else:
                return
        raise KeyError("Retry-limit reached")

    @short_description(_("Is in use?"))
    def is_in_use(self):
        return self.private_key is not None and not self.private_key.startswith("!")
    is_in_use.boolean = True

    @short_description(_("Is locked?"))
    def is_locked(self):
        return self.private_key is not None and self.private_key.startswith("!")
    is_locked.boolean = True

    class Meta:
        unique_together = (
            ("event", "identifier"),
        )

    def __str__(self):
        return u"{1} ({0})".format(self.identifier, self.name)


class ReceiptItem(models.Model):
    ADD = "ADD"
    REMOVED_LATER = "RL"
    REMOVE = "DEL"

    ACTION = (
        (ADD, _(u"Added to receipt")),
        (REMOVED_LATER, _(u"Removed later")),
        (REMOVE, _(u"Removed from receipt")),
    )

    item = models.ForeignKey(Item, on_delete=models.CASCADE)
    receipt = models.ForeignKey("Receipt", on_delete=models.CASCADE)
    action = models.CharField(choices=ACTION, max_length=16, default=ADD)
    add_time = models.DateTimeField(auto_now_add=True)

    def as_dict(self):
        ret = {
            "action": self.action,
        }
        ret.update(self.item.as_dict())
        return ret

    def __str__(self):
        return str(self.item)


class Receipt(models.Model):
    PENDING = "PEND"
    FINISHED = "FINI"
    SUSPENDED = "SUSP"
    ABORTED = "ABRT"

    STATUS = (
        (PENDING, _(u"Not finished")),
        (FINISHED, _(u"Finished")),
        (SUSPENDED, _(u"Suspended")),
        (ABORTED, _(u"Aborted")),
    )

    TYPE_PURCHASE = "PURCHASE"
    TYPE_COMPENSATION = "COMPENSATION"
    TYPE_TRANSFER = "TRANSFER"

    TYPES = (
        (TYPE_PURCHASE, _(u"Purchase")),
        (TYPE_COMPENSATION, _(u"Compensation")),
        (TYPE_TRANSFER, _("Transfer")),
    )

    items = models.ManyToManyField(Item, through=ReceiptItem)
    status = models.CharField(choices=STATUS, max_length=16, default=PENDING)
    total = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    clerk = models.ForeignKey(Clerk, on_delete=models.CASCADE)
    counter = models.ForeignKey(Counter, on_delete=models.CASCADE)
    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(null=True, blank=True)
    type = models.CharField(choices=TYPES, max_length=16, default=TYPE_PURCHASE)

    # Relevant only for vendor-specific receipts, i.e. TYPE_COMPENSATION.
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, null=True, blank=True)

    # Relevant only for TYPE_TRANSFER receipts.
    src_account = models.ForeignKey(Account, on_delete=models.CASCADE,
                                    related_name="src_receipts", null=True, blank=True)
    dst_account = models.ForeignKey(Account, on_delete=models.CASCADE,
                                    related_name="dst_receipts", null=True, blank=True)

    def items_list(self):
        return [
            self._item_dict(row)
            for row in self.receiptitem_set.select_related("item", "item__itemtype")
                .annotate(box_number=F("item__box__box_number"),
                          box_code=F("item__box__representative_item__code"),
                          box_description=F("item__box__description"))
                .order_by("add_time")
        ]

    @staticmethod
    def _item_dict(row):
        r = row.as_dict()
        if row.item.box_id is not None:
            r.update(dict(
                box_number=row.box_number,
                box_code=row.box_code,
                description=row.box_description,
            ))
        return r

    def row_list(self):
        r = self.items_list()
        r.extend([row.as_dict() for row in self.extra_rows.all()])
        return r

    @property
    def total_cents(self):
        return decimal_to_transport(self.total)

    as_dict = model_dict_fn(
        "status",
        "type",
        id="pk",
        total="total_cents",
        status_display=lambda self: self.get_status_display(),
        start_time=lambda self: format_datetime(self.start_time) if self.start_time is not None else None,
        end_time=lambda self: format_datetime(self.end_time) if self.end_time is not None else None,
        clerk=lambda self: self.clerk.as_dict(),
        counter=lambda self: self.counter.name,
        notes=lambda self: [note.as_dict() for note in self.receiptnote_set.order_by("timestamp")] if self.pk else [],
        type_display=lambda self: self.get_type_display(),
    )

    as_transfer_dict = model_dict_fn(
        src_account=lambda self: self.src_account.name,
        src_account_balance=lambda self: self.src_account.name_balance,
        dst_account=lambda self: self.dst_account.name,
        dst_account_balance=lambda self: self.dst_account.name_balance,
        __extend=as_dict,
    )

    def calculate_total(self):
        result = ReceiptItem.objects.filter(action=ReceiptItem.ADD, receipt=self)\
            .aggregate(price_total=Sum("item__price"))
        extras = ReceiptExtraRow.objects.filter(receipt=self).aggregate(extras_total=Sum("value"))

        price_total = result["price_total"]
        extras_total = extras["extras_total"]

        self.total = (price_total or 0) + (extras_total or 0)
        return self.total

    def __str__(self):
        return "{type}: {start} / {clerk}".format(
            type=self.get_type_display(),
            start=datetime_iso_human(self.start_time),
            clerk=str(self.clerk),
        )

    class Meta:
        permissions = (
            ("view_accounting", "View accounting data"),
        )
        constraints = [
            models.CheckConstraint(condition=(
                models.Q(type="COMPENSATION", vendor__isnull=False)) | (
                ~models.Q(type="COMPENSATION") & models.Q(vendor__isnull=True)
            ), name="vendor_id_nullity"),
            models.CheckConstraint(condition=(
                ~models.Q(type="TRANSFER") | models.Q(src_account__isnull=False, dst_account__isnull=False)
            ), name="account_id_nullity"),
        ]


class ReceiptExtraRow(models.Model):
    TYPE_PROVISION = "PRO"
    TYPE_PROVISION_FIX = "PRO_FIX"
    TYPES = (
        (TYPE_PROVISION, _("Provision")),
        (TYPE_PROVISION_FIX, _("Provision balancing")),
    )

    type = models.CharField(max_length=8, choices=TYPES)
    value = models.DecimalField(max_digits=8, decimal_places=2)
    receipt = models.ForeignKey(Receipt, on_delete=models.CASCADE, related_name="extra_rows")

    as_dict = model_dict_fn(
        "type",
        type_display=lambda self: self.get_type_display(),
        action=lambda _: "EXTRA",  # Same key as in ReceiptItem.action.
        value="value_cents",
    )

    @property
    def value_cents(self):
        return decimal_to_transport(self.value)

    def __str__(self):
        return "{}: {} ({})".format(self.get_type_display(), self.value, self.receipt)


class AbstractNote(models.Model):
    class Meta:
        abstract = True

    timestamp = models.DateTimeField(auto_now_add=True)
    clerk = models.ForeignKey(Clerk, on_delete=models.CASCADE)
    text = models.TextField()

    _as_dict = model_dict_fn(
        "text",
        timestamp=lambda self: format_datetime(self.timestamp) if self.timestamp is not None else None,
        clerk=lambda self: self.clerk.as_dict(),
    )


class ReceiptNote(AbstractNote):
    receipt = models.ForeignKey(Receipt, on_delete=models.CASCADE)

    def __str__(self):
        return "{0} / {1} @ r {2}".format(
            str(self.timestamp),
            str(self.clerk),
            str(self.receipt_id)
        )

    as_dict = AbstractNote._as_dict


class VendorNote(AbstractNote):
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE)
    erased = models.BooleanField(default=False)

    def __str__(self):
        return "{0} / {1} @ v {2}".format(
            str(self.timestamp),
            str(self.clerk),
            str(self.vendor_id),
        )

    as_dict = model_dict_fn(
        "id",
        "erased",
        __extend=AbstractNote._as_dict,
    )


class ItemStateLogManager(models.Manager):
    @staticmethod
    def _make_log_state(request, item, doit):
        from .ajax_util import get_clerk, get_counter, AjaxError
        counter = None
        clerk = None
        try:
            clerk = get_clerk(request)
            counter = get_counter(request)
        except AjaxError:
            if request.user.is_authenticated:
                try:
                    if item is not None:
                        event_id = item.vendor.event_id
                        clerk_set = Clerk.objects.filter(event_id=event_id)
                    else:
                        # Will probably raise MultipleObjectsReturned.
                        clerk_set = Clerk.objects
                    clerk = clerk_set.get(user=request.user)
                except Clerk.DoesNotExist:
                    clerk = None

        return doit(counter, clerk)

    def log_state(self, item, new_state, request):
        def actual(counter, clerk):
            return self.create(
                item=item,
                old_state=item.state,
                new_state=new_state,
                clerk=clerk,
                counter=counter)
        return self._make_log_state(request, item, actual)

    def log_states(self, item_set, new_state, request):
        def actual(counter, clerk):
            objs = [
                ItemStateLog(
                    item=item,
                    old_state=item.state,
                    new_state=new_state,
                    clerk=clerk,
                    counter=counter
                )
                for item in item_set
            ]
            return self.bulk_create(objs)
        return self._make_log_state(request, None, actual)


class ItemStateLog(models.Model):
    objects = ItemStateLogManager()

    item = models.ForeignKey(Item, on_delete=models.CASCADE)
    time = models.DateTimeField(auto_now_add=True)
    old_state = models.CharField(
        choices=Item.STATE,
        max_length=2,
    )
    new_state = models.CharField(
        choices=Item.STATE,
        max_length=2,
    )

    clerk = models.ForeignKey(Clerk, null=True, on_delete=models.CASCADE)
    counter = models.ForeignKey(Counter, null=True, on_delete=models.CASCADE)

    def __repr__(self):
        return "<ItemStateLog item={} time={} old={} new={} clerk={} counter={}>".format(
            self.item.code,
            self.time,
            self.old_state,
            self.new_state,
            self.clerk.pk if self.clerk is not None else "",
            self.counter.pk if self.counter is not None else "",
        )

    class Meta:
        permissions = (
            ("view_statistics", "Can see statistics"),
        )


def default_temporary_access_permit_expiry(minutes: int = None):
    minutes = minutes or settings.KIRPPU_SHORT_CODE_EXPIRATION_TIME_MINUTES
    return timezone.now() + datetime.timedelta(minutes=minutes)


class TemporaryAccessPermit(models.Model):
    STATE_UNUSED = "new"
    STATE_IN_USE = "use"
    STATE_EXHAUSTED = "exh"
    STATE_INVALIDATED = "inv"
    STATES = (
        (STATE_UNUSED, _("Unused")),
        (STATE_IN_USE, _("In use")),
        (STATE_EXHAUSTED, _("Exhausted")),
        (STATE_INVALIDATED, _("Invalidated")),
    )

    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, db_index=True)
    creation_time = models.DateTimeField(auto_now_add=True)
    expiration_time = models.DateTimeField(default=default_temporary_access_permit_expiry)
    state = models.CharField(choices=STATES, default=STATE_UNUSED, max_length=8)
    creator = models.ForeignKey(Clerk, on_delete=models.DO_NOTHING)
    short_code = models.CharField(max_length=128, unique=True, validators=[MinLengthValidator(4)])

    def __str__(self):
        return "{vendor} ({state} / {expiry})".format(
            vendor=UserAdapter.print_name(self.vendor.user),
            state=self.get_state_display(),
            expiry=self.expiration_time,
        )


class TemporaryAccessPermitLog(models.Model):
    ACTION_ADD = "add"
    ACTION_TRY = "try"
    ACTION_USE = "use"
    ACTION_DELETE = "del"
    ACTION_INVALIDATE = "inv"
    ACTIONS = (
        (ACTION_ADD, _("Add")),
        (ACTION_TRY, _("Try using")),
        (ACTION_USE, _("Use")),
        (ACTION_DELETE, _("Delete")),
        (ACTION_INVALIDATE, _("Invalidate")),
    )

    permit = models.ForeignKey(TemporaryAccessPermit, on_delete=models.DO_NOTHING, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    action = models.CharField(max_length=16, choices=ACTIONS)
    address = models.CharField(max_length=512)
    peer = models.CharField(max_length=1024)

    def __str__(self):
        return "{action} ({code}) / {vendor} / {timestamp}".format(
            action=self.get_action_display(),
            code=self.permit.short_code,
            vendor=self.permit.vendor,
            timestamp=self.timestamp,
        )
