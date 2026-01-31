# -*- coding: utf-8 -*-

from http import HTTPStatus

import faker
from django.test import TestCase

from ..models import Item, Receipt, ReceiptItem
from . import ResultMixin
from .api_access import Api
from .factories import *


class PublicTest(TestCase, ResultMixin):
    def setUp(self):
        self.event = EventFactory.create()
        self.vendor = VendorFactory.create(event=self.event)
        self.type = ItemTypeFactory.create(event=self.event)

        user = self.vendor.user

        if not self.client.login(username=user.username, password=UserFactory.DEFAULT_PASSWORD):
            raise RuntimeError("Could not log in.")

    def test_register_item(self):
        data = dict(
            name=faker.Faker().sentence(nb_words=3),
            price="1.25",
            tag_type="short",
            suffixes="",
            item_type=self.type.id,
            adult=False,
        )
        result = self.assertSuccess(self.client.post("/kirppu/{}/vendor/item/".format(self.event.slug),
                                                     data=data)).json()
        self.assertEqual(1, len(result))
        r_item = result[0]
        self.assertEqual(self.vendor.id, r_item["vendor_id"])

    def test_register_box(self):
        data = dict(
            description=faker.Faker().sentence(nb_words=3),
            price="1.25",
            item_type=self.type.id,
            adult=False,
            count=4,
            bundle_size=1,
        )
        # Returns actually an html-page.. Test within context.
        result = self.assertSuccess(self.client.post("/kirppu/{}/vendor/box/".format(self.event.slug), data=data))
        self.assertEqual(data["description"], result.context["description"])

    def test_register_box_with_single_item(self):
        data = dict(
            description=faker.Faker().sentence(nb_words=3),
            price="1.25",
            item_type=self.type.id,
            adult=False,
            count=1,
            bundle_size=1,
        )
        # Returns actually an html-page.. Test within context.
        result = self.assertSuccess(self.client.post("/kirppu/{}/vendor/box/".format(self.event.slug), data=data))
        self.assertEqual(data["description"], result.context["description"])

    def test_register_single_bundle_box(self):
        data = dict(
            description=faker.Faker().sentence(nb_words=3),
            price="1.25",
            item_type=self.type.id,
            adult=False,
            count=1,
            bundle_size=2,
        )
        # Returns actually a html-page.. Test within context.
        result = self.assertSuccess(self.client.post("/kirppu/{}/vendor/box/".format(self.event.slug), data=data))
        self.assertEqual(data["description"], result.context["description"])


