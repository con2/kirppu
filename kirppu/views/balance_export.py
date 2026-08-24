# -*- coding: utf-8 -*-
import csv
import decimal
import hashlib
import io
import json
import typing

from django import forms
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import models, transaction
from django.http import HttpResponse, Http404, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from ..models import (
    Clerk,
    Counter,
    Event,
    EventPermission,
    Item,
    Receipt,
    ReceiptItem,
    Vendor,
    UserAdapter,
)
from ..checkout_api import compensation_end, item_mode_change
from ..provision import Provision

DataRow: typing.TypeAlias = tuple[int, str, str, str, decimal.Decimal]
DataRowEx: typing.TypeAlias = tuple[
    int,
    str,
    str,
    str,
    decimal.Decimal,
    decimal.Decimal,
    decimal.Decimal,
    decimal.Decimal,
]


def _data_iterator(
    event: Event, verbose: bool = False
) -> typing.Iterator[DataRow | DataRowEx]:
    vo = (
        Vendor.objects.filter(event=event)
        .filter(~models.Q(bank_iban=""), bank_iban__isnull=False)
        .order_by("id")
        .annotate(sum=models.Sum("item__price", filter=models.Q(item__state=Item.SOLD)))
    )

    for vendor in vo:
        provision = Provision(
            vendor_id=vendor.pk, provision_function=event.provision_function
        )

        if (vendor.sum is None or not (vendor.sum > 0)) and not (
            (provision.provision_fix or 0) > 0
        ):
            continue
        vendor_sum = (
            (vendor.sum or 0)
            + (provision.provision or 0)
            + (provision.provision_fix or 0)
        )

        name = (
            UserAdapter.full_name(vendor.user)
            if vendor.person is None
            else vendor.person.full_name()
        )
        final_sum = Item.price_fmt_for(vendor_sum, short_exact=False)
        if final_sum.is_zero():
            continue

        if verbose:
            yield (
                vendor.id,
                name,
                vendor.bank_iban,
                vendor.bank_bic,
                final_sum,
                Item.price_fmt_for(
                    provision.provision or decimal.Decimal(0), short_exact=False
                ),
                Item.price_fmt_for(
                    provision.provision_fix or decimal.Decimal(0), short_exact=False
                ),
                Item.price_fmt_for(vendor.sum or 0, short_exact=False),
            )
        else:
            yield (
                vendor.id,
                name,
                vendor.bank_iban,
                vendor.bank_bic,
                final_sum,
            )


def _hash_row(hasher, row: DataRow | DataRowEx) -> None:
    hasher.update(
        ",".join((str(row[0]), row[1], row[2] or "", str(row[4]))).encode("UTF-8")
    )


def _preconditions(request, event_slug: str) -> Event:
    event = get_object_or_404(Event, slug=event_slug)
    perms = EventPermission.get(event, request.user)
    if not perms.can_see_accounting and not request.user.is_superuser:
        raise PermissionDenied()
    if not event.collect_bank_information:
        raise Http404()
    return event


@login_required
def view(request, event_slug: str):
    event = _preconditions(request, event_slug)
    has_clerk = Clerk.objects.filter(event=event, user=request.user).exists()

    return render(
        request,
        "kirppu/balance_export.html",
        {
            "event": event,
            "enabled": has_clerk,
        },
    )


@login_required
def csv_view(request, event_slug: str):
    event = _preconditions(request, event_slug)
    verbose = request.GET.get("verbose", "0") in ("1", "true", "yes")

    hasher = hashlib.sha256()
    with io.StringIO() as buf:
        writer = csv.writer(buf, dialect=csv.excel)
        if verbose:
            writer.writerow(
                [
                    "ID",
                    _("Name"),
                    "IBAN",
                    "BIC",
                    _("Sum"),
                    "Included provision",
                    "Provision fix",
                    "Original",
                ]
            )
        else:
            writer.writerow(["ID", _("Name"), "IBAN", "BIC", _("Sum")])
        price_sum = decimal.Decimal(0)
        for v in _data_iterator(event, verbose=verbose):
            price_sum += v[-1]
            writer.writerow(v)
            _hash_row(hasher, v)

        writer.writerow([])
        writer.writerow(["", "Sum", "", "", price_sum])
        writer.writerow(["", "Content hash", "", "", "H" + hasher.hexdigest()])
        buf.seek(0)
        return HttpResponse(
            buf,
            content_type="text/csv+plain; charset=UTF-8",
            headers={"Content-Disposition": f"inline; filename={event_slug}.csv"},
        )


class ExportCompensationForm(forms.Form):
    hash = forms.CharField(required=True)
    counter_code = forms.CharField(required=True)

    def __init__(self, data, request, event: Event, hasher, *args, **kwargs):
        super().__init__(data, *args, **kwargs)
        self._request = request
        self._event = event
        self._hash_len = hasher.digest_size * 2 + 1  # 1 for prefix

        self.val_counter = None
        self.val_clerk = None
        self.val_hash = None

    def clean_hash(self):
        val: str = self.cleaned_data["hash"]
        if not val.startswith("H") or len(val) != self._hash_len:
            raise forms.ValidationError("Invalid hash")
        self.val_hash = val
        return val

    def clean_counter_code(self):
        val: str = self.cleaned_data["counter_code"]
        val = val.removeprefix(":*")
        try:
            c = Counter.objects.only("pk").get(event=self._event, identifier=val)
            self.val_counter = c
        except Counter.DoesNotExist:
            raise forms.ValidationError("Invalid counter code")
        return val

    def clean(self):
        cleaned_data = super().clean()
        try:
            c = Clerk.objects.only("pk").get(event=self._event, user=self._request.user)
            self.val_clerk = c
        except Clerk.DoesNotExist:
            raise forms.ValidationError("No clerk found for current user")
        return cleaned_data


