import logging
import math
import random
import re
import typing

from django.conf import settings

from django.core.exceptions import ValidationError
from django.db import models, transaction, IntegrityError
from django.db.models import Q, F, Count
from django.http.response import (
    HttpResponse,
    JsonResponse,
    StreamingHttpResponse,
)
from django.shortcuts import (
    get_object_or_404,
    render,
    reverse,
)
from django.utils.translation import gettext as _
from django.utils.timezone import now
from ipware.ip import get_client_ip

from .api.common import (
    get_item_or_404 as _get_item_or_404,
    item_state_conflict as _item_state_conflict,
    get_receipt,
)
from .provision import Provision
from .models import (
    Item,
    ItemType,
    Receipt,
    Clerk,
    Counter,
    Event,
    EventPermission,
    Account,
    ReceiptItem,
    ReceiptExtraRow,
    Vendor,
    VendorNote,
    ItemStateLog,
    Box,
    TemporaryAccessPermit,
    TemporaryAccessPermitLog,
    decimal_to_transport,
    default_temporary_access_permit_expiry,
)
from .fields import ItemPriceField
from .forms import remove_item_from_receipt

from . import ajax_util, stats
from .ajax_util import (
    AjaxError,
    get_all_ajax_functions,
    get_counter,
    get_clerk,
    empty_as_none,
    RET_ACCEPTED,
    RET_BAD_REQUEST,
    RET_CONFLICT,
    RET_FORBIDDEN,
    RET_AUTH_FAILED,
    RET_LOCKED,
)

# Must be imported, for part to be included at all in the API.
# noinspection PyUnresolvedReferences
from . import api  # isort: skip


ajax_func = ajax_util.ajax_func_factory("checkout")
logger = logging.getLogger(__name__)


def raise_if_item_not_available(item):
    """Raise appropriate AjaxError if item is not in buyable state."""
    if item.state == Item.STAGED:
        # Staged somewhere other?
        raise AjaxError(RET_LOCKED, 'Item is already staged to be sold.')
    elif item.state == Item.ADVERTISED:
        return 'Item has not been brought to event.'
    elif item.state in (Item.SOLD, Item.COMPENSATED):
        raise AjaxError(RET_CONFLICT, 'Item has already been sold.')
    elif item.state == Item.RETURNED:
        raise AjaxError(RET_CONFLICT, 'Item has already been returned to owner.')
    return None


def checkout_js(request, event_slug):
    """
    Render the JavaScript file that defines the AJAX API functions.
    """
    event = get_object_or_404(Event, slug=event_slug)
    context = {
        'funcs': get_all_ajax_functions(),
        'api_name': 'Api',
        'event': event,
    }
    return render(
        request,
        "kirppu/app_ajax_api.js",
        context,
        content_type="application/javascript"
    )


@transaction.atomic
def item_mode_change(request, code, from_, to, message_if_not_first=None):
    if isinstance(code, Item):
        item = code
    else:
        item = _get_item_or_404(code, for_update=True)
    if not isinstance(from_, tuple):
        from_ = (from_,)
    if item.state in from_:
        if item.hidden:
            # If an item is brought to the event, even though the user deleted it, it should begin showing again in
            # users list. The same probably applies to any interaction with the item.
            item.hidden = False

        ItemStateLog.objects.log_state(item=item, new_state=to, request=request)
        old_state = item.state
        item.state = to
        item.save(update_fields=("state", "hidden"))
        ret = item.as_dict()
        if message_if_not_first is not None and len(from_) > 1 and old_state != from_[0]:
            ret.update(_message=message_if_not_first)
        return ret

    else:
        # Item not in expected state.
        _item_state_conflict(item)


@ajax_func('^clerk/login$', clerk=False, counter=False)
def clerk_login(request, event, code, counter):
    if counter is not None and any(c not in Counter.PRIVATE_KEY_ALPHABET for c in counter):
        raise AjaxError(RET_BAD_REQUEST, "Invalid key")
    try:
        counter_obj = Counter.objects.get(event=event, private_key=counter)
    except Counter.DoesNotExist:
        raise AjaxError(RET_AUTH_FAILED, _(u"Counter has gone missing."))

    try:
        clerk = Clerk.by_code(code, event=event)
    except ValueError as ve:
        raise AjaxError(RET_AUTH_FAILED, repr(ve))

    if clerk is None:
        raise AjaxError(RET_AUTH_FAILED, _(u"No such clerk."))

    clerk_data = clerk.as_dict()
    permissions = EventPermission.get(event, clerk.user)
    oversee = permissions.can_perform_overseer_actions
    clerk_data['overseer_enabled'] = oversee
    clerk_data['stats_enabled'] = oversee or permissions.can_see_statistics

    active_receipts = Receipt.objects.filter(clerk=clerk, status=Receipt.PENDING, type=Receipt.TYPE_PURCHASE)
    if active_receipts:
        if len(active_receipts) > 1:
            clerk_data["receipts"] = [receipt.as_dict() for receipt in active_receipts]
            clerk_data["receipt"] = "MULTIPLE"
        else:
            receipt = active_receipts[0]
            if "receipt" in request.session:
                logging.warning("Previous receipt reference found in session at login.")
            request.session["receipt"] = receipt.pk
            clerk_data["receipt"] = receipt.as_dict()

    elif "receipt" in request.session:
        logging.warning("Stale receipt reference found in session at login.")
        del request.session["receipt"]

    request.session["clerk"] = clerk.pk
    request.session["clerk_token"] = clerk.access_key
    request.session["counter"] = counter_obj.pk
    request.session["counter_key"] = counter_obj.private_key
    request.session["event"] = event.pk
    return clerk_data


