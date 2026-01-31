# -*- coding: utf-8 -*-
import json
import textwrap
import typing
from decimal import Decimal

from django.test import TestCase, override_settings

from kirppu.provision import Provision

from ..models import Account, Item, Receipt
from . import ResultMixin
from .api_access import Api
from .factories import *


class ApiOK(Api, ResultMixin):
    def _check_response(self, response):
        self.assertSuccess(response)

    # noinspection PyPep8Naming
    @staticmethod
    def assertEqual(expect, actual, msg=""):
        # used by assertSuccess.
        if expect != actual:
            raise AssertionError(msg or ("%s != %s" % (repr(expect), repr(actual))))


class SoldItemFactory(ItemFactory):
    state = Item.SOLD


@override_settings(KIRPPU_ALLOW_PROVISION_FUNCTIONS=True)
class ProvisionTest(TestCase):
    """Provision tests running without compensable items."""
    def setUp(self):
        self.vendor = VendorFactory.create()

    def test_no_items_no_provision(self):
        p = Provision(self.vendor.id, provision_function="null")

        self.assertFalse(p.has_provision)
        self.assertIsNone(p.provision_fix)
        self.assertIsNone(p.provision)

    def test_initial_provision(self):
        p = Provision(self.vendor.id, provision_function="15")

        self.assertTrue(p.has_provision)
        # Presented in provision instead of fix, since we are in 'initial' state and there is nothing to fix.
        self.assertEqual(Decimal("-15.00"), p.provision)
        self.assertEqual(Decimal("0.00"), p.provision_fix)

    def test_no_items_with_provision_already_compensated(self):
        some_items = ItemFactory.create_batch(10, vendor=self.vendor, state=Item.COMPENSATED)

        p = Provision(self.vendor.id, provision_function="""(* 0.10 (.count sold_and_compensated))""")

        self.assertTrue(p.has_provision)
        self.assertEqual(Decimal("-1.00"), p.provision_fix, p)
        self.assertEqual(Decimal("0.00"), p.provision, p)


@override_settings(KIRPPU_ALLOW_PROVISION_FUNCTIONS=True)
class BeforeProvisionTest(TestCase):
    """Tests running before a provision has been paid; having items to compensate."""
    def setUp(self):
        self.vendor = VendorFactory.create()
        self.items = SoldItemFactory.create_batch(10, vendor=self.vendor)

    def test_no_provision_before_compensation(self):
        p = Provision(self.vendor.id, provision_function="null")

        self.assertEqual(len(p._vendor_items), len(self.items))
        self.assertFalse(p.has_provision)
        self.assertIsNone(p.provision)
        self.assertIsNone(p.provision_fix)

    def test_simple_provision_before_compensation(self):
        p = Provision(self.vendor.id, provision_function="""(* 0.10 (.count sold_and_compensated))""")

        self.assertEqual(len(p._vendor_items), len(self.items))
        self.assertTrue(p.has_provision)
        self.assertEqual(Decimal("0.00"), p.provision_fix)
        self.assertEqual(Decimal("-1.00"), p.provision)  # -(10 * 0.10) == -1

    def test_missing_provision(self):
        some_items = ItemFactory.create_batch(10, vendor=self.vendor, state=Item.COMPENSATED)

        p = Provision(self.vendor.id, provision_function="""(* 0.10 (.count sold_and_compensated))""")

        self.assertTrue(p.has_provision)
        self.assertEqual(Decimal("-1.00"), p.provision_fix)
        self.assertEqual(Decimal("-1.00"), p.provision)

    def test_provision_gt_compensable(self):
        """Provision is higher than average item price -> compensation causes actually vendor to pay."""
        p = Provision(self.vendor.id, provision_function="""(* 2 (.count sold_and_compensated))""")

        self.assertTrue(p.has_provision, p)
        self.assertEqual(Decimal("0.00"), p.provision_fix, p)
        self.assertEqual(Decimal("-20.00"), p.provision, p)

    def test_provision_fix_gt_compensable(self):
        some_items = ItemFactory.create_batch(10, vendor=self.vendor, state=Item.COMPENSATED)

        p = Provision(self.vendor.id, provision_function="""(* 2 (.count sold_and_compensated))""")

        self.assertTrue(p.has_provision, p)
        self.assertEqual(Decimal("-20.00"), p.provision_fix, p)
        self.assertEqual(Decimal("-20.00"), p.provision, p)


