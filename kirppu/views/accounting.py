# -*- coding: utf-8 -*-
from collections import defaultdict
import csv
import typing

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Sum
from django.shortcuts import get_object_or_404, render
from django.utils.translation import gettext_lazy as _, pgettext_lazy, gettext
from django.utils import timezone

from .csv_utils import csv_streamer_view, strip_generator
from .menu import vendor_menu
from ..models import (
    Event,
    EventPermission,
    Item,
    Receipt,
    ReceiptExtraRow,
    ReceiptItem,
    RemoteEvent,
    decimal_to_transport,
)

__all__ = [
    "accounting_receipt_view",
    "accounting_receipt",
]


COLUMNS = (
    _("Event number"),
    _("Timestamp"),
    _("Vendor"),
    _("Event type"),
    pgettext_lazy("Substantive, change in value or balance", "Change"),
    _("Vendor balance"),
    _("Total balance"),
)

EVENT_FORFEIT = "__FEE"
EVENTS = dict((
    (Receipt.TYPE_PURCHASE, _("SALE")),
    (Receipt.TYPE_COMPENSATION, _("PAYOUT")),
    (ReceiptExtraRow.TYPE_PROVISION, _("COMMISSION")),
    (ReceiptExtraRow.TYPE_PROVISION_FIX, _("COMMISSION FIX")),
    (EVENT_FORFEIT, _("FORFEIT")),
))


def _zero_fn():
    return 0


@login_required
def accounting_receipt_view(request, event_slug):
    event = get_object_or_404(Event, slug=event_slug)
    if not EventPermission.get(event, request.user).can_see_accounting:
        raise PermissionDenied

    event = event.get_real_event()
    return csv_streamer_view(
        request,
        lambda output: accounting_receipt(output, event, generator=True),
        gettext("accounting")
    )


@strip_generator
def accounting_receipt(output, event: typing.Union[Event, RemoteEvent]):
    writer = csv.writer(output)
    writer.writerow(str(c) for c in COLUMNS)
    # Used here and later for buffer streaming and clearing in case of StringIO.
    yield

    receipts = (Receipt.objects
                .using(event.get_real_database_alias())
                .filter(clerk__event=event, status=Receipt.FINISHED)
                .prefetch_related("receiptitem_set", "receiptitem_set__item", "extra_rows")
                .order_by("end_time")
                )

    impl = AccountingWriter(writer)
    for receipt in receipts:
        impl.write_receipt(receipt)
        yield
    impl.finish()
    yield

    items_paid_out = (Item.objects
                      .using(event.get_real_database_alias())
                      .filter(vendor__event=event, state=Item.COMPENSATED)
                      .aggregate(sum=Sum("price"))
                      )
    items_paid_out = decimal_to_transport(items_paid_out["sum"] or 0)
    items_forfeited = (Item.objects
                       .using(event.get_real_database_alias())
                       .filter(vendor__event=event, state=Item.SOLD)
                       .aggregate(sum=Sum("price")))
    items_forfeited = decimal_to_transport(items_forfeited["sum"] or 0)

    # Basic sanity checking. Does not really give a straight explanation of why something is amiss.
    writer.writerow(())
    if items_paid_out != impl.total_payout:
        writer.writerow((gettext("Payout difference:"),))
        writer.writerow((None, gettext("In Items"), items_paid_out))
        writer.writerow((None, gettext("In Receipts"), impl.total_payout))

    if items_forfeited != impl.total_forfeit:
        writer.writerow((gettext("Forfeit difference:"),))
        writer.writerow((None, gettext("In Items"), items_forfeited))
        writer.writerow((None, gettext("In Receipts"), impl.total_forfeit))

    yield


