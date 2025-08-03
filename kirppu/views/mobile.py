# -*- coding: utf-8 -*-
from collections import OrderedDict
from decimal import Decimal
import textwrap

from django.conf import settings
from django.core import signing
from django.db import transaction, models
from django.db.models import Count, Q
from django.http import HttpResponseRedirect
from django.http.response import HttpResponseForbidden, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse, resolve
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST
from ipware.ip import get_client_ip
from django_ratelimit.core import is_ratelimited

from ..models import Box, Event, Item, Receipt, ReceiptExtraRow, TemporaryAccessPermit, TemporaryAccessPermitLog, Vendor
from ..provision import Provision
from ..templatetags.kirppu_login import login_url, logout_url
from ..templatetags.kirppu_tags import format_price
from ..util import first, shorten_text

__all__ = [
    "index",
    "logout",
]


_PERMIT_SESSION_KEY = "temporary_permit_key"


class Table(object):
    def __init__(self, states, title, hidden=False, checkable=False, custom_filter=None):
        self.states = states
        self.title = title
        self.hidden = hidden
        self.checkable = checkable
        self.custom_filter = custom_filter

    def filter(self, item):
        if self.custom_filter:
            return self.custom_filter(self, item)
        else:
            return item.state in self.states


TABLES = {
    "returnable": Table(
        [Item.BROUGHT, Item.STAGED],
        title=_('Returnable Items'),
        checkable=True,
    ),
    "compensable": Table(
        [Item.SOLD],
        title=_('Compensable Items'),
    ),
    "compensated": Table(
        [Item.COMPENSATED],
        title=_('Compensated Items'),
    ),
    "other": Table(
        [Item.MISSING, Item.RETURNED],
        title=_('Other Items'),
    ),
    "registered": Table(
        [Item.ADVERTISED],
        title=_('Not brought to event'),
        hidden=True,
    ),
}

TABLES_ORDER = [
    "returnable",
    "compensable",
    "compensated",
    "other",
    "registered",
]

TABLE_FOR_STATE = {}


def __populate_table_for_state():
    for key, table in TABLES.items():
        for state in table.states:
            TABLE_FOR_STATE.setdefault(state, []).append(key)


__populate_table_for_state()


class TableContents(object):
    def __init__(self, spec):
        self.spec = spec
        self.items = []
        self.pre_sum_line = ()
        self.sum = Decimal(0)


def _get_client_ip(request):
    client_ip, routable = get_client_ip(request)
    return client_ip


def _ratelimit_key(group, request):
    return _get_client_ip(request)


def _login_view(request, event):
    errors = []
    if request.method == "POST":
        key = request.POST.get("key", "")
        if len(key) == 0:
            errors.append(_("Access key must be given"))
        elif is_ratelimited(
                request,
                fn=_login_view,
                key=_ratelimit_key,
                rate=settings.KIRPPU_MOBILE_LOGIN_RATE_LIMIT,
                increment=True):
            errors.append(_("You are trying too much. Try again later."))
        else:
            with transaction.atomic():
                try:
                    permit = TemporaryAccessPermit.objects.get(short_code=key)
                except TemporaryAccessPermit.DoesNotExist:
                    errors.append(_("Invalid access key"))
                else:
                    can_use = permit.state == TemporaryAccessPermit.STATE_UNUSED\
                              and permit.expiration_time >= timezone.now()

                    TemporaryAccessPermitLog.objects.create(
                        permit=permit,
                        action=TemporaryAccessPermitLog.ACTION_USE if can_use else TemporaryAccessPermitLog.ACTION_TRY,
                        address=shorten_text(_get_client_ip(request) + "; " + request.META.get("REMOTE_HOST", ""),
                                             TemporaryAccessPermitLog._meta.get_field("address").max_length, False),
                        peer=shorten_text(request.META.get("HTTP_USER_AGENT", ""),
                                          TemporaryAccessPermitLog._meta.get_field("peer").max_length, False)
                    )

                    if can_use:
                        permit.state = TemporaryAccessPermit.STATE_IN_USE
                        permit.save(update_fields=("state",))
                        request.session[_PERMIT_SESSION_KEY] = permit.pk
                        return HttpResponseRedirect(reverse("kirppu:mobile", kwargs={"event_slug": event.slug}))
                    else:
                        errors.append(_("Invalid access key"))

    field = TemporaryAccessPermit._meta.get_field("short_code")
    min_length = first(field.validators, lambda v: v.code == "min_length")
    return render(request, "kirppu/vendor_status_login.html", {
        'event': event,
        'min_length': min_length.limit_value if min_length else 0,
        'max_length': field.max_length,
        'errors': errors,
    })


