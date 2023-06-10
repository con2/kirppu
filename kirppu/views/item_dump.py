# -*- coding: utf-8 -*-
import csv
import typing

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Max, TextField
from django.db.models.functions import Length, Cast
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _, gettext

from .csv_utils import csv_streamer_view
from ..models import Event, EventPermission, Item, RemoteEvent

__all__ = [
    "dump_items_view",
]


ColFn = typing.Callable[[Item], typing.Any]

COLUMNS = (
    (_("Vendor id"), "vendor_id"),
    (_("Barcode"), "code"),
    (_("Price"), "price"),
    (_("Brought"), lambda i: i.state in (Item.BROUGHT, Item.STAGED, Item.SOLD, Item.COMPENSATED, Item.RETURNED)),
    (_("Sold"), lambda i: i.state in (Item.SOLD, Item.COMPENSATED)),
    (_("Compensated / Returned"), lambda i: i.state in (Item.COMPENSATED, Item.RETURNED)),
    (_("Name"), "name"),
)


@login_required
def dump_items_view(request, event_slug):
    event = get_object_or_404(Event, slug=event_slug)
    if not EventPermission.get(event, request.user).can_see_accounting:
        raise PermissionDenied

    as_text = request.GET.get("txt") is not None
    event = event.get_real_event()
    return csv_streamer_view(
        request,
        lambda output: item_dump(output, event, as_text),
        gettext("items")
    )


def _process_column(item, column: typing.Tuple[str, typing.Union[str, ColFn]], as_text):
    ref = column[1]
    if isinstance(ref, str):
        value = getattr(item, ref)
        if as_text:
            return value if value is not None else ""
        return value
    elif callable(ref):
        value = ref(item)
        if isinstance(value, bool):
            if as_text:
                return "\u2612" if value else "\u2610"  # BALLOT BOX WITH X and BALLOT BOX
            return "X" if value else None
        else:
            raise NotImplementedError(column[0] + " " + repr(value))
    else:
        raise NotImplementedError(column[0] + " " + repr(ref))


class TextWriter(object):
    def __init__(self, output, widths: typing.List[int]):
        self._output = output
        self._widths = widths
        self._sep = "  "
        self._pattern = self._sep.join(
            ("{:%i}" % w) if w > 0 else "{}"
            for w in widths
        )

    def writerow(self, columns):
        columns = list(columns)
        assert len(columns) == len(self._widths)
        self._output.write(self._pattern.format(*columns))
        self._output.write("\n")

    def write_staggered(self, columns):
        columns = list(columns)
        assert len(columns) == len(self._widths)
        for index, (column, width) in enumerate(zip(columns, self._widths)):
            for p in self._widths[0:index]:
                self._output.write("|  ")
                self._output.write(" " * (p - 1))
            self._output.write(column)
            self._output.write("\n")


def item_dump(output, event: typing.Union[Event, RemoteEvent], as_text):
    items = Item.objects.using(event.get_real_database_alias()).filter(vendor__event=event)

    if as_text:
        straight_column_names = [c[1] for c in COLUMNS if isinstance(c[1], str)]
        column_name_lengths = {c + "_length": Length(Cast(c, output_field=TextField())) for c in straight_column_names}
        max_column_name_lengths = {"max_" + c: Max(c + "_length") for c in straight_column_names}
        max_lengths = items.annotate(**column_name_lengths).aggregate(**max_column_name_lengths)

        column_widths = [
            (max_lengths["max_" + c[1]] if isinstance(c[1], str) else 1) or 0
            for c in COLUMNS
        ]
        # Last column doesn't need trailing padding as line is changed after that.
        column_widths[-1] = 0

        writer = TextWriter(output, column_widths)
        writer.write_staggered(str(c[0]) for c in COLUMNS)
    else:
        writer = csv.writer(output)
        writer.writerow(str(c[0]) for c in COLUMNS)

    # Used here and later for buffer streaming and clearing in case of StringIO.
    yield

    for item in items.order_by("vendor__id", "name"):
        writer.writerow(_process_column(item, c, as_text) for c in COLUMNS)
        yield
