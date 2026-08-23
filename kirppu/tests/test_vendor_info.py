from datetime import timedelta
from decimal import Decimal
import re

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from . import ResultMixin
from .factories import (
    AccountFactory,
    ClerkFactory,
    CounterFactory,
    EventFactory,
    EventPermissionFactory,
    ItemFactory,
    UserFactory,
    VendorFactory,
)
from ..models import Item, Vendor

TEST_IBAN = "FI1260415379240366"
TEST_REASON = "Foo bar baz."


def _make_iban_vendor(event, user, lock: bool = False, clean: bool = False) -> Vendor:
    return VendorFactory(
        event=event,
        user=user,
        bank_iban="!" if clean else "IBAN",
        bank_bic="!" if clean else "BIC",
        bank_lock=lock,
    )


def _make_skip_vendor(event, user, lock: bool = False, clean: bool = False) -> Vendor:
    return VendorFactory(
        event=event,
        user=user,
        bank_skip=TEST_REASON,
        bank_iban="!" if clean else None,
        bank_bic="!" if clean else None,
        bank_lock=lock,
    )


class TestBankInfo(TestCase, ResultMixin):
    def setUp(self) -> None:
        self.user = UserFactory()
        self.client.force_login(self.user)
        self.event = EventFactory(
            collect_bank_information=True,
        )
        self.url = reverse(
            "kirppu:accept_terms", kwargs={"event_slug": self.event.slug}
        )

    def test_skip(self):
        self.assertSuccess(
            self.client.post(
                self.url,
                data={
                    "terms-accepted": "true",
                    "with_account": "false",
                    "reason": TEST_REASON,
                },
            )
        )

    def test_bank(self):
        self.assertSuccess(
            self.client.post(
                self.url,
                data={
                    "terms-accepted": "true",
                    "with_account": "true",
                    "iban": TEST_IBAN,
                },
            )
        )

    def test_change_to_bank(self):
        _make_skip_vendor(self.event, self.user)

        self.assertSuccess(
            self.client.post(
                self.url,
                data={
                    "terms-accepted": "true",
                    "with_account": "true",
                    "iban": TEST_IBAN,
                },
            )
        )

    def test_change_to_skip(self):
        _make_iban_vendor(self.event, self.user)

        self.assertSuccess(
            self.client.post(
                self.url,
                data={
                    "terms-accepted": "true",
                    "with_account": "false",
                    "reason": TEST_REASON,
                },
            )
        )


class _PastEventTest(TestCase, ResultMixin):
    def setUp(self) -> None:
        self.user = UserFactory()
        self.client.force_login(self.user)
        d = timezone.now()
        self.event = EventFactory(
            registration_end=d - timedelta(days=3),
            start_date=(d - timedelta(days=2)).date(),
            end_date=(d - timedelta(days=1)).date(),
            collect_bank_information=True,
        )
        self.url = reverse(
            "kirppu:accept_terms", kwargs={"event_slug": self.event.slug}
        )


class TestBankInfoAfterEvent(_PastEventTest):
    def test_change_to_bank(self):
        _make_skip_vendor(self.event, self.user)

        self.assertSuccess(
            self.client.post(
                self.url,
                data={
                    "terms-accepted": "true",
                    "with_account": "true",
                    "iban": TEST_IBAN,
                },
            )
        )

    def test_update_reason(self):
        _make_skip_vendor(self.event, self.user)

        self.assertSuccess(
            self.client.post(
                self.url,
                data={
                    "terms-accepted": "true",
                    "with_account": "false",
                    "reason": TEST_REASON + "1",
                },
            )
        )

    def test_no_change_to_skip(self):
        _make_iban_vendor(self.event, self.user)

        self.assertContains(
            self.client.post(
                self.url,
                data={
                    "terms-accepted": "true",
                    "with_account": "false",
                    "reason": TEST_REASON,
                },
            ),
            "failure",
            status_code=400,
        )

    def test_no_change_bank_after_compensation(self):
        _make_iban_vendor(self.event, self.user, lock=True)

        self.assertContains(
            self.client.post(
                self.url,
                data={
                    "terms-accepted": "true",
                    "with_account": "true",
                    "iban": TEST_IBAN,
                },
            ),
            "failure",
            status_code=400,
        )

    def test_no_change_to_skip_after_compensation(self):
        _make_iban_vendor(self.event, self.user, lock=True)

        self.assertContains(
            self.client.post(
                self.url,
                data={
                    "terms-accepted": "true",
                    "with_account": "false",
                    "reason": TEST_REASON,
                },
            ),
            "failure",
            status_code=400,
        )

    def test_no_change_skip_after_compensation(self):
        _make_skip_vendor(self.event, self.user, lock=True)

        self.assertContains(
            self.client.post(
                self.url,
                data={
                    "terms-accepted": "true",
                    "with_account": "false",
                    "reason": TEST_REASON,
                },
            ),
            "failure",
            status_code=400,
        )


