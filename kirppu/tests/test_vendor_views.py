# -*- coding: utf-8 -*-
import typing

import factory
from django.conf import settings
from django.test import TestCase, override_settings

from ..models import Box, Item
from . import ResultMixin
from .factories import *


class ApiFactory(factory.Factory[dict]):
    # Factory that can be used to generate data dicts for django's test Client.
    class Meta:
        abstract = True
        model = dict
        strategy = factory.CREATE_STRATEGY


class ApiItemFactory(ApiFactory):
    name = factory.Faker("sentence", nb_words=3)
    price = "1.50"
    tag_type = "short"
    suffixes = ""
    item_type = ""
    adult = False


class ApiBoxFactory(ApiItemFactory):
    count = 5
    bundle_size = 1

    class Meta:
        rename = {"name": "description"}


@override_settings(LANGUAGES=(("en", "English"),))
class _VendorTest(TestCase, ResultMixin):
    def setUp(self):
        self.event = EventFactory.create()
        self.type = ItemTypeFactory.create(event=self.event)
        self.client.cookies.load({settings.LANGUAGE_COOKIE_NAME: 'en'})

    def _defaults(self):
        self.vendor = VendorFactory.create(event=self.event)
        self.client.force_login(self.vendor.user)
        # self.api = Api(client=self.c, event=self.event)


def count(fn: typing.Callable, iterable: typing.Iterable) -> int:
    r = 0
    for i in iterable:
        if fn(i):
            r += 1
    return r


class InitialAddTest(_VendorTest):

    # region Initial Items

    def test_register_vendor_and_items(self):
        vendor = VendorFactory.create(terms_accepted=None, event=self.event)

        if not self.client.login(username=vendor.user.username, password=UserFactory.DEFAULT_PASSWORD):
            raise RuntimeError("Could not log in.")

        self.assertEqual("ok", self.assertSuccess(
            self.client.post("/kirppu/%s/vendor/accept_terms" % self.event.slug)).json()["result"])

        data = ApiItemFactory.create(item_type=self.type.id)
        result = self.assertSuccess(
            self.client.post("/kirppu/%s/vendor/item/" % self.event.slug, data=data)).json()

        self.assertEqual(1, len(result))
        self.assertTrue(result[0]["barcode_dataurl"].startswith("data:image/png"))

    def test_register_items_without_terms(self):
        user = UserFactory.create()
        self.client.force_login(user)

        data = ApiItemFactory.create(item_type=self.type.id)
        result = self.client.post("/kirppu/%s/vendor/item/" % self.event.slug, data=data)
        self.assertContains(result, "terms", status_code=400)

    def test_register_items_for_other_event(self):
        self.test_register_vendor_and_items()
        event = EventFactory()

        data = ApiItemFactory.create(item_type=self.type.id)
        result = self.client.post("/kirppu/%s/vendor/item/" % event.slug, data=data)
        self.assertContains(result, "terms", status_code=400)

    def test_register_item_invalid_price(self):
        self._defaults()
        data = ApiItemFactory.create(item_type=self.type.id, price="0")
        result = self.client.post("/kirppu/%s/vendor/item/" % self.event.slug, data=data)
        self.assertContains(result, "Price", status_code=400)

    @override_settings(KIRPPU_MIN_MAX_PRICE=("-100", "400"))
    def test_register_item_invalid_price_negative(self):
        """Negative price should not be allowed even if the configuration says so."""
        self._defaults()
        data = ApiItemFactory.create(item_type=self.type.id, price="-1.00")
        result = self.client.post("/kirppu/%s/vendor/item/" % self.event.slug, data=data)
        self.assertContains(result, "negative", status_code=400)

    @override_settings(KIRPPU_MIN_MAX_PRICE=("0", "400"))
    def test_register_item_zero_price_negative(self):
        self._defaults()
        data = ApiItemFactory.create(item_type=self.type.id, price="0.00")
        result = self.assertSuccess(self.client.post("/kirppu/%s/vendor/item/" % self.event.slug, data=data)).json()
        self.assertEqual(1, len(result))

    def test_register_item_suffixes(self):
        self._defaults()
        data = ApiItemFactory.create(item_type=self.type.id, suffixes="1-10")
        result = self.assertSuccess(self.client.post("/kirppu/%s/vendor/item/" % self.event.slug, data=data)).json()
        self.assertEqual(10, len(result))

    def test_register_item_for_other_event_itemtype(self):
        self.test_register_vendor_and_items()
        event = EventFactory()
        itemtype = ItemTypeFactory.create(event=event)

        data = ApiItemFactory.create(item_type=itemtype.id)
        result = self.client.post("/kirppu/%s/vendor/item/" % self.event.slug, data=data)
        self.assertContains(result, "item type", status_code=400)

    # endregion

    # region Initial Boxes

    def test_register_box(self):
        self._defaults()
        data = ApiBoxFactory.create(item_type=self.type.id)
        result = self.client.post("/kirppu/%s/vendor/box/" % self.event.slug, data=data)
        # Result is html...
        self.assertContains(result, data["description"])
        self.assertEqual(data["count"], Item.objects.count())

    def test_register_box_without_terms(self):
        user = UserFactory.create()
        self.client.force_login(user)

        data = ApiBoxFactory.create(item_type=self.type.id)
        result = self.client.post("/kirppu/%s/vendor/box/" % self.event.slug, data=data)
        self.assertContains(result, "terms", status_code=400)

    def test_register_box_suffixes(self):
        """Uses ItemForm, should not create multiple sets nor try to validate unused field, though."""
        self._defaults()
        data = ApiBoxFactory.create(item_type=self.type.id, suffixes="1-200")
        result = self.client.post("/kirppu/%s/vendor/box/" % self.event.slug, data=data)
        # Result is html...
        self.assertContains(result, data["description"])
        self.assertEqual(data["count"], Item.objects.count())

    def test_register_box_bundle(self):
        self._defaults()
        # 5 bundles, each containing 3 items (== 15 items, but they are not individually listed in system)
        data = ApiBoxFactory.create(item_type=self.type.id, count=5, bundle_size=3)
        result = self.client.post("/kirppu/%s/vendor/box/" % self.event.slug, data=data)
        self.assertContains(result, data["description"])
        self.assertEqual(5, Item.objects.count())

    # endregion