@ajax_func('^clerk/logout$', clerk=False, counter=False)
def clerk_logout(request):
    """
    Logout currently logged in clerk.
    """
    # Does not matter which event is being used, the logout shall always succeed.
    clerk_logout_fn(request)
    return HttpResponse(content_type="application/json", content=b"{}")


def clerk_logout_fn(request):
    """
    The actual logout procedure that can be used from elsewhere too.

    :param request: Active request, for session access.
    """
    for key in ["clerk", "clerk_token", "compensation", "counter", "counter_key", "event", "receipt"]:
        request.session.pop(key, None)


@ajax_func('^counter/validate$', clerk=False, counter=False, ignore_session=True)
def counter_validate(request, event, code=None, key=None):
    """
    Validates the counter identifier and returns its exact form, if it is
    valid.
    Either `code` or `key` must be given, `code` being the counter identifier code,
    and `key` being the private key used after first validation has been done.
    """
    if code is None and key is None:
        raise AjaxError(RET_BAD_REQUEST, "Either code or key must be given")
    if key is not None and any(c not in Counter.PRIVATE_KEY_ALPHABET for c in key):
        raise AjaxError(RET_BAD_REQUEST, "Invalid key")

    try:
        if key is None:
            counter = Counter.objects.get(event=event, identifier__iexact=code)
            if counter.private_key is not None:
                raise AjaxError(RET_CONFLICT, "Requested counter is already in use.")
            counter.assign_private_key()
        else:
            counter = Counter.objects.get(event=event, private_key=key)
        clerk_logout_fn(request)
    except Counter.DoesNotExist:
        raise AjaxError(RET_AUTH_FAILED)

    return {
        "counter": counter.identifier,
        "event_name": event.name,
        "name": counter.name,
        "key": counter.private_key,
        "expires": 14,
        "path": reverse("kirppu:vendor_view", kwargs={"event_slug": event.slug}),
    }


@ajax_func('^counter/list$', clerk=False, counter=False, ignore_session=True)
def counter_list(request, event, code):
    if not settings.KIRPPU_COUNTER_LIST:
        raise AjaxError(404, "Api is not enabled")
    try:
        if Clerk.by_code(code, event=event) is None:
            raise AjaxError(RET_FORBIDDEN)
    except ValueError:
        raise AjaxError(RET_BAD_REQUEST)
    counters = Counter.objects.filter(event=event, private_key__isnull=True).values_list("name", flat=True)
    return list(counters)


@ajax_func('^item/find$', method='GET')
def item_find(request, event, code, available=None):
    item = _get_item_or_404(code, event=event)
    value = item.as_dict()
    if "available" in request.GET:
        if item.state == Item.STAGED:
            suspended = item.receipt_set.filter(status=Receipt.SUSPENDED, type=Receipt.TYPE_PURCHASE).distinct()
            if len(suspended) == 1:
                suspended = suspended[0]
                value.update(receipt=suspended.as_dict())
                return JsonResponse(
                    value,
                    status=RET_LOCKED,
                    content_type='application/json',
                )

        message = raise_if_item_not_available(item)
        if message is not None:
            value.update(_message=message)
    return value


@ajax_func('^item/search$', method='GET', overseer=True)
def item_search(request, event, query, code, box_number, vendor, min_price, max_price, item_type, item_state, is_box, show_hidden):

    clauses = []
    name_clauses = []
    description_clauses = []

    types = item_type.split()
    if types:
        clauses.append(Q(itemtype_id__in=types))

    code = code.strip()
    if code:
        clauses.append(Q(code__contains=code))

    if box_number:
        clauses.append(Q(box__box_number=int(box_number)))

    if vendor:
        clauses.append(Q(vendor=vendor))

    states = item_state.split()
    if states:
        clauses.append(Q(state__in=states))

    for part in query.split():
        p = Q(name__icontains=part)
        d = Q(box__description__icontains=part)
        if Item.is_item_barcode(part):
            p |= Q(code=part)
            d |= Q(box__representative_item__code=part)
        name_clauses.append(p)
        description_clauses.append(d)

    try:
        clauses.append(Q(price__gte=float(min_price)))
    except ValueError:
        pass

    try:
        clauses.append(Q(price__lte=float(max_price)))
    except ValueError:
        pass

    if is_box:
        clauses.append(Q(box__isnull=False if is_box == "yes" else True))

    if show_hidden not in ("true", "1", "on"):
        clauses.append(Q(hidden=False))

    item_clauses = clauses + name_clauses
    box_clauses = clauses + description_clauses
    results = []

    for item in (
        Item.objects
        .filter(*item_clauses, box__isnull=True, vendor__event=event)
        .select_related("itemtype", "vendor", "vendor__user")
        .all()
    ):
        item_dict = item.as_dict()
        item_dict['vendor'] = item.vendor.as_dict()
        results.append(item_dict)

    box_item_details = dict()
    box_item_detail_query = (
        Item.objects
            .filter(*box_clauses, box__isnull=False, vendor__event=event)
            .values("box", "price", "state")
            .annotate(item_count=Count("id"))
            .values_list("box", "item_count", "price", "state")
    )
    box_item_counts = dict()
    for entry in box_item_detail_query:
        box_id = entry[0]
        count_prices = box_item_details.setdefault(box_id, list())
        count_prices.append(
            {
                "count": entry[1],
                "price": decimal_to_transport(entry[2]),
                "state": entry[3],
            }
        )
        box_item_counts[box_id] = entry[1] + box_item_counts.get(box_id, 0)

    if box_item_counts:
        for item in (
            Item.objects
            .filter(*box_clauses, box__representative_item__id=F("pk"), vendor__event=event)
            .select_related("box", "itemtype", "vendor", "vendor__user")
            .all()
        ):
            item_dict = item.as_dict()
            details = box_item_details[item.box_id]
            box_item_states = {g["state"] for g in details}
            for k, v in Box.ITEM_SET_REDUCED_STATE.items():
                if v(box_item_states):
                    item_dict["state"] = k
                    item_dict["state_display"] = Item(state=k).get_state_display()
                    break
            else:
                item_dict["state"] = "??"
                item_dict["state_display"] = "??: " + str(box_item_states)
                logger.error("No matching group for states: %s", str(box_item_states))

            item_dict['name'] = item.box.description
            item_dict['vendor'] = item.vendor.as_dict()
            item_dict['box'] = {
                "box_number": item.box.box_number,
                "bundle_size": item.box.bundle_size,
                "item_count": box_item_counts[item.box_id],
                "item_prices": details,
            }
            results.append(item_dict)

    return results