class TestVendorAfterEvent(_PastEventTest):
    def test_bank(self):
        self.assertResult(
            self.client.post(
                self.url,
                data={
                    "terms-accepted": "true",
                    "with_account": "true",
                    "iban": TEST_IBAN,
                },
            ),
            expect=403,
        )

    def test_partial_vendor_reason(self):
        # This is only possible if the collection is enabled midway the registration.
        VendorFactory(event=self.event, user=self.user)

        v = self.client.post(
            self.url,
            data={
                "terms-accepted": "true",
                "with_account": "false",
                "reason": TEST_REASON,
            },
        )
        self.assertContains(v, "failure", status_code=400)

    def test_partial_vendor_iban(self):
        # This is only possible if the collection is enabled midway the registration.
        VendorFactory(event=self.event, user=self.user)

        self.assertSuccess(
            self.client.post(
                self.url,
                data={
                    "terms-accepted": "true",
                    "with_account": "true",
                    "iban": TEST_IBAN,
                },
            )
        )


class TestBalanceExport(TestCase, ResultMixin):
    def setUp(self) -> None:
        self.user = UserFactory()
        self.event = EventFactory(
            collect_bank_information=True,
        )
        self.clerk = ClerkFactory(event=self.event)
        self.client.force_login(self.clerk.user)
        self.account = AccountFactory.create(event=self.event, balance=Decimal(1000))
        self.counter = CounterFactory(
            event=self.event, default_store_location=self.account
        )

        EventPermissionFactory(
            event=self.event,
            user=self.clerk.user,
            can_manage_event=True,
            can_see_accounting=True,
        )

    def _url(self, p):
        return reverse(p, kwargs={"event_slug": self.event.slug})

    def test_index(self):
        self.assertSuccess(self.client.get(self._url("kirppu:balance_export")))

    def test_compensation_nops(self):
        start_data = {
            "hash": "H0000000000000000000000000000000000000000000000000000000000000000",
            "counter_code": ":*" + self.counter.identifier,
        }
        self.assertContains(
            self.client.post(
                self._url("kirppu:balance_export_start"),
                data=start_data,
                content_type="application/json",
            ),
            "Nothing to do",
            status_code=400,
        )
        self.assertContains(
            self.client.post(self._url("kirppu:balance_export_iter")),
            "Not started",
            status_code=400,
        )
        # Ending always succeeds
        self.assertSuccess(self.client.post(self._url("kirppu:balance_export_end")))
        # Checking should succeed without needing to do anything
        self.assertContains(
            self.client.post(self._url("kirppu:balance_check_cleanup")), "OK"
        )

    def _obtain_hash(self) -> str:
        v = self.client.get(self._url("kirppu:balance_export_csv"))

        h = re.search(r"Content hash.*(H\w+)", v.content.decode())
        self.assertIsNotNone(h)
        return h.group(1)

    def _start(self, length: int = 1):
        h = self._obtain_hash()

        start_data = {
            "hash": h,
            "counter_code": ":*" + self.counter.identifier,
        }
        start = self.assertSuccess(
            self.client.post(
                self._url("kirppu:balance_export_start"),
                data=start_data,
                content_type="application/json",
            ),
        ).json()
        self.assertEqual(start.get("index"), 0)
        self.assertEqual(start.get("length"), length)

    def test_simple_compensation(self):
        v = _make_iban_vendor(self.event, self.user)
        i = ItemFactory(vendor=v, state=Item.SOLD)

        self._start()
        self.assertEqual(Item.objects.get(pk=i.pk).state, Item.SOLD)

        it = self.assertSuccess(
            self.client.post(self._url("kirppu:balance_export_iter"))
        ).json()
        self.assertEqual(it.get("index"), 1)
        self.assertEqual(it.get("length"), 1)
        self.assertEqual(Item.objects.get(pk=i.pk).state, Item.COMPENSATED)
        self.assertTrue(Vendor.objects.get(pk=v.pk).bank_lock)

        self.assertSuccess(self.client.post(self._url("kirppu:balance_export_end")))

    def test_compensation_mixed(self):
        v2 = _make_skip_vendor(self.event, self.user)
        i = ItemFactory(vendor=v2, state=Item.SOLD)

        # Skip vendors should not affect iban vendors
        self.test_simple_compensation()

        # Also skip vendors should be now locked
        self.assertTrue(Vendor.objects.get(pk=v2.pk).bank_lock)

    def test_cleanup_nok(self):
        v = _make_iban_vendor(self.event, self.user)
        ItemFactory(vendor=v, state=Item.SOLD)

        self.assertContains(
            self.client.post(self._url("kirppu:balance_check_cleanup")),
            "vendors with bank info",
            status_code=409,
        )

        self.assertContains(
            self.client.post(self._url("kirppu:balance_details_cleanup")),
            "vendors with bank info",
            status_code=400,
        )

    def test_cleanup(self):
        # XXX: This test needs a compensation receipt
        self.test_simple_compensation()

        self.assertContains(
            self.client.post(self._url("kirppu:balance_check_cleanup")),
            "OK",
            status_code=200,
        )

        self.assertSuccess(
            self.client.post(self._url("kirppu:balance_details_cleanup"))
        )

        # After cleanup, no re-do should be done.
        self.assertContains(
            self.client.post(self._url("kirppu:balance_check_cleanup")),
            "NOP",
            status_code=200,
        )