@override_settings(KIRPPU_ALLOW_PROVISION_FUNCTIONS=True)
class FinishingProvisionTest(TestCase):
    def setUp(self):
        self.vendor = VendorFactory.create()
        self.receipt = ReceiptFactory.create(type=Receipt.TYPE_COMPENSATION, vendor=self.vendor)
        self.items = ReceiptItemFactory.create_batch(
            10, receipt=self.receipt, item__vendor=self.vendor, item__state=Item.COMPENSATED)

    def test_no_provision_finishing_compensation(self):
        p = Provision(self.vendor.id, receipt=self.receipt,
                      provision_function="""null""")

        self.assertEqual(len(p._vendor_items), len(self.items))
        self.assertFalse(p.has_provision)
        self.assertIsNone(p.provision)
        self.assertIsNone(p.provision_fix)

    def test_simple_provision_finishing_compensation(self):
        p = Provision(self.vendor.id, receipt=self.receipt,
                      provision_function="""(* 0.10 (.count sold_and_compensated))""")

        self.assertEqual(len(self.items), len(p._vendor_items))
        self.assertTrue(p.has_provision, p)
        self.assertEqual(Decimal("0.00"), p.provision_fix, p)
        self.assertEqual(Decimal("-1.00"), p.provision, p)  # -(10 * 0.10) == -1

    def test_concurrent_sell_finishing_compensation(self):
        more_items = SoldItemFactory.create_batch(10, vendor=self.vendor)

        p = Provision(self.vendor.id, receipt=self.receipt,
                      provision_function="""(* 0.10 (.count sold_and_compensated))""")

        still_more_items = SoldItemFactory.create_batch(10, vendor=self.vendor)

        self.assertTrue(p.has_provision)
        self.assertEqual(Decimal("0.00"), p.provision_fix, p)
        self.assertEqual(Decimal("-1.00"), p.provision, p)  # -(10 * 0.10) == -1


# noinspection PyPep8Naming,PyAttributeOutsideInit
class _ApiProvisionTest(TestCase):
    def _setUp_Event(self):
        self.event = EventFactory.create()

    def setUp(self):
        self._setUp_Event()

        self.vendor = VendorFactory.create(event=self.event)
        self.items = SoldItemFactory.create_batch(10, vendor=self.vendor)

        self.account = AccountFactory.create(event=self.event, balance=Decimal(100))
        self.counter = CounterFactory.create(event=self.event, default_store_location=self.account)
        self.clerk = ClerkFactory.create(event=self.event)

        self.apiOK = ApiOK(client=self.client, event=self.event.slug)

        self.apiOK.clerk_login(code=self.clerk.get_code(), counter=self.counter.private_key)

    def tearDown(self):
        self.apiOK.clerk_logout()

    def _compensate(self, items):
        receipt = self.apiOK.item_compensate_start(vendor=self.vendor.id)

        for item in items:
            self.apiOK.item_compensate(code=item.code)

        response = self.apiOK.item_compensate_end()
        receipt = response.json()
        return receipt, response

    def _get_extra(self, extras, extra_type):
        e = [item for item in extras if item["type"] == extra_type]
        self.assertTrue(len(e) <= 1)
        if not e:
            return None
        return e[0]

    def _get_receipt(self, receipt_id):
        # The arguments are actually consumed by the view.
        # noinspection PyArgumentList
        receipt = self.apiOK.receipt_get(id=receipt_id, type="compensation")
        extras = [item for item in receipt.json()["items"] if item["action"] == "EXTRA"]
        return extras

    def _get_receipt_lazy(self, receipt_id: typing.Union[typing.Dict, int]):
        if isinstance(receipt_id, dict):
            receipt_id = receipt_id["id"]

        def fn():
            return json.dumps(self._get_receipt(receipt_id))
        return self.LazyStr(fn)

    class LazyStr:
        def __init__(self, fn):
            self._fn = fn

        def __str__(self):
            return self._fn()