def _box_prices(box: Box) -> list:
    price_counts = box.item_set.values("price", "state").annotate(count=Count("id"))
    return list(
        {
            "count": p["count"],
            "price": decimal_to_transport(p["price"]),
            "state": p["state"],
        }
        for p in price_counts
    )


@ajax_func('^item/edit$', method='POST', overseer=True, atomic=True)
def item_edit(request, event, code, price, state):
    try:
        price = ItemPriceField().clean(price)
    except ValidationError as v:
        raise AjaxError(RET_BAD_REQUEST, ' '.join(v.messages))

    if state not in {st for (st, _) in Item.STATE}:
        raise AjaxError(RET_BAD_REQUEST, 'Unknown state: {0}'.format(state))

    item = _get_item_or_404(code, for_update=True, event=event)
    if item.box_id is not None:
        return _box_edit(request, item.box, price, state)
    else:
        return _item_edit(request, item, price, state)


def _item_edit(request, item, price, state):
    updates = set()

    if price != item.price:
        updates.add("price")
        price_editable_states = {
            Item.ADVERTISED,
            Item.BROUGHT,
        }
        if (item.state not in price_editable_states and
                state not in price_editable_states):
            raise AjaxError(
                RET_BAD_REQUEST,
                'Cannot change price in state "{0}"'.format(item.get_state_display())
            )

    if item.state != state:
        updates.add("state")
        unsold_states = {
            Item.ADVERTISED,
            Item.BROUGHT,
            Item.MISSING,
            Item.RETURNED,
        }
        # Removing already sold item from receipt.
        if item.state not in unsold_states and item.state != Item.STAGED and state in unsold_states:
            # Need to remove item from receipt.
            receipt_ids = ReceiptItem.objects.filter(
                action=ReceiptItem.ADD,
                item=item,
            ).values_list('receipt_id', flat=True)

            for receipt_id in receipt_ids:
                receipt = Receipt.objects.get(pk=receipt_id)
                remove_item_from_receipt(request, item, receipt)
                account_id = receipt.dst_account_id
                Account.objects.filter(pk=account_id).update(balance=F("balance") - price)
        elif item.state == Item.RETURNED and state in Item.BROUGHT:
            # Allow this.
            ItemStateLog.objects.log_state(item, state, request)
        else:
            raise AjaxError(
                RET_BAD_REQUEST,
                u'Cannot change state from "{0}" to "{1}".'.format(
                    item.get_state_display(), str(dict(Item.STATE)[state])
                )
            )

    item.state = state
    item.price = price
    item.save(update_fields=updates)

    item_dict = item.as_dict()
    item_dict['vendor'] = item.vendor.as_dict()
    return item_dict


def _box_edit(request, box, price, state):
    if box.item_set.filter(state=Item.STAGED).exists():
        raise AjaxError(RET_LOCKED, _("Some box items are currently staged and cannot be changed."))
    available_items = box.item_set.filter(state__in=(Item.ADVERTISED, Item.BROUGHT))
    any_item = available_items.first()
    if any_item is None:
        raise AjaxError(RET_BAD_REQUEST, _("Nothing left to change"))
    if any(i.price != any_item.price for i in available_items):
        raise AjaxError(RET_CONFLICT, "Available box item prices are in conflicting state")

    if price != any_item.price:
        available_items.update(price=price)

    representative = box.representative_item
    item_dict = representative.as_dict()
    item_dict['vendor'] = representative.vendor.as_dict()
    item_dict['box'] = {
        "box_number": box.box_number,
        "bundle_size": box.bundle_size,
        "item_prices": _box_prices(box),
    }
    return item_dict


@ajax_func('^item/list$', method='GET')
def item_list(request, event, vendor):
    items = (Item.objects
             .filter(vendor__id=vendor, vendor__event=event, box__isnull=True)
             .select_related("itemtype")
             .order_by("name")
             )
    return [i.as_dict() for i in items]


