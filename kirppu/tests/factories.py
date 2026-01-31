# -*- coding: utf-8 -*-
from decimal import Decimal

import factory.django
from django.utils.timezone import now, timedelta

from kirppu.models import (
    Account,
    Box,
    Clerk,
    Counter,
    Event,
    EventPermission,
    Item,
    ItemType,
    Person,
    Receipt,
    ReceiptItem,
    Vendor,
)
from kirppuauth.models import User

Factory = factory.django.DjangoModelFactory

__all__ = [
    "AccountFactory",
    "UserFactory",
    "EventFactory",
    "EventPermissionFactory",
    "VendorFactory",
    "CounterFactory",
    "ClerkFactory",
    "ItemTypeFactory",
    "ItemFactory",
    "PersonFactory",
    "ReceiptFactory",
    "ReceiptItemFactory",
    "BoxFactory",
]


class UserFactory(Factory[User]):
    class Meta:
        model = User

    DEFAULT_PASSWORD = "AjU2k3Pzpdpz5yf5sjZn9p56"

    username = factory.Faker("user_name")
    phone = factory.Faker("phone_number")
    first_name = factory.Faker("first_name")
    last_name = factory.Faker("last_name")

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        manager = cls._get_manager(model_class)
        kwargs.pop("DEFAULT_PASSWORD")
        obj = model_class(*args, **kwargs)
        if not obj.password:
            obj.set_password(cls.DEFAULT_PASSWORD)
        obj.save(force_insert=True, using=manager.db)
        return obj


class EventFactory(Factory[Event]):
    class Meta:
        model = Event
        exclude = ("_slug", "_slug_seq")

    _slug = factory.Faker("slug")
    _slug_seq = factory.Sequence(lambda a: str(a))
    slug = factory.LazyAttribute(lambda a: a._slug + "-" + a._slug_seq)

    name = factory.LazyAttribute(lambda a: a.slug.replace("-", " ").title())
    start_date = (now() + timedelta(days=2)).date()
    end_date = (now() + timedelta(days=3)).date()

    registration_end = now() + timedelta(days=1)
    registration_disabled = False
    checkout_active = True


class EventPermissionFactory(Factory[EventPermission]):
    class Meta:
        model = EventPermission


class VendorFactory(Factory[Vendor]):
    class Meta:
        model = Vendor

    user = factory.SubFactory(UserFactory)
    terms_accepted = factory.LazyFunction(now)
    event = factory.SubFactory(EventFactory)


# Monetary account, not related to user.
class AccountFactory(Factory[Account]):
    class Meta:
        model = Account

    event = factory.SubFactory(EventFactory)
    name = factory.Faker("sentence", nb_words=2)


class CounterFactory(Factory[Counter]):
    class Meta:
        model = Counter
    event = factory.SubFactory(EventFactory)
    identifier = factory.Sequence(lambda n: "counter_{}".format(n))
    name = factory.LazyAttribute(lambda a: a.identifier.capitalize())
    private_key = "secret"
    default_store_location = factory.SubFactory(AccountFactory)


class ClerkFactory(Factory[Clerk]):
    class Meta:
        model = Clerk

    event = factory.SubFactory(EventFactory)
    user = factory.SubFactory(UserFactory)

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        manager = cls._get_manager(model_class)
        obj = manager.create(*args, **kwargs)
        obj.generate_access_key()
        obj.save(update_fields=("access_key",))
        return obj


class ItemTypeFactory(Factory[ItemType]):
    class Meta:
        model = ItemType
    event = factory.SubFactory(EventFactory)
    order = factory.Sequence(lambda n: n)
    title = factory.Faker("sentence", nb_words=2)


class ItemFactory(Factory[Item]):
    class Meta:
        model = Item
    vendor = factory.SubFactory(VendorFactory)
    price = Decimal("1.25")
    code = factory.LazyFunction(lambda: Item.gen_barcode())
    name = factory.Faker("sentence", nb_words=2)
    itemtype = factory.SubFactory(ItemTypeFactory)


class PersonFactory(Factory[Person]):
    class Meta:
        model = Person
    first_name = factory.Faker("first_name")
    last_name = factory.Faker("last_name")
    phone = factory.Faker("phone_number")
    email = factory.Faker("email")


class ReceiptFactory(Factory[Receipt]):
    class Meta:
        model = Receipt

    counter = factory.SubFactory(CounterFactory)
    clerk = factory.SubFactory(ClerkFactory)


class ReceiptItemFactory(Factory[ReceiptItem]):
    class Meta:
        model = ReceiptItem

    item = factory.SubFactory(ItemFactory)
    receipt = factory.SubFactory(ReceiptFactory)


class BoxFactory(Factory[Box]):
    """
    Can be used in two forms:
        BoxFactory(vendor=..., item_count=...)
        BoxFactory(adopt=True, items=...)

    First creates random items for given vendor. Second adopts the items into the Box.
    Both return newly created Box instance.
    """
    class Meta:
        model = Box

    description = factory.Faker("sentence", nb_words=3)
    box_number = factory.Sequence(lambda n: n + 1)

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        manager = cls._get_manager(model_class)

        if kwargs.get("adopt", False):
            kwargs.pop("adopt")
            items = kwargs.pop("items")

            kwargs.setdefault("representative_item", items[0])
            obj = manager.create(*args, **kwargs)

            for i in items:
                i.box = obj
                i.save(update_fields=("box",))

            return obj

        vendor = kwargs.pop("vendor")
        item_count = kwargs.pop("item_count")

        representative_item = ItemFactory.create(vendor=vendor)

        kwargs["representative_item"] = representative_item
        obj = manager.create(*args, **kwargs)

        representative_item.box = obj
        representative_item.save(update_fields=("box",))

        ItemFactory.create_batch(
            item_count - 1,
            vendor=vendor,
            box=obj,
            price=representative_item.price,
            itemtype=representative_item.itemtype
        )

        return obj