class NoBoxSupportTest(_VendorTest):
    """All Box endpoints should return 404 when the event doesn't have box support."""
    def setUp(self):
        super().setUp()
        self._defaults()
        self.event.use_boxes = False
        self.event.save()

    def test_register_box(self):
        data = ApiBoxFactory.create(item_type=self.type.id)
        result = self.client.post("/kirppu/%s/vendor/box/" % self.event.slug, data=data)
        self.assertResult(result, 404)

    def test_box_list(self):
        BoxFactory(vendor=self.vendor, item_count=3)
        self.assertResult(self.client.get("/kirppu/%s/vendor/boxes/" % self.event.slug),
                          404)

    def _test(self, fn: str, get=False):
        box1 = BoxFactory.create(vendor=self.vendor, item_count=3)
        m = self.client.get if get else self.client.post
        self.assertResult(m("/kirppu/%s/vendor/box/%d/%s" % (self.event.slug, box1.pk, fn)),
                          404)

    def test_print_box(self):
        self._test("print")

    def test_hide_box(self):
        self._test("hide")

    def test_box_content(self):
        self._test("content", get=True)


class ManipulationTest(_VendorTest):
    def setUp(self):
        super().setUp()
        self._defaults()
        self.item = ItemFactory.create(itemtype=self.type, vendor=self.vendor)

    # region Hiding / deleting

    def test_item_hide(self):
        """hide = 'delete'. Hidden item should not be shown in listing."""
        result = self.client.get("/kirppu/%s/vendor/items/" % self.event.slug)
        self.assertEqual(1, len(result.context["items"]))

        self.assertSuccess(self.client.post("/kirppu/%s/vendor/item/%s/hide" % (self.event.slug, self.item.code)))

        result = self.client.get("/kirppu/%s/vendor/items/" % self.event.slug)
        self.assertEqual(0, len(result.context["items"]))

    def test_item_re_hide(self):
        self.test_item_hide()
        self.assertSuccess(self.client.post("/kirppu/%s/vendor/item/%s/hide" % (self.event.slug, self.item.code)))

    def test_box_hide(self):
        """Hidden box should not be shown in listing."""
        data = ApiBoxFactory(item_type=self.type.id)
        self.assertSuccess(self.client.post("/kirppu/%s/vendor/box/" % self.event.slug, data=data))

        result = self.client.get("/kirppu/%s/vendor/boxes/" % self.event.slug)
        self.assertEqual(1, len(result.context["boxes"]))

        pk = Box.objects.get().pk
        self.assertSuccess(self.client.post("/kirppu/%s/vendor/box/%d/hide" % (self.event.slug, pk)))

        result = self.client.get("/kirppu/%s/vendor/boxes/" % self.event.slug)
        self.assertEqual(0, len(result.context["boxes"]))

    # endregion

    # region Marking printed

    def test_item_print(self):
        ItemFactory(itemtype=self.type, vendor=self.vendor)

        self.assertSuccess(self.client.post("/kirppu/%s/vendor/item/%s/to_printed" % (self.event.slug, self.item.code)))
        result = self.assertSuccess(self.client.get("/kirppu/%s/vendor/items/" % self.event.slug))
        self.assertEqual(1, len(result.context["printed_items"]))
        self.assertEqual(1, len(result.context["items"]))

    @override_settings(KIRPPU_COPY_ITEM_WHEN_UNPRINTED=False)
    def test_item_unprint(self):
        self.test_item_print()

        result = self.assertSuccess(
            self.client.post("/kirppu/%s/vendor/item/%s/to_not_printed" % (self.event.slug, self.item.code)))
        self.assertEqual(self.item.code, result.json()["code"])

    @override_settings(KIRPPU_COPY_ITEM_WHEN_UNPRINTED=True)
    def test_item_unprint_copy(self):
        self.test_item_print()

        result = self.assertSuccess(
            self.client.post("/kirppu/%s/vendor/item/%s/to_not_printed" % (self.event.slug, self.item.code)))
        # 1 from setUp, 1 from test_item_print, 1 from copy.
        self.assertEqual(3, Item.objects.filter(vendor=self.vendor).count())
        new_item_code = result.json()["code"]
        self.assertNotEqual(self.item.code, new_item_code)

        result = self.client.get("/kirppu/%s/vendor/items/" % self.event.slug)
        self.assertNotContains(result, self.item.code)
        self.assertContains(result, new_item_code)

    def test_box_print(self):
        box1 = BoxFactory.create(vendor=self.vendor, item_count=3)
        BoxFactory(vendor=self.vendor, item_count=5)

        result = self.assertSuccess(self.client.get("/kirppu/%s/vendor/boxes/" % self.event.slug))
        self.assertEqual(2, count(lambda b: not b.is_printed(), result.context["boxes"]))

        self.assertSuccess(self.client.post("/kirppu/%s/vendor/box/%d/print" % (self.event.slug, box1.pk)))

        result = self.assertSuccess(self.client.get("/kirppu/%s/vendor/boxes/" % self.event.slug))
        self.assertEqual(1, count(lambda b: b.is_printed(), result.context["boxes"]))

    # endregion