@ajax_func('^vendor/returnable$', method='GET')
def vendor_returnable_items(request, vendor):
    # Items that can be returned with box representative items (without other box items).
    items = Item.objects \
        .exclude(state=Item.ADVERTISED) \
        .filter(Q(vendor__id=vendor) & (Q(box__isnull=True) | Q(box__representative_item__pk=F("pk")))) \
        .select_related("itemtype", "box")

    # Shrink boxes to single representative items with box information.
    boxes = Box.objects \
        .filter(item__vendor__id=vendor) \
        .annotate(
            item_count=Count("item", filter=Q(item__hidden=False)),
            returnable_count=Count(1, filter=Q(item__state=Item.BROUGHT)),
            returned_count=Count(1, Q(item__state=Item.RETURNED)),
        )
    boxes = {b.representative_item_id: b for b in boxes}

    # Merge the two queries to a single response.
    r = []
    for i in items:
        box = boxes.get(i.pk)  # type: Box
        element = i.as_dict()
        if box is not None:
            element.update(
                box={
                    "id": box.id,
                    "description": box.description,
                    "box_number": box.box_number,
                    "item_count": box.item_count,
                    "returnable_count": box.returnable_count,
                    "returned_count": box.returned_count,
                }
            )
        r.append(element)

    return sorted(r, key=lambda e: e["name"])


@ajax_func('^item/compensable', method='GET', atomic=True)
def compensable_items(request, event, vendor):
    vendor = int(vendor)
    vendor_items = (
        Item.objects
        .filter(vendor__id=vendor)
        .select_related("itemtype")
        .annotate(box_number=F("box__box_number"), box_code=F("box__representative_item__code"))
        .order_by("name")
    )

    items_for_compensation = vendor_items.filter(state=Item.SOLD)

    def format_dict(item):
        i = item.as_dict()
        if item.box_id is not None:
            i["box_number"] = item.box_number
            i["box_code"] = item.box_code
            # Pk needed, as box items don't have code anymore.
            i["code"] = None
            i["pk"] = item.pk
        return i

    r = dict(items=[format_dict(i) for i in items_for_compensation])

    provision = Provision(vendor_id=vendor, provision_function=event.provision_function)
    if provision.has_provision:
        # DON'T SAVE THESE OBJECTS!
        provision_obj = ReceiptExtraRow(
            type=ReceiptExtraRow.TYPE_PROVISION,
            value=provision.provision,
        )
        r["extras"] = [provision_obj.as_dict()]

        if not provision.provision_fix.is_zero():
            # print(provision.provision_fix, provision.provision_fix.is_zero())

            provision_fixup_obj = ReceiptExtraRow(
                type=ReceiptExtraRow.TYPE_PROVISION_FIX,
                value=provision.provision_fix,
            )
            r["extras"].append(provision_fixup_obj.as_dict())

    return r


@ajax_func('^box/list$', method='GET')
def box_list(request, vendor):
    out_boxes = []
    boxes = (
        Box.objects
        .filter(item__vendor__id=vendor, item__hidden=False)
        .select_related("representative_item", "representative_item__itemtype")
        .annotate(
            count=Count("item"),
            brought=Count("item", Q(item__state__in=(
                Item.BROUGHT, Item.STAGED, Item.SOLD, Item.COMPENSATED, Item.RETURNED))),
            returnable=Count("item", Q(item__state__in=(Item.BROUGHT, Item.STAGED))),
        )
        .distinct()
    )
    box_detail_data = (
        Box.objects
        .filter(item__vendor__id=vendor, item__hidden=False)
        .values("id", "item__price")
        .annotate(
            sold=Count("item", Q(item__state=Item.SOLD)),
            compensated=Count("item", Q(item__state=Item.COMPENSATED)),
        )
        .distinct()
    )
    box_details = {}
    for detail in box_detail_data:
        box_details.setdefault(detail["id"], []).append(detail)

    for box in boxes:
        # item_count is already resolved more efficiently.
        # item_price may be multi-valued.
        data = box.as_dict(exclude=("item_count", "item_price"))
        details = box_details[box.id]
        data["item_count"] = box.count
        data["items_brought_total"] = box.brought
        data["items_returnable"] = box.returnable

        for detail in details:
            stat = {
                "items_sold": detail["sold"],
                "items_compensated": detail["compensated"],
            }
            price = decimal_to_transport(detail["item__price"])
            data.setdefault("counts", {})[price] = stat

        out_boxes.append(data)
    return out_boxes


@ajax_func('^item/checkin$', atomic=True)
def item_checkin(request, event, code, vendor: int, note: typing.Optional[str] = None):
    item = _get_item_or_404(code, for_update=True, event=event)
    if not item.vendor.terms_accepted:
        raise AjaxError(500, _(u"Vendor has not accepted terms!"))
    clerk = get_clerk(request)

    if item.state != Item.ADVERTISED:
        _item_state_conflict(item)

    if not vendor or item.vendor_id != int(vendor):
        return JsonResponse(
            item.as_dict(),
            status=RET_ACCEPTED,
            reason="NOT CHANGED",
        )

    left_count = None
    if event.max_brought_items is not None:
        count = 1 if event.box_as_single_brought_item or item.box is None else item.box.get_item_count()
        brought_count = Item.get_brought_count(event, item.vendor)
        if brought_count + count > event.max_brought_items:
            raise AjaxError(RET_CONFLICT, _("Too many items brought, limit is %i!") % event.max_brought_items)
        else:
            left_count = event.max_brought_items - brought_count - count

    if item.box is not None:
        # Client did not expect box, but this is a box.
        # Assign box number and return box information to client.
        # Expecting a retry to box_checkin.
        box = item.box
        box.assign_box_number()

        response = item.as_dict()
        response["box"] = box.as_dict()

        # TODO: Consider returning bad request to clearly separate actual success.
        return JsonResponse(response, status=RET_ACCEPTED, reason="OTHER API")

    result = item_mode_change(request, item, Item.ADVERTISED, Item.BROUGHT)
    if left_count is not None:
        result["_item_limit_left"] = left_count

    if note:
        the_note = VendorNote.objects.create(
            vendor_id=item.vendor_id,
            clerk=clerk,
            text=note,
        )
        result["_note"] = the_note.as_dict()

    return result