class AccountingWriter(object):
    def __init__(self, writer):
        self.i = 1
        self.total_balance = 0
        self.total_vendors = defaultdict(_zero_fn)
        self.writer = writer

        self.total_income = 0
        self.total_payout = 0
        self.total_forfeit = 0

    def write_receipt(self, receipt):
        if receipt.type == Receipt.TYPE_PURCHASE:
            self._write_purchase(receipt)
        elif receipt.type == Receipt.TYPE_COMPENSATION:
            self._write_compensation(receipt)

    def _write_purchase(self, receipt: Receipt):
        # Group receipt data by vendor.
        receipt_vendors = defaultdict(_zero_fn)
        for row in receipt.receiptitem_set.all():
            if row.action == ReceiptItem.ADD:
                item = row.item
                vid = item.vendor_id
                price = item.price_cents
                receipt_vendors[vid] += price

        # Dump grouped data while calculating.
        event_type = EVENTS[receipt.type]
        timestamp = timezone.localtime(receipt.end_time).isoformat(timespec="seconds")
        for vid in sorted(receipt_vendors.keys()):
            value = receipt_vendors[vid]
            vendor_balance = self.total_vendors[vid] + value
            self.total_vendors[vid] = vendor_balance
            self.total_balance += value
            self.total_income += value

            self.writer.writerow((
                self.i, timestamp, vid, event_type, value, vendor_balance, self.total_balance
            ))
            self.i += 1

    def _write_compensation(self, receipt: Receipt):
        rows = receipt.receiptitem_set.all()
        common_vendor = receipt.vendor_id
        if any(common_vendor != r.item.vendor_id for r in rows):
            raise ValueError("Invalid receipt configuration")

        compensation_sum = sum(r.item.price_cents for r in rows)
        event_type = EVENTS[receipt.type]
        timestamp = timezone.localtime(receipt.end_time).isoformat(timespec="seconds")

        vendor_balance = self.total_vendors[common_vendor] - compensation_sum
        self.total_vendors[common_vendor] = vendor_balance
        self.total_balance -= compensation_sum
        self.total_payout += compensation_sum

        if receipt.extra_rows.count() > 0:
            provision = 0
            provision_fix = 0
            for r in receipt.extra_rows.all():
                if r.type == ReceiptExtraRow.TYPE_PROVISION:
                    provision += r.value_cents
                elif r.type == ReceiptExtraRow.TYPE_PROVISION_FIX:
                    provision_fix += r.value_cents
                else:
                    assert False, "Not Implemented: " + r.type

            alter = provision + provision_fix
            self.writer.writerow((
                self.i, timestamp, common_vendor, event_type,
                -compensation_sum - alter,
                vendor_balance - alter,
                self.total_balance - alter
            ))
            self.i += 1

            if provision:
                self.writer.writerow((
                    self.i, timestamp, common_vendor, EVENTS[ReceiptExtraRow.TYPE_PROVISION],
                    provision,
                    vendor_balance - provision_fix,
                    self.total_balance - provision_fix
                ))
                self.i += 1

            if provision_fix:
                self.writer.writerow((
                    self.i, timestamp, common_vendor, EVENTS[ReceiptExtraRow.TYPE_PROVISION_FIX],
                    provision_fix,
                    vendor_balance,
                    self.total_balance
                ))
                self.i += 1

        else:
            self.writer.writerow((
                self.i, timestamp, common_vendor, event_type, -compensation_sum, vendor_balance, self.total_balance
            ))
            self.i += 1

    def finish(self):
        now = timezone.localtime(timezone.now()).isoformat(timespec="seconds")
        event_type = EVENTS[EVENT_FORFEIT]
        for vid in sorted(self.total_vendors.keys()):
            value = self.total_vendors[vid]
            if value != 0:
                self.total_forfeit += value
                value = -value
                self.total_balance += value
                self.writer.writerow((
                    self.i, now, vid, event_type, value, 0, self.total_balance
                ))
                self.i += 1

        if self.i == 1:
            self.writer.writerow((
                self.i, now, None, event_type, 0, 0, 0
            ))

        assert self.total_balance == 0


@login_required
def live_accounts(request, event_slug: str):
    event = get_object_or_404(Event, slug=event_slug)
    if not EventPermission.get(event, request.user).can_see_accounting:
        raise PermissionDenied

    return render(
        request,
        "kirppu/live_accounts.html",
        context={
            "CURRENCY": settings.KIRPPU_CURRENCY,
            "event": event,
            "menu": vendor_menu(request, event),
        }
    )
