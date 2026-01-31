from django.test import TestCase

from . import ResultMixin

from ..models import Item, Receipt
from .factories import BoxFactory, ReceiptItemFactory, ItemFactory, UserFactory


class ReceiptRemovalTests(TestCase, ResultMixin):
    def setUp(self):
        self.receipt_item = ReceiptItemFactory.create()
        self.item = self.receipt_item.item
        self.item.state = Item.SOLD
        self.item.save(update_fields=["state"])

        vendor = self.item.vendor
        self.event = vendor.event
        self.receipt = self.receipt_item.receipt

        self.other_item = ItemFactory.create(vendor=vendor, state=Item.SOLD)
        self.other_receipt_item = ReceiptItemFactory.create(
            item=self.other_item, receipt=self.receipt
        )

        self.receipt.calculate_total()
        self.receipt.status = Receipt.FINISHED
        self.receipt.save(update_fields=["status", "total"])
        self.assertEqual(250, self.receipt.total_cents)

        user = UserFactory.create(is_superuser=True, is_staff=True)
        self.client.force_login(user)

    def _refresh(self):
        self.item.refresh_from_db()
        self.other_item.refresh_from_db()
        self.receipt.refresh_from_db()

    def _perform(self, code: str):
        data = {
            "code": code,
            "receipt": self.receipt.id,
        }
        self.assertResult(
            self.client.post(f"/kirppu/{self.event.slug}/remove_item", data=data),
            expect=302,
        )

    def test_item_removal(self):
        self._perform(self.item.code)
        self._refresh()

        self.assertEqual(Item.BROUGHT, self.item.state)
        self.assertEqual(Item.SOLD, self.other_item.state)
        self.assertEqual(125, self.receipt.total_cents)

    def test_box_item_removal(self):
        box = BoxFactory.create(adopt=True, items=[self.item, self.other_item])

        self._perform(f"box{box.box_number}")
        self._refresh()

        result_states = [self.item.state, self.other_item.state]
        self.assertTrue(Item.BROUGHT in result_states)
        self.assertTrue(Item.SOLD in result_states)
        self.assertEqual(125, self.receipt.total_cents)