@ajax_func('^item/checkout$', atomic=True)
def item_checkout(request, event, code, vendor=None):
    item = _get_item_or_404(code, for_update=True, event=event)
    if vendor == "":
        vendor = None
    if vendor is not None:
        vendor_id = int(vendor)
        if item.vendor_id != vendor_id:
            raise AjaxError(RET_LOCKED, _("Someone else's item!"))

    box = item.box
    if box:
        if box.representative_item.pk != item.pk:
            raise AjaxError(RET_CONFLICT,
                            "This is not returnable! Boxes have only one returnable item code which returns all!")
        items = box.get_items().select_for_update().filter(state=Item.BROUGHT)

        ItemStateLog.objects.log_states(item_set=items, new_state=Item.RETURNED, request=request)
        items.update(state=Item.RETURNED)

        box_info = Box.objects \
            .filter(pk=box.pk) \
            .annotate(
                item_count=Count("item", filter=Q(item__hidden=False)),
                returnable_count=Count(models.Case(models.When(item__state=Item.BROUGHT, then=1),
                                                   output_field=models.IntegerField())),
                returned_count=Count(models.Case(models.When(item__state=Item.RETURNED, then=1),
                                                 output_field=models.IntegerField()))
            ) \
            .values("item_count", "returnable_count", "returned_count")[0]

        ret = box.representative_item.as_dict()
        ret["box"] = {
            "id": box.id,
            "description": box.description,
            "box_number": box.box_number,
            "item_count": box_info["item_count"],
            "returnable_count": box_info["returnable_count"],
            "returned_count": box_info["returned_count"],
            "changed": items.count(),
        }
        return ret
    else:
        return item_mode_change(request, item, (Item.BROUGHT, Item.ADVERTISED), Item.RETURNED,
                                _(u"Item was not brought to event."))


@ajax_func('^item/compensate/start$')
def item_compensate_start(request, event, vendor):
    if "compensation" in request.session:
        raise AjaxError(RET_CONFLICT, _(u"Already compensating"))

    vendor_id = int(vendor)
    vendor_list = list(Vendor.objects.filter(pk=vendor_id, event=event))
    if not vendor_list:
        raise AjaxError(RET_BAD_REQUEST)

    clerk = get_clerk(request)
    counter = Counter.objects.get(pk=request.session["counter"])

    receipt = Receipt(
        clerk=clerk,
        counter=counter,
        type=Receipt.TYPE_COMPENSATION,
        vendor=vendor_list[0]
    )
    receipt.save()

    request.session["compensation"] = (receipt.pk, vendor_id)

    return receipt.as_dict()


@ajax_func('^item/compensate$', atomic=True)
def item_compensate(request, event, code):
    if "compensation" not in request.session:
        raise AjaxError(RET_CONFLICT, _(u"No compensation started!"))
    receipt_pk, vendor_id = request.session["compensation"]
    receipt = Receipt.objects.select_for_update().get(pk=receipt_pk, type=Receipt.TYPE_COMPENSATION)

    item = _get_item_or_404(code, vendor=vendor_id, for_update=True, event=event)
    item_dict = item_mode_change(request, item, Item.SOLD, Item.COMPENSATED)

    ReceiptItem.objects.create(item=item, receipt=receipt)
    receipt.calculate_total()
    receipt.save(update_fields=("total",))

    return item_dict


@ajax_func('^box/compensate$', atomic=True)
def box_item_compensate(request, event, pk, box_code):
    if "compensation" not in request.session:
        raise AjaxError(RET_CONFLICT, _(u"No compensation started!"))
    receipt_pk, vendor_id = request.session["compensation"]
    receipt = Receipt.objects.select_for_update().get(pk=receipt_pk, type=Receipt.TYPE_COMPENSATION)

    item = _get_item_or_404(None, pk=pk, vendor=vendor_id, for_update=True, event=event)
    # stupidly expensive check...
    if item.box.representative_item.code != box_code:
        raise AjaxError(RET_BAD_REQUEST, "Box item not found for {}".format(box_code))

    item_dict = item_mode_change(request, item, Item.SOLD, Item.COMPENSATED)
    item_dict["pk"] = item.pk

    ReceiptItem.objects.create(item=item, receipt=receipt)
    receipt.calculate_total()
    receipt.save(update_fields=("total",))

    return item_dict


