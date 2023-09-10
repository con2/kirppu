# -*- coding: utf-8 -*-
from django.utils.translation import gettext as _

from .common import (
    get_item_or_404 as _get_item_or_404,
    get_box_or_404 as _get_box_or_404,
    item_state_conflict as _item_state_conflict,
    get_receipt,
)
from ..ajax_util import ajax_func_factory, AjaxError, RET_BAD_REQUEST, RET_CONFLICT
from ..forms import remove_item_from_receipt
from ..models import Item, ItemStateLog, ReceiptItem, decimal_to_transport

__author__ = 'codez'


ajax_func = ajax_func_factory("checkout")


def _parse_item_count(inp, minimum=1):
    """
    Parse input string as integer.

    :type inp: int|str
    :type minimum: int
    :raises AjaxError: If value is not a valid integer or the value is less than minimum allowed.
    :rtype: int
    """
    try:
        value = int(inp)
        if value < minimum:
            raise AjaxError(RET_BAD_REQUEST, "Value {} less than minimum {}".format(value, minimum))
        return value
    except ValueError as e:
        raise AjaxError(RET_BAD_REQUEST, "Value is not a valid number.")


@ajax_func('^box/find$', method='GET')
def box_find(request, event, box_number, box_item_count="1"):
    box_item_count = _parse_item_count(box_item_count)

    box = _get_box_or_404(box_number, event=event)
    available_count = box.item_set.filter(state=Item.BROUGHT).count()
    if available_count < box_item_count:
        raise AjaxError(RET_CONFLICT, _("Not enough available box items, only {} exist").format(available_count))

    ret = box.as_dict()
    ret.update(available=available_count)
    return ret


@ajax_func('^box/checkin$', atomic=True)
def box_checkin(request, event, code, box_info):
    item = _get_item_or_404(code, event=event)
    if not item.vendor.terms_accepted:
        raise AjaxError(500, _(u"Vendor has not accepted terms!"))

    if item.state != Item.ADVERTISED:
        _item_state_conflict(item)

    box = item.box

    box_number = int(box_info)
    if box_number != box.box_number:
        raise AjaxError(500, _("Unexpected box number conflict"))

    left_count = None
    if event.max_brought_items is not None:
        count = 1 if event.box_as_single_brought_item else box.get_item_count()
        brought_count = Item.get_brought_count(event, item.vendor)
        if brought_count + count > event.max_brought_items:
            raise AjaxError(RET_CONFLICT, _("Too many items brought, limit is %i!") % event.max_brought_items)
        else:
            left_count = event.max_brought_items - brought_count - count

    items = box.get_items().select_for_update()
    wrong_count = items.exclude(state=Item.ADVERTISED).count()
    if wrong_count > 0:
        raise AjaxError(RET_CONFLICT,
                        _("Some box items ({}/{}) are in unexpected state.").format(wrong_count, items.count()))

    ItemStateLog.objects.log_states(item_set=items, new_state=Item.BROUGHT, request=request)
    items.update(state=Item.BROUGHT)

    result = {
        "box": box.as_dict(),
        "changed": items.count(),
        "code": item.code,
    }
    if left_count is not None:
        result["_item_limit_left"] = left_count
    return result


@ajax_func("^box/item/reserve$", atomic=True)
def box_item_reserve(request, event, box_number, box_item_count="1"):
    box_item_count = _parse_item_count(box_item_count)
    box = _get_box_or_404(box_number, event=event)

    receipt_id = request.session.get("receipt")
    if receipt_id is None:
        raise AjaxError(RET_BAD_REQUEST, "No active receipt found")
    receipt = get_receipt(receipt_id, for_update=True)

    # Must force id-list to ensure stability.
    # Otherwise the "list" is considered as a subquery which may not be stable.
    candidates = list(box.item_set.select_for_update()
                      .filter(state=Item.BROUGHT)[:box_item_count + 1].values_list("pk", flat=True))

    # Avoid representative item, as it is needed for representing all available items.
    # Reserve it only when it is last item to be reserved.
    representative_item_id = box.representative_item_id
    if len(candidates) == box_item_count + 1:
        if representative_item_id in candidates:
            candidates = [c for c in candidates if c != representative_item_id]
        else:
            candidates = candidates[:-1]

    if len(candidates) == box_item_count:
        items = Item.objects.filter(pk__in=candidates)
        rows = [
            ReceiptItem(
                item=item,
                receipt=receipt,
            )
            for item in items
        ]

        ItemStateLog.objects.log_states(items, Item.STAGED, request=request)
        items.update(state=Item.STAGED)

        ReceiptItem.objects.bulk_create(rows)
        receipt.calculate_total()
        receipt.save(update_fields=("total",))

        result_items = [
            {
                "code": entry["code"],
                "price": decimal_to_transport(entry["price"]),
            }
            for entry in items.values("code", "price")
        ]
        ret = box.as_dict()
        del ret["item_price"]  # item_price assumes representative item has same price as ones being reserved.
        ret.update(
            total=receipt.total_cents,
            changed=box_item_count,
            items=result_items,
            item_name=box.representative_item.name,
        )
        return ret
    else:
        raise AjaxError(
            RET_CONFLICT,
            _("Only {available} items of {requested} available for reservation in box #{box_number}: {box_name}.")
            .format(
                available=len(candidates),
                requested=box_item_count,
                box_number=box.box_number,
                box_name=box.description,
            )
        )


@ajax_func('^box/item/release$', atomic=True)
def box_item_release(request, event, box_number, box_item_count="1"):
    box_item_count = _parse_item_count(box_item_count)
    box = _get_box_or_404(box_number, event=event)

    receipt_id = request.session.get("receipt")
    if receipt_id is None:
        raise AjaxError(RET_BAD_REQUEST, "No active receipt found")
    receipt = get_receipt(receipt_id, for_update=True)

    # This query may return duplicates due extra inner join for action filtering.
    # Distinct cannot be used, since this is select_for_update query.
    receipt_items = receipt.items.select_for_update().filter(receiptitem__action=ReceiptItem.ADD, box=box)
    # Make distinct by hand.
    box_items = list({i.pk: i for i in receipt_items}.values())

    if len(box_items) < box_item_count:
        raise AjaxError(RET_CONFLICT,
                        _("Only {} items of {} available for removal.").format(len(box_items), box_item_count))

    representative_item_id = box.representative_item_id
    items = list()

    # Firstly remove representative item, if possible.
    box_items = sorted(box_items, key=lambda i: 0 if i.pk == representative_item_id else 1)

    # Remove items until enough are removed.
    for box_item in box_items:
        if len(items) == box_item_count:
            break
        removal_entry = remove_item_from_receipt(request, box_item, receipt, update_receipt=False)
        items.append({
            "code": removal_entry.item.code,
            "price": decimal_to_transport(removal_entry.item.price),
        })

    receipt.calculate_total()
    receipt.save(update_fields=("total",))

    ret = box.as_dict()
    del ret["item_price"]  # item_price assumes representative item has same price as ones being reserved.
    ret.update(
        total=receipt.total_cents,
        changed=box_item_count,
        items=items,
        item_name=box.representative_item.name
    )
    return ret