def _data_view(request, event: Event, permit):
    original_event = event
    if permit:
        vendor = permit.vendor
        database = "default"
        default_database = True
    else:
        database = event.get_real_database_alias()
        default_database = database == "default"
        try:
            vendor = Vendor.get_vendor(request, event=event.get_real_event())
        except Vendor.DoesNotExist:
            vendor = None
        if vendor is None:
            if request.GET.get("type") == "txt":
                return HttpResponse(_("Unregistered vendor."), content_type="text/plain; charset=utf-8")
            return render(request, "kirppu/vendor_status.html", {
                "tables": {},
                "CURRENCY": settings.KIRPPU_CURRENCY,
                "event": event,
                "event_slug": original_event.slug,
                "vendor": request.user,
                "logout_next": reverse("kirppu:vendor_view", kwargs={"event_slug": event.slug}),
            })

    if default_database and not vendor.mobile_view_visited:
        vendor.mobile_view_visited = True
        vendor.save(update_fields=("mobile_view_visited",))

    items = Item.objects \
        .using(database) \
        .filter(vendor=vendor, hidden=False) \
        .select_related("box") \
        .order_by("name") \
        .only("id", "hidden", "price", "state", "code", "name", "box__id")

    box_objects = (
        Box.objects
        .using(database)
        .filter(item__vendor=vendor)
        .values("pk", "item__price", "item__state")
        .annotate(item_count=Count("item", filter=Q(item__hidden=False)),
                  box_code=models.F("representative_item__code"),
                  box_number=models.F("box_number"),
                  description=models.F("description"))
    )

    boxes = {(box["pk"], box["item__state"], box["item__price"]): box for box in box_objects}
    box_total_items = {}
    for key, box in boxes.items():
        pk = box["pk"]
        box_total_items[pk] = box_total_items.get(pk, 0) + box["item_count"]

    currency_length = len(format_price(Decimal(0))) - 1

    tables = OrderedDict((k, TableContents(spec=TABLES[k])) for k in TABLES_ORDER)
    max_price_width = 0
    for item in items:
        table_key = TABLE_FOR_STATE[item.state]
        for candidate in table_key:
            table_spec = TABLES[candidate]
            if table_spec.filter(item) and candidate in tables:
                table = tables[candidate]  # type: TableContents
                row = None

                price_value = None
                price_multiplier = 1

                if item.box is not None:
                    pk = item.box.pk
                    key = pk, item.state, item.price
                    box = boxes.get(key)
                    if box is not None:
                        del boxes[key]
                        row = _box(box, box_total_items[pk])

                        price_multiplier = box["item_count"]
                        price_value = box["item__price"]
                else:
                    row = _item(item)
                    price_value = item.price

                if row is not None:
                    max_price_width = max(max_price_width, len(str(row["price"])) + currency_length)
                    table.items.append(row)
                    table.sum += price_value * price_multiplier
                break

    if event.provision_function:
        compensable = tables["compensable"]
        if compensable.items:
            provision = Provision(vendor_id=vendor.id, provision_function=event.provision_function, database=database)
            to_be_provision = provision.provision + provision.provision_fix
            compensable.pre_sum_line = (_("provision:"), to_be_provision)
            compensable.sum += to_be_provision

        compensated = tables["compensated"]
        if compensated.items:
            current_provision = ReceiptExtraRow.objects.using(database).filter(
                type__in=(ReceiptExtraRow.TYPE_PROVISION, ReceiptExtraRow.TYPE_PROVISION_FIX),
                receipt__type=Receipt.TYPE_COMPENSATION,
                receipt__items__vendor=vendor,
            ).distinct().aggregate(sum=models.Sum("value"))["sum"] or Decimal(0)

            current_provision = Item.price_fmt_for(current_provision)
            compensated.pre_sum_line = (_("provision:"), current_provision)
            compensated.sum += current_provision

    if request.GET.get("type") == "txt":
        sign_data = {}
        total_items = 0
        for key, table in tables.items():
            if key == "registered":
                continue
            items = [_sign_data(i) for i in table.items]
            total_items += len(items)
            sign_data[key] = items
            sign_data[key + "_s"] = str(table.sum)
            if table.pre_sum_line:
                sign_data[key + "_p"] = str(table.pre_sum_line[1])

        if total_items > 0:
            sign_data["vendor"] = vendor.id
            sign_data["event"] = event.slug
            signature = signing.dumps(sign_data, compress=True)
            signature = "\n".join(textwrap.wrap(signature, 78, break_on_hyphens=False))
        else:
            signature = None

        return render(request, "kirppu/vendor_status.txt", {
            "event_slug": original_event.slug,
            "tables": tables,
            "price_width": max_price_width,
            "vendor": vendor.id,
            "signature": signature,
        }, content_type="text/plain; charset=utf-8")
    return render(request, "kirppu/vendor_status.html", {
        "event": event,
        "event_slug": original_event.slug,
        "tables": tables,
        "CURRENCY": settings.KIRPPU_CURRENCY,
        "vendor": vendor.id,
        "logout_next": reverse("kirppu:vendor_view", kwargs={"event_slug": event.slug}),
    })