@ajax_func('^item/compensate/end')
def item_compensate_end(request, event):
    if "compensation" in request.session:
        receipt_pk, vendor_id = request.session["compensation"]
    else:
        if not request.user.is_superuser or not ("receipt" in request.POST and "vendor" in request.POST):
            raise AjaxError(RET_CONFLICT, _(u"No compensation started!"))
        receipt_pk = int(request.POST["receipt"])
        vendor_id = int(request.POST["vendor"])

    state = "init"
    try:
        with transaction.atomic():
            receipt = Receipt.objects.select_for_update().get(
                pk=receipt_pk, type=Receipt.TYPE_COMPENSATION, status=Receipt.PENDING)

            provision = Provision(vendor_id=vendor_id, provision_function=event.provision_function, receipt=receipt)
            if provision.has_provision:
                state = "provision"
                ReceiptExtraRow.objects.create(
                    type=ReceiptExtraRow.TYPE_PROVISION,
                    value=provision.provision,
                    receipt=receipt,
                )

                if not provision.provision_fix.is_zero():
                    ReceiptExtraRow.objects.create(
                        type=ReceiptExtraRow.TYPE_PROVISION_FIX,
                        value=provision.provision_fix,
                        receipt=receipt,
                    )

            state = "receipt finish"
            receipt.status = Receipt.FINISHED
            receipt.end_time = now()
            receipt.calculate_total()

            account_id = receipt.counter.default_store_location_id
            total = receipt.total
            receipt.src_account_id = account_id

            state = "receipt save"
            receipt.save(update_fields=("status", "end_time", "total", "src_account"))

            state = "account"
            Account.objects.filter(pk=account_id).update(balance=F("balance") - total)

    except IntegrityError:
        if state == "account":
            account_balance = Account.objects.get(pk=account_id).balance
            raise AjaxError(RET_CONFLICT,
                            _("Not enough money in account ({0}) to give out ({1})").format(account_balance, total))
        else:
            raise

    if "compensation" in request.session:
        del request.session["compensation"]

    return receipt.as_dict()


@ajax_func('^vendor/get$', method='GET')
def vendor_get(request, event, id: typing.Optional[int] = None, code: typing.Optional[str] = None):
    id = empty_as_none(id)
    code = empty_as_none(code)

    if id is None and code is None:
        raise AjaxError(RET_BAD_REQUEST, "Either id or code must be given")
    if id and code:
        raise AjaxError(RET_BAD_REQUEST, "Only id or code must be given")

    if code:
        id = _get_item_or_404(code, event=event).vendor_id

    try:
        vendor = Vendor.objects.get(pk=int(id), event=event)
    except (ValueError, Vendor.DoesNotExist):
        raise AjaxError(RET_BAD_REQUEST, _(u"Invalid vendor id"))
    else:
        return vendor.as_dict()


@ajax_func('^vendor/find$', method='GET')
def vendor_find(request, event, q):
    clauses = [Q(event=event)]
    box_pat = re.compile("box[=:_-]?(\d+)")
    id_pat = re.compile("id[=:]?(\d+)")
    mail_pat = re.compile("e?mail[=:](.+)")
    for part in q.split():
        if part.isdigit():
            clause = Q(id=int(part))
            clause |= Q(item__box__box_number=part)
        elif match := box_pat.match(part):
            clause = Q(item__box__box_number=match.group(1))
            clauses.append(clause)
            continue
        elif match := id_pat.match(part):
            clause = Q(id=match.group(1))
            clauses.append(clause)
            continue
        elif match := mail_pat.match(part):
            clause = Q(user__email__icontains=match.group(1)) | Q(person__email__icontains=match.group(1))
            clauses.append(clause)
            continue
        else:
            clause = Q()

        clause = clause | (
            Q(user__username__icontains=part) |
            Q(user__first_name__icontains=part) |
            Q(user__last_name__icontains=part) |
            Q(user__email__icontains=part)
        )
        clause = clause | (Q(person__isnull=False) & (
            Q(person__first_name__icontains=part) |
            Q(person__last_name__icontains=part) |
            Q(person__email__icontains=part)
        ))

        clauses.append(clause)

    return [
        v.as_dict()
        for v in (
            Vendor.objects
            .filter(*clauses)
            .distinct()
            .select_related("user", "person")
            .all()
        )
    ]


@ajax_func('^vendor/token/create$', method='POST', atomic=True)
def vendor_token_create(request, vendor_id, expiry: int = None):
    clerk = get_clerk(request)
    vendor = Vendor.objects.get(id=int(vendor_id))

    old_permits = TemporaryAccessPermit.objects.select_for_update().filter(vendor=vendor)
    for permit in old_permits:
        TemporaryAccessPermitLog.objects.create(
            permit=permit,
            action=TemporaryAccessPermitLog.ACTION_INVALIDATE,
            address=get_client_ip(request),
            peer="{0}/{1}".format(clerk.user.username, clerk.pk),
        )
    old_permits.update(state=TemporaryAccessPermit.STATE_INVALIDATED)

    if expiry:
        expiry = int(expiry)
        if expiry < 10000:
            numbers = round(math.log10(1700 * expiry))
        else:
            raise AjaxError(RET_BAD_REQUEST, "Reduce the expiry time")
        numbers = max(numbers, settings.KIRPPU_SHORT_CODE_LENGTH)
    else:
        numbers = settings.KIRPPU_SHORT_CODE_LENGTH
        expiry = None

    permit, code = None, None
    for retry in range(60):
        try:
            code = random.randint(10 ** (numbers - 1), 10 ** numbers - 1)
            permit = TemporaryAccessPermit.objects.create(
                vendor=vendor,
                creator=clerk,
                expiration_time=default_temporary_access_permit_expiry(expiry),
                short_code=str(code),
            )
            TemporaryAccessPermitLog.objects.create(
                permit=permit,
                action=TemporaryAccessPermitLog.ACTION_ADD,
                address=get_client_ip(request),
                peer="{0}/{1}".format(clerk.user.username, clerk.pk),
            )
            break
        except IntegrityError as e:
            continue
    if permit and code:
        return {
            "code": code,
        }
    else:
        raise AjaxError(RET_CONFLICT, _("Gave up code generation."))


