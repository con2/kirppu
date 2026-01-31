from django.test import TestCase

from ..models import Item
from .factories import EventFactory, EventPermissionFactory, ItemFactory, ItemTypeFactory, UserFactory, VendorFactory


class ItemDumpTest(TestCase):
    def _addPermission(self):
        EventPermissionFactory(event=self.event, user=self.user, can_see_accounting=True)

    def _addItems(self, count=5):
        vendor = VendorFactory.create(user=self.user, event=self.event)
        itemtype = ItemTypeFactory.create()
        for _ in range(count):
            ItemFactory(vendor=vendor, itemtype=itemtype, state=Item.BROUGHT)

    def _get(self, query=""):
        return self.client.get("/kirppu/%s/itemdump/" % self.event.slug + "?" + query)

    def setUp(self):
        self.user = UserFactory.create()
        self.event = EventFactory.create()
        self.client.force_login(self.user)

    def test_defaultState(self):
        self._addPermission()
        resp = self._get()
        self.assertEqual(200, resp.status_code)

    def test_noPermission(self):
        resp = self._get()
        self.assertEqual(403, resp.status_code)

    def test_csv(self):
        self._addPermission()
        self._addItems(count=5)
        resp = self._get()

        self.assertEqual(200, resp.status_code)
        self.assertFalse(resp.has_header("Content-Disposition"))

        # CSV: 5 items + header
        self.assertEqual(5 + 1, resp.getvalue().count(b"\n"))

    def test_text(self):
        self._addPermission()
        self._addItems(count=5)
        resp = self._get(query="txt")

        self.assertEqual(200, resp.status_code)

        content = resp.getvalue()
        # Text: 5 items + 7 header rows (1 per column)
        self.assertEqual(5 + 7, content.count(b"\n"))

    def test_download(self):
        self._addPermission()
        self._addItems(count=5)
        resp = self._get(query="download")

        self.assertEqual(200, resp.status_code)
        self.assertTrue(resp.has_header("Content-Disposition"))
        self.assertTrue(resp["Content-Type"].startswith("text/csv"))

        content = resp.getvalue()
        # CSV: 5 items + header
        self.assertEqual(5 + 1, content.count(b"\n"))
