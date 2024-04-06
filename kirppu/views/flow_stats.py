# -*- coding: utf-8 -*-
import typing
from datetime import timedelta, datetime

from django.contrib.auth.decorators import login_required
from django.db import models
from django.http import StreamingHttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404
from django.utils import timezone

from ..models import Event, EventPermission, Item, ItemStateLog, Receipt

__all__ = [
    "flow_stats",
]


class Entry(typing.Protocol):
    old_state: str
    new_state: str
    time: datetime
    vendor: int
    value: int


@login_required
def flow_stats(request, event_slug):
    event = get_object_or_404(Event, slug=event_slug)
    if not EventPermission.get(event, request.user).can_see_accounting:
        return HttpResponseForbidden()
    return StreamingHttpResponse(csv_generator(flow_generator(event)), content_type="text/plain")


def csv_generator(generator):
    for row in generator:
        yield ",".join(str(el) for el in row) + "\n"


def flow_generator(event: Event):
    receipts_q: typing.Iterable[datetime] = (
        Receipt.objects
        .filter(type=Receipt.TYPE_PURCHASE, status=Receipt.FINISHED, clerk__event=event)
        .order_by("start_time")
        .values_list("start_time", flat=True)
    )
    receipts = list(receipts_q)

    entries_q: typing.Iterable[Entry] = (
        ItemStateLog.objects
        .using(event.get_real_database_alias())
        .exclude(new_state=Item.ADVERTISED)
        .filter(item__vendor__event=event)
        .annotate(vendor=models.F("item__vendor__id"))
        .only("old_state", "new_state", "time")
        .annotate(value=models.Value(1, output_field=models.IntegerField()))
        .order_by("time")
    )

    vendors: set[int] = set()
    balance = {
        "items_brought": 0,
        "items_sold": 0,
        "receipts": 0,
        "vendors_brought": 0,
    }
    previous_balance = balance.copy()

    bucket_index = 0
    bucket_time: datetime | None = None
    bucket_td = timedelta(minutes=60)

    yield make_header()

    for entry in entries_q:
        if bucket_time is None:
            bucket_time = truncate_to_hour(entry.time)
            # Start the graph before the first entry, such that everything starts at zero.
            start_time = bucket_time - bucket_td
            receipt_count, receipts = iter_receipt_times(receipts, bucket_time + bucket_td)
            balance["receipts"] += receipt_count
            yield make_row(start_time, balance, previous_balance, bucket_index)
            dict_copy(balance, previous_balance)
            bucket_index += 1

        elif (entry.time - bucket_time) > bucket_td:
            # Fart out what was in the old bucket and start a new bucket.
            receipt_count, receipts = iter_receipt_times(receipts, bucket_time + bucket_td)
            balance["receipts"] += receipt_count
            yield make_row(bucket_time, balance, previous_balance, bucket_index)
            dict_copy(balance, previous_balance)
            bucket_index += 1
            bucket_time = truncate_to_hour(entry.time)

        item_weight = entry.value

        if entry.old_state == Item.ADVERTISED and entry.new_state != Item.ADVERTISED:
            balance["items_brought"] += item_weight
            if entry.vendor not in vendors:
                vendors.add(entry.vendor)
                balance["vendors_brought"] += 1

        if entry.new_state == Item.SOLD:
            # Old state likely ST, but allow also BR and AD (data before state log).
            balance["items_sold"] += item_weight
        elif entry.old_state == Item.SOLD and entry.new_state == Item.BROUGHT:
            # Item is un-sold, returned to BR.
            balance["items_sold"] -= item_weight

    # Fart out the last bucket.
    if bucket_time is not None:
        receipt_count, receipts = iter_receipt_times(receipts, bucket_time + bucket_td)
        balance["receipts"] += receipt_count
        yield make_row(bucket_time, balance, previous_balance, bucket_index)
        dict_copy(balance, previous_balance)  # unused, but for symmetry.


def truncate_to_hour(dt: datetime) -> datetime:
    return dt.replace(minute=0, second=0, microsecond=0)


def make_header():
    return [
        "hour_index",
        "start_time",

        "items_brought",
        "items_sold",
        "vendors_brought",
        "receipts",

        "items_brought_delta",
        "items_sold_delta",
        "vendors_brought_delta",
        "receipts_delta",
    ]


def make_row(bucket: datetime, balance: dict[str, int], previous_balance: dict[str, int], index: int) -> list:
    delta = dot_sub(balance, previous_balance)
    return [
        index,
        # First convert to local, then remove tz as csv datetime apparently don't expect tz info.
        timezone.localtime(bucket).replace(tzinfo=None).isoformat(timespec="seconds"),

        balance["items_brought"],
        balance["items_sold"],
        balance["vendors_brought"],
        balance["receipts"],

        delta["items_brought"],
        delta["items_sold"],
        delta["vendors_brought"],
        delta["receipts"],
    ]


def dot_sub(a: dict[str, int], b: dict[str, int]) -> dict[str, int]:
    return {
        k: a[k] - b[k]
        for k in a.keys()
    }


def dict_copy(src: dict[str, int], to: dict[str, int]):
    for k, v in src.items():
        to[k] = v


def iter_receipt_times(
        receipts: list[datetime],
        until: datetime,
) -> tuple[int, list[datetime]]:
    n = 0
    for index, entry in enumerate(receipts):
        if entry >= until:
            return n, receipts[index:]
        n += 1
    return n, []