@ajax_func('^receipt/start$', atomic=True)
def receipt_start(request):
    if "receipt" in request.session:
        raise AjaxError(RET_CONFLICT, "There is already an active receipt on this counter!")

    clerk = get_clerk(request)
    if Receipt.objects.filter(clerk=clerk, status=Receipt.PENDING, type=Receipt.TYPE_PURCHASE).count() > 0:
        raise AjaxError(RET_CONFLICT, "There is already an active receipt!")

    receipt = Receipt()
    receipt.clerk = clerk
    receipt.counter = get_counter(request)
    receipt.type = Receipt.TYPE_PURCHASE

    receipt.save()

    request.session["receipt"] = receipt.pk
    return receipt.as_dict()


@ajax_func('^item/reserve$', atomic=True)
def item_reserve(request, event, code):
    item = _get_item_or_404(code, for_update=True, event=event)
    if item.box_id is not None:
        raise AjaxError(RET_CONFLICT, "A box cannot be reserved")
    receipt_id = request.session.get("receipt")
    if receipt_id is None:
        raise AjaxError(RET_BAD_REQUEST, "No active receipt found")
    receipt = get_receipt(receipt_id, for_update=True)

    if receipt.status != Receipt.PENDING:
        raise AjaxError(RET_CONFLICT, "Internal error: Receipt is not open anymore.")

    message = raise_if_item_not_available(item)
    if item.state in (Item.ADVERTISED, Item.BROUGHT, Item.MISSING):
        ItemStateLog.objects.log_state(item, Item.STAGED, request=request)
        item.state = Item.STAGED
        item.save(update_fields=("state",))

        ReceiptItem.objects.create(item=item, receipt=receipt)
        # receipt.items.create(item=item)
        receipt.calculate_total()
        receipt.save(update_fields=("total",))

        ret = item.as_dict()
        ret.update(total=receipt.total_cents)
        if message is not None:
            ret.update(_message=message)
        return ret
    else:
        # Not in expected state.
        raise AjaxError(RET_CONFLICT)


@ajax_func('^item/release$', atomic=True)
def item_release(request, code):
    item = _get_item_or_404(code, for_update=True)
    receipt_id = request.session.get("receipt")
    if receipt_id is None:
        raise AjaxError(RET_BAD_REQUEST, "No active receipt found")
    try:
        removal_entry = remove_item_from_receipt(request, item, receipt_id)
    except ValueError as e:
        raise AjaxError(RET_CONFLICT, e.args[0])

    return removal_entry.as_dict()


def _get_active_receipt(request, id, allowed_states=(Receipt.PENDING,)):
    arg_id = int(id)
    in_session = "receipt" in request.session
    if in_session:
        receipt_id = request.session["receipt"]
        if receipt_id != arg_id:
            msg = "Receipt id conflict: {} != {}".format(receipt_id, arg_id)
            logger.error(msg)
            raise AjaxError(RET_CONFLICT, msg)
    else:
        receipt_id = arg_id
        logger.warning("Active receipt is being read without it being in session: %i", receipt_id)

    receipt = get_receipt(receipt_id, for_update=True)
    if receipt.status not in allowed_states:
        if not in_session and receipt.status == Receipt.FINISHED:
            raise AjaxError(RET_CONFLICT, "Receipt {} was already ended at {}".format(receipt_id, receipt.end_time))
        raise AjaxError(RET_CONFLICT, "Receipt {} is in unexpected state: {}".format(
            receipt_id, receipt.get_status_display()))
    return receipt, receipt_id


@ajax_func('^receipt/finish$', atomic=True)
def receipt_finish(request, id):
    receipt, receipt_id = _get_active_receipt(request, id)

    account_id = receipt.counter.default_store_location_id
    receipt.end_time = now()
    receipt.status = Receipt.FINISHED
    receipt.dst_account_id = account_id
    receipt.save(update_fields=("end_time", "status", "dst_account"))

    Account.objects.filter(pk=account_id).update(balance=F("balance") + receipt.total)

    receipt_items = Item.objects.select_for_update().filter(receipt=receipt, receiptitem__action=ReceiptItem.ADD)
    ItemStateLog.objects.log_states(item_set=receipt_items, new_state=Item.SOLD, request=request)
    receipt_items.update(state=Item.SOLD)

    del request.session["receipt"]
    return receipt.as_dict()


@ajax_func('^receipt/abort$', atomic=True)
def receipt_abort(request, id):
    receipt, receipt_id = _get_active_receipt(request, id, (Receipt.PENDING, Receipt.SUSPENDED))

    # For all ADDed items, add REMOVE-entries and return the real Item's back to available.
    added_items = ReceiptItem.objects.select_for_update().filter(receipt_id=receipt_id, action=ReceiptItem.ADD)
    for receipt_item in added_items.only("item"):
        item = receipt_item.item

        ReceiptItem(item=item, receipt=receipt, action=ReceiptItem.REMOVE).save()

        if item.state != Item.BROUGHT:
            ItemStateLog.objects.log_state(item=item, new_state=Item.BROUGHT, request=request)
            item.state = Item.BROUGHT
            item.save()

    # Update ADDed items to be REMOVED_LATER. This must be done after the real Items have
    # been updated, and the REMOVE-entries added, as this will change the result set of
    # the original added_items -query (to always return zero entries).
    added_items.update(action=ReceiptItem.REMOVED_LATER)

    # End the receipt. (Must be done after previous updates, so calculate_total calculates
    # correct sum.)
    receipt.end_time = now()
    receipt.status = Receipt.ABORTED
    receipt.calculate_total()
    receipt.save(update_fields=("end_time", "status", "total"))

    del request.session["receipt"]
    return receipt.as_dict()