@override_settings(KIRPPU_ALLOW_PROVISION_FUNCTIONS=True)
class ApiNoProvisionTest(_ApiProvisionTest):

    # region No Provision
    def test_no_provision_no_items(self):
        receipt, response = self._compensate([])
        self.assertEqual(0, receipt["total"])

    def test_no_provision_single_go(self):
        receipt, response = self._compensate(self.items)
        self.assertEqual(1250, receipt["total"])  # 10*1.25 as cents

    def test_no_provision_two_phases(self):
        part_1 = self.items[:6]
        part_2 = self.items[6:]

        receipt_1, response_1 = self._compensate(part_1)
        self.assertEqual(750, receipt_1["total"], self._get_receipt_lazy(receipt_1))  # 6*1.25 as cents

        receipt_2, response_2 = self._compensate(part_2)
        self.assertEqual(500, receipt_2["total"], self._get_receipt_lazy(receipt_2))  # 4*1.25 as cents
        # 750 + 500 == 1250
    # endregion


@override_settings(KIRPPU_ALLOW_PROVISION_FUNCTIONS=True)
class ApiLinearProvisionTest(_ApiProvisionTest):
    def _setUp_Event(self):
        self.event = EventFactory.create(
            provision_function="""(* 0.10 (.count sold_and_compensated))"""
        )

    # region Linear Provision
    def test_linear_provision_no_items(self):
        receipt, response = self._compensate([])
        self.assertEqual(0, receipt["total"])

    def test_linear_provision_single_go(self):
        guess = self.apiOK.compensable_items(vendor=self.vendor.id)
        provision = self._get_extra(guess.json()["extras"], "PRO")
        self.assertEqual(-100, provision["value"])

        receipt, response = self._compensate(self.items)
        self.assertEqual(1150, receipt["total"])  # 10*(1.25-0.10) as cents
        self.assertEqual(self.account.balance - Decimal("11.50"), Account.objects.get(pk=self.account.pk).balance)

    def test_linear_provision_two_phases(self):
        part_1 = self.items[:6]
        part_2 = self.items[6:]

        receipt_1, response_1 = self._compensate(part_1)
        self.assertEqual(690, receipt_1["total"], self._get_receipt_lazy(receipt_1))  # 6*(1.25-0.10) as cents

        receipt_2, response_2 = self._compensate(part_2)
        self.assertEqual(460, receipt_2["total"], self._get_receipt_lazy(receipt_2))  # 4*(1.25-0.10) as cents
        # 690 + 460 == 1150

    def test_provision_gt_compensation(self):
        self.event.provision_function = """15"""
        self.event.save(update_fields=("provision_function",))

        receipt, response = self._compensate(self.items)
        self.assertEqual(-250, receipt["total"], self._get_receipt_lazy(receipt))  # 10*1.25-15 as cents

    # endregion


@override_settings(KIRPPU_ALLOW_PROVISION_FUNCTIONS=True)
class ApiStepProvisionTest(_ApiProvisionTest):
    def _setUp_Event(self):
        self.event = EventFactory.create(
            provision_function="""(* 0.50 (// (.count sold_and_compensated) 4))"""
        )

    # region Step Provision
    def test_step_provision_single_go(self):
        guess = self.apiOK.compensable_items(vendor=self.vendor.id)
        provision = self._get_extra(guess.json()["extras"], "PRO")
        self.assertEqual(-100, provision["value"])

        receipt, response = self._compensate(self.items)
        self.assertEqual(1150, receipt["total"])  # 10*1.25-(10//4)*0.50 as cents

    def test_step_provision_two_phases(self):
        part_1 = self.items[:6]
        part_2 = self.items[6:]

        receipt_1, response_1 = self._compensate(part_1)
        self.assertEqual(700, receipt_1["total"])  # 6*1.25-0.50 as cents

        receipt_2, response_2 = self._compensate(part_2)
        self.assertEqual(450, receipt_2["total"])  # 4*1.25-0.50 as cents
        # 700 + 450 == 1150

        # Ensure there is no fixup entry in the item set.
        extras = [item["type"] for item in self._get_receipt(receipt_2["id"])]
        self.assertEqual(1, len(extras))
        self.assertIn("PRO", extras)
        self.assertNotIn("PRO_FIX", extras)
    # endregion