class StatesTest(TestCase, ResultMixin):
    def setUp(self):
        self.event = EventFactory.create()
        self.vendor = VendorFactory.create(event=self.event)
        self.items: list[Item] = ItemFactory.create_batch(10, vendor=self.vendor)

        self.counter = CounterFactory.create(event=self.event)
        self.clerk = ClerkFactory.create(event=self.event)

        self.api = Api(client=self.client, event=self.event)
        self.assertSuccess(self.api.clerk_login(code=self.clerk.get_code(), counter=self.counter.private_key))

    def test_fail_reserve_without_receipt(self):
        ret = self.api.item_reserve(code=self.items[0].code)
        self.assertEqual(HTTPStatus.BAD_REQUEST, ret.status_code)

    def test_normal_item_receipt(self):
        item_code = self.items[0].code

        receipt = self.assertSuccess(self.api.receipt_start()).json()

        self.assertSuccess(self.api.item_reserve(code=item_code))

        db_item = Item.objects.get(code=item_code)
        self.assertEqual(Item.STAGED, db_item.state)

        finished_receipt = self.assertSuccess(self.api.receipt_finish(id=receipt["id"])).json()

        db_item = Item.objects.get(code=item_code)
        self.assertEqual(Item.SOLD, db_item.state)
        self.assertEqual(Receipt.FINISHED, finished_receipt["status"])

    def test_double_reservation(self):
        # Note: This tests only two subsequent requests.
        # Two simultaneous requests cannot be tested here as basic tests require sequential request/database access.
        item_code = self.items[0].code

        receipt = self.assertSuccess(self.api.receipt_start()).json()
        self.assertSuccess(self.api.item_reserve(code=item_code))

        expected_failure = self.api.item_reserve(code=item_code)
        self.assertEqual(HTTPStatus.LOCKED, expected_failure.status_code)

    def _register_box_brought(self, box):
        rep = box.representative_item
        box_checkin = self.assertResult(self.api.item_checkin(code=rep.code, vendor=rep.vendor_id),
                                        expect=HTTPStatus.ACCEPTED).json()
        self.assertSuccess(self.api.box_checkin(code=rep.code,
                                                box_info=box_checkin["box"]["box_number"]))
        return box

    def test_normal_box_receipt(self):
        box = self._register_box_brought(BoxFactory.create(adopt=True, items=self.items))

        receipt = self.assertSuccess(self.api.receipt_start()).json()
        reserve_count = 3

        self.assertSuccess(self.api.box_item_reserve(box_number=box.box_number, box_item_count=reserve_count))
        self.assertEqual(reserve_count, Item.objects.filter(box=box, state=Item.STAGED).count())

        finished_receipt = self.assertSuccess(self.api.receipt_finish(id=receipt["id"])).json()

        self.assertEqual(Receipt.FINISHED, finished_receipt["status"])

    def test_double_box_reserve(self):
        # Note: This tests only two subsequent requests. Simultaneous access would behave differently.
        box = self._register_box_brought(BoxFactory.create(adopt=True, items=self.items))
        receipt = self.assertSuccess(self.api.receipt_start()).json()
        self.assertSuccess(self.api.box_item_reserve(box_number=box.box_number, box_item_count=3))
        self.assertSuccess(self.api.box_item_reserve(box_number=box.box_number, box_item_count=3))
        self.assertEqual(6, Item.objects.filter(box=box, state=Item.STAGED).count())

    def test_box_over_reserve(self):
        reserve_count = 3

        box = self._register_box_brought(
            BoxFactory.create(vendor=VendorFactory.create(event=self.event), item_count=reserve_count - 1)
        )

        receipt = self.assertSuccess(self.api.receipt_start()).json()

        self.assertResult(self.api.box_item_reserve(box_number=box.box_number, box_item_count=reserve_count),
                          expect=HTTPStatus.CONFLICT)

    def test_box_return_receipt(self):
        """Reserving and releasing box items should avoid representative item,
        as it is the one used to display item price.
        Relevant when part of box items are sold, and price of rest of its items are changed."""
        box = BoxFactory.create(adopt=True, items=self.items, box_number=1)
        Item.objects.all().update(state=Item.BROUGHT)

        representative_item_id = box.representative_item_id
        receipt = self.assertSuccess(self.api.receipt_start()).json()

        def check_count(n):
            self.assertEqual(n, Item.objects.filter(state=Item.STAGED).count())
            self.assertEqual(n, ReceiptItem.objects.filter(receipt__pk=receipt["id"], action=ReceiptItem.ADD).count())

        self.assertSuccess(self.api.box_item_reserve(box_number=1, box_item_count=4))
        self.assertEqual(4, Item.objects.filter(state=Item.STAGED).count())
        # Representative item should not be added to the receipt first.
        self.assertEqual(Item.BROUGHT, Item.objects.get(pk=representative_item_id).state)
        self.assertSuccess(self.api.box_item_release(box_number=1, box_item_count=2))
        self.assertEqual(2, Item.objects.filter(state=Item.STAGED).count())

        # Representative item should be first to be released.
        self.assertSuccess(self.api.box_item_reserve(box_number=1, box_item_count=8))
        check_count(10)
        self.assertEqual(Item.STAGED, Item.objects.get(pk=representative_item_id).state)
        self.assertSuccess(self.api.box_item_release(box_number=1, box_item_count=1))
        check_count(9)
        self.assertEqual(Item.BROUGHT, Item.objects.get(pk=representative_item_id).state)

        self.assertSuccess(self.api.box_item_reserve(box_number=1, box_item_count=1))
        check_count(10)
        self.assertEqual(Item.STAGED, Item.objects.get(pk=representative_item_id).state)
        self.assertSuccess(self.api.box_item_release(box_number=1, box_item_count=2))
        check_count(8)
        self.assertEqual(Item.BROUGHT, Item.objects.get(pk=representative_item_id).state)

    def test_suspend(self):
        other = ClerkFactory.create(event=self.event)
        Item.objects.all().update(state=Item.BROUGHT)

        receipt = self.assertSuccess(self.api.receipt_start()).json()

        self.assertSuccess(self.api.item_reserve(code=self.items[0].code))
        self.assertSuccess(self.api.receipt_suspend(note=""))

        self.assertEqual(Item.STAGED, Item.objects.get(pk=self.items[0].pk).state)
        self.assertEqual(Receipt.SUSPENDED, Receipt.objects.get(pk=receipt["id"]).status)

        self.assertSuccess(self.api.clerk_logout())

        self.assertSuccess(self.api.clerk_login(code=other.get_code(), counter=self.counter.private_key))
        self.assertSuccess(self.api.clerk_logout())

        self.assertSuccess(self.api.clerk_login(code=self.clerk.get_code(), counter=self.counter.private_key))

        sus_item_w_receipt = self.assertResult(
            self.api.item_find(code=self.items[0].code, available=True),
            expect=423,
        ).json()
        sus_receipt = sus_item_w_receipt["receipt"]
        res_receipt = self.assertSuccess(self.api.receipt_continue(code=self.items[0].code)).json()

        self.assertEqual(sus_receipt["id"], res_receipt["id"])