def _get_receipt_data_with_items(**kwargs):
    kwargs.setdefault("type", Receipt.TYPE_PURCHASE)
    receipt = get_object_or_404(Receipt, **kwargs)

    data = receipt.as_dict()
    data["items"] = receipt.row_list()
    return data


@ajax_func('^receipt$', method='GET')
def receipt_get(request):
    """
    Find receipt by receipt id or one item in the receipt.
    """
    if "id" in request.GET:
        receipt_id = int(request.GET.get("id"))
        query = {"pk": receipt_id}
        if request.GET.get("type") == "compensation":
            query["type"] = Receipt.TYPE_COMPENSATION
    elif "item" in request.GET:
        item_code = request.GET.get("item")
        query = {
            "receiptitem__item__code": item_code,
            "receiptitem__action": ReceiptItem.ADD,
            "status": Receipt.FINISHED,
        }
    else:
        raise AjaxError(RET_BAD_REQUEST)
    return _get_receipt_data_with_items(**query)


@ajax_func('^receipt/activate$')
def receipt_activate(request):
    """
    Activate previously started pending receipt.
    """
    clerk = request.session["clerk"]
    receipt_id = int(request.POST.get("id"))
    data = _get_receipt_data_with_items(pk=receipt_id, clerk__id=clerk, status=Receipt.PENDING,
                                        type=Receipt.TYPE_PURCHASE)
    request.session["receipt"] = receipt_id
    return data


@ajax_func('^receipt/pending', overseer=True, method='GET')
def receipt_pending(request, event: Event):
    receipts = Receipt.objects.filter(
        clerk__event=event,
        status__in=(Receipt.PENDING, Receipt.SUSPENDED),
        type=Receipt.TYPE_PURCHASE,
    )
    return [receipt.as_dict() for receipt in receipts]


@ajax_func('^receipt/compensated', method='GET')
def receipt_compensated(request, vendor):
    receipts = Receipt.objects.filter(
        type=Receipt.TYPE_COMPENSATION,
        vendor_id=int(vendor)
    ).distinct().order_by("start_time")

    return [receipt.as_dict() for receipt in receipts]


@ajax_func('^barcode$', counter=False, clerk=False, staff_override=True)
def get_barcodes(request, codes=None):
    """
    Get barcode images for a code, or list of codes.

    :param codes: Either list of codes, or a string, encoded in Json string.
    :type codes: str
    :return: List of barcode images encoded in data-url.
    :rtype: list[str]
    """
    from .templatetags.kirppu_tags import barcode_dataurl
    from json import loads

    codes = loads(codes)
    if isinstance(codes, str):
        codes = [codes]

    # XXX: This does ignore the width assertion. Beware with style sheets...
    outs = [
        barcode_dataurl(code, "png", None)
        for code in codes
    ]
    return outs


@ajax_func('^item/abandon$')
def items_abandon(request, vendor):
    """
    Set all of the vendor's 'brought to event' and 'missing' items to abandoned
    The view is expected to refresh itself
    """
    Item.objects.filter(
        vendor__id=vendor,
        state__in=(Item.BROUGHT, Item.MISSING),
    ).update(abandoned=True)
    return


@ajax_func('^item/mark_lost$', overseer=True, atomic=True)
def item_mark_lost(request, event, code):
    item = _get_item_or_404(code=code, for_update=True, event=event)
    if item.state == Item.SOLD:
        raise AjaxError(RET_CONFLICT, u"Item is sold!")
    if item.state == Item.STAGED:
        raise AjaxError(RET_CONFLICT, u"Item is staged to be sold!")
    if item.abandoned:
        raise AjaxError(RET_CONFLICT, u"Item is abandoned.")

    item.lost_property = True
    item.save(update_fields=("lost_property",))
    return item.as_dict()


@ajax_func('^stats/sales_data$', method='GET', staff_override=True)
def stats_sales_data(request, event: Event, prices="false"):
    source_event = event.get_real_event()
    formatter = stats.SalesData(event=source_event, as_prices=prices == "true")
    log_generator = stats.iterate_logs(formatter)
    return StreamingHttpResponse(log_generator, content_type='text/csv')


@ajax_func('^stats/registration_data$', method='GET', staff_override=True)
def stats_registration_data(request, event: Event, prices="false"):
    source_event = event.get_real_event()
    formatter = stats.RegistrationData(event=source_event, as_prices=prices == "true")
    log_generator = stats.iterate_logs(formatter)
    return StreamingHttpResponse(log_generator, content_type='text/csv')


@ajax_func('^stats/group_sales$', method='GET', staff_override=True)
def stats_group_sales_data(request, event: Event, type_id, prices="false"):
    source_event = event.get_real_event()
    database = event.get_real_database_alias()
    item_type = ItemType.objects.using(database).get(event=source_event, id=int(type_id))
    formatter = stats.SalesData(event=source_event, as_prices=prices == "true",
                                extra_filter=dict(item__itemtype=item_type))
    log_generator = stats.iterate_logs(formatter)
    return StreamingHttpResponse(log_generator, content_type='text/csv')