@override_settings(KIRPPU_ALLOW_PROVISION_FUNCTIONS=True)
class ApiRoundingProvisionTest(_ApiProvisionTest):
    def _setUp_Event(self):
        self.event = EventFactory.create(
            provision_function=textwrap.dedent("""
            (/ (ceil (* 2 (* 0.20 (.count sold_and_compensated)))) 2)
            """)
        )

    # region Rounding Provision
    def test_rounding_provision_single_go(self):
        guess = self.apiOK.compensable_items(vendor=self.vendor.id).json()["extras"]
        provision = self._get_extra(guess, "PRO")
        self.assertEqual(-200, provision["value"])
        self.assertIsNone(self._get_extra(guess, "PRO_FIX"))

        receipt, response = self._compensate(self.items)
        self.assertEqual(1050, receipt["total"])  # 10*1.25-10*0.20 as cents

    def test_rounding_provision_two_phases(self):
        part_1 = self.items[:6]
        part_2 = self.items[6:]

        receipt_1, response_1 = self._compensate(part_1)
        self.assertEqual(600, receipt_1["total"])  # 6*1.25-1.50 as cents

        receipt_2, response_2 = self._compensate(part_2)
        receipt = self._get_receipt(receipt_2["id"])

        self.assertEqual(450, receipt_2["total"])  # 4*1.25-2*0.50 as cents
        # 600 + 450 == 1050

        receipt = self._get_receipt(receipt_2["id"])
        extras = [item["type"] for item in receipt]
        self.assertEqual(1, len(extras))
        self.assertIn("PRO", extras)
        self.assertNotIn("PRO_FIX", extras)

    def test_rounding_provision_two_phases_2(self):
        part_1 = self.items[:5]
        part_2 = self.items[5:]

        receipt_1, response_1 = self._compensate(part_1)
        self.assertEqual(525, receipt_1["total"])  # 5*1.25-1.00 as cents

        receipt_2, response_2 = self._compensate(part_2)
        receipt = self._get_receipt(receipt_2["id"])

        self.assertEqual(525, receipt_2["total"])  # 5*1.25-2*0.50 as cents

        receipt = self._get_receipt(receipt_2["id"])
        extras = [item["type"] for item in receipt]
        self.assertEqual(1, len(extras))
        self.assertIn("PRO", extras)
        self.assertNotIn("PRO_FIX", extras)

    def test_rounding_provision_two_phases_3(self):
        part_1 = self.items[:4]
        part_2 = self.items[4:]

        receipt_1, response_1 = self._compensate(part_1)
        self.assertEqual(400, receipt_1["total"])  # 4*1.25-1.00 as cents

        receipt_2, response_2 = self._compensate(part_2)
        receipt = self._get_receipt(receipt_2["id"])

        self.assertEqual(650, receipt_2["total"])  # 6*1.25-2*0.50 as cents
        # 400 + 650 == 1050

        receipt = self._get_receipt(receipt_2["id"])
        extras = [item["type"] for item in receipt]
        self.assertEqual(1, len(extras))
        self.assertIn("PRO", extras)
        self.assertNotIn("PRO_FIX", extras)

    def test_rounding_provision_with_add(self):
        guess = self.apiOK.compensable_items(vendor=self.vendor.id).json()["extras"]
        provision = self._get_extra(guess, "PRO")
        self.assertEqual(-200, provision["value"])
        self.assertIsNone(self._get_extra(guess, "PRO_FIX"))

        receipt_1, response_1 = self._compensate(self.items)
        self.assertEqual(1050, receipt_1["total"])

        more = SoldItemFactory.create_batch(4, vendor=self.vendor)
        guess = self.apiOK.compensable_items(vendor=self.vendor.id).json()["extras"]
        provision = self._get_extra(guess, "PRO")
        self.assertEqual(-100, provision["value"])
        self.assertIsNone(self._get_extra(guess, "PRO_FIX"))

        receipt_2, response_2 = self._compensate(more)
        receipt = self._get_receipt(receipt_2["id"])

        self.assertEqual(400, receipt_2["total"])
# [<-needed for ide-region]
    # endregion