def _item(item):
    return {
        "code": item.code,
        "price": item.price_fmt,
        "name": item.name,
    }


def _box(box, total):
    """
    :type box: dict
    :type total: int
    """
    return {
        "box": True,
        "code": box["box_code"],
        "number": box["box_number"],
        "price": Item.price_fmt_for(box["item__price"]),
        "name": box["description"],
        "value": box["item_count"],
        "total": total,
    }


def _sign_data(item_dict):
    if "box" in item_dict:
        return "{}@{}:{}/{}".format(item_dict["code"], item_dict["price"], item_dict["value"], item_dict["total"])
    return "{}@{}".format(item_dict["code"], item_dict["price"])


def _is_permit_valid(request):
    if _PERMIT_SESSION_KEY in request.session:
        try:
            permit = TemporaryAccessPermit.objects.get(pk=request.session[_PERMIT_SESSION_KEY])
            if permit.state in (TemporaryAccessPermit.STATE_EXHAUSTED, TemporaryAccessPermit.STATE_INVALIDATED):
                raise TemporaryAccessPermit.DoesNotExist()

            if permit.state == TemporaryAccessPermit.STATE_UNUSED and permit.expiration_time < timezone.now():
                raise TemporaryAccessPermit.DoesNotExist()

            return permit

        except TemporaryAccessPermit.DoesNotExist:
            del request.session[_PERMIT_SESSION_KEY]
            return None
    else:
        return None


def index(request, event_slug):
    event = get_object_or_404(Event, slug=event_slug)
    if not event.mobile_view_visible:
        return HttpResponseForbidden(_("This location is not in use."))

    if request.user.is_authenticated:
        return _data_view(request, event, None)
    elif event.source_db:
        # If data comes from external database, allow visibility only via real login.
        return HttpResponseRedirect(login_url(reverse("kirppu:mobile", kwargs={"event_slug": event_slug})))
    else:
        permit = _is_permit_valid(request)
        if permit:
            return _data_view(request, event, permit)
        else:
            return _login_view(request, event)


@require_POST
def logout(request, event_slug):
    event = get_object_or_404(Event, slug=event_slug)
    # TODO: Check session and temporary_codes, remove both.
    if _PERMIT_SESSION_KEY in request.session:
        permit = TemporaryAccessPermit.objects.get(pk=request.session[_PERMIT_SESSION_KEY])
        if settings.KIRPPU_EXHAUST_SHORT_CODE_ON_LOGOUT:
            permit.state = TemporaryAccessPermit.STATE_EXHAUSTED
        else:
            permit.state = TemporaryAccessPermit.STATE_UNUSED
        permit.save(update_fields=["state"])

        del request.session[_PERMIT_SESSION_KEY]

    if request.user.is_authenticated:
        # XXX: Call the actual logout with same request object to perform the real logout.
        # The ?next query parameter gets passed as is.
        func, args, kwargs = resolve(settings.LOGOUT_URL)
        return func(request, *args, **kwargs)
    else:
        request.session.flush()
        return HttpResponseRedirect(reverse("kirppu:mobile", kwargs={"event_slug": event.slug}))