def json_bad_request(obj: str | object):
    if isinstance(obj, str):
        return HttpResponseBadRequest(obj, content_type="application/json")
    return HttpResponseBadRequest(json.dumps(obj), content_type="application/json")


def json_vendor_pos(pos: int, vendors: list[int], clazz=HttpResponse):
    return clazz(
        json.dumps(
            {
                "index": pos,
                "length": len(vendors),
            }
        ),
        content_type="application/json",
    )


@login_required
@require_POST
def start_compensation(request, event_slug: str):
    event = _preconditions(request, event_slug)

    try:
        args = json.loads(request.body)
    except json.JSONDecodeError:
        return json_bad_request("Invalid JSON")
    hasher = hashlib.sha256()
    form = ExportCompensationForm(args, request, event, hasher)
    if not form.is_valid():
        return json_bad_request(form.errors.as_json())

    if (
        "compensation_hash" in request.session
        and "compensation_vendors" in request.session
    ):
        # Retry from error
        if form.val_hash == request.session["compensation_hash"]:
            pos = request.session["compensation_vendor_pos"]
            return json_vendor_pos(pos, request.session["compensation_vendors"])

    vendors: list[int] = []
    for v in _data_iterator(event):
        _hash_row(hasher, v)
        vendors.append(v[0])

    expected_hash = "H" + hasher.hexdigest()

    if not vendors:
        return json_bad_request({"__all__": [{"message": "Nothing to do"}]})

    if form.val_hash == expected_hash:
        request.session["compensation_hash"] = expected_hash
        request.session["compensation_vendors"] = vendors
        request.session["compensation_vendor_pos"] = 0
        request.session["compensation_clerk"] = form.val_clerk.pk
        request.session["compensation_counter"] = form.val_counter.pk
        return json_vendor_pos(0, vendors)
    return json_bad_request({"__all__": [{"message": "Bad content hash"}]})


@login_required
@require_POST
def iter_vendor(request, event_slug: str):
    event = _preconditions(request, event_slug)

    pos: int | None = request.session.get("compensation_vendor_pos")
    vendors: list[int] | None = request.session.get("compensation_vendors")
    if pos is None or not vendors:
        return HttpResponseBadRequest("Not started", content_type="text/plain")
    if pos >= len(vendors):
        return HttpResponseBadRequest("Overflow", content_type="text/plain")
    vendor_id = vendors[pos]

    new_pos = _do_compensation(request, event, pos, vendor_id)
    return json_vendor_pos(new_pos, vendors)


@transaction.atomic
def _do_compensation(request, event: Event, pos: int, vendor_id: int) -> int:
    clerk_pk: int = request.session["compensation_clerk"]
    counter_pk: int = request.session["compensation_counter"]

    counter = Counter.objects.only("pk").get(pk=counter_pk)
    clerk = Clerk.objects.only("pk").get(pk=clerk_pk)
    vendor = Vendor.objects.get(event=event, id=vendor_id)

    receipt = Receipt.objects.create(
        clerk=clerk, counter=counter, type=Receipt.TYPE_COMPENSATION, vendor=vendor
    )

    for item in Item.objects.filter(vendor=vendor, state=Item.SOLD).select_for_update():
        item_dict = item_mode_change(request, item, Item.SOLD, Item.COMPENSATED)
        ReceiptItem.objects.create(item=item, receipt=receipt)

    receipt.calculate_total()
    receipt.save()

    compensation_end(receipt.pk, vendor_id, event)

    # Prevent further modifications from the processed vendor.
    vendor.bank_lock = True
    vendor.save(update_fields=["bank_lock"])

    pos += 1
    request.session["compensation_vendor_pos"] = pos

    return pos


@login_required
@require_POST
def end_compensation(request, event_slug: str):
    event = _preconditions(request, event_slug)

    # Lock rest of the vendors too
    (
        Vendor.objects.filter(event=event)
        .filter(~models.Q(bank_skip=""), bank_skip__isnull=False)
        .update(bank_lock=True)
    )

    for k in (
        "compensation_hash",
        "compensation_vendors",
        "compensation_vendor_pos",
        "compensation_counter",
        "compensation_clerk",
    ):
        if k in request.session:
            del request.session[k]
    return HttpResponse(content_type="text/plain")


def _can_cleanup(event: Event) -> bool:
    for _ in _data_iterator(event):
        return False
    return True


@login_required
@require_POST
def check_cleanup(request, event_slug: str):
    event = _preconditions(request, event_slug)

    if _can_cleanup(event):
        if (
            Vendor.objects.filter(event=event)
            .filter(models.Q(bank_iban="!"), bank_iban__isnull=False, bank_lock=True)
            .count()
        ) > 0:
            return HttpResponse("NOP", content_type="text/plain")
        return HttpResponse("OK", content_type="text/plain")

    return HttpResponse(
        "There are vendors with bank info, without compensation",
        content_type="text/plain",
        status=409,
    )


@login_required
@require_POST
def do_cleanup(request, event_slug: str):
    event = _preconditions(request, event_slug)

    if not _can_cleanup(event):
        return HttpResponseBadRequest(
            "There are vendors with bank info, without compensation",
            content_type="text/plain",
        )

    rows = (
        Vendor.objects.filter(event=event)
        .filter(~models.Q(bank_iban=""), bank_iban__isnull=False)
        .update(bank_iban="!", bank_bic="!")
    )

    return HttpResponse(
        "Updated %d vendors" % rows,
        content_type="text/plain",
    )
