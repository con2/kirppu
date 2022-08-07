# -*- coding: utf-8 -*-
from django.http import Http404
from django.utils.translation import gettext as _

from ..ajax_util import AjaxError, RET_BAD_REQUEST, RET_CONFLICT
from ..models import Box, Item, Receipt


def get_item_or_404(code, for_update=False, event=None, **kwargs):
    """
    :param code: Item barcode to find. If not given, pk should be in arguments.
    :param for_update: If True, Item is retrieved for update.
    :param event: Optional Event object to match the Item by.
    :param kwargs: Extra query filters.
    :rtype: Item
    :raises Http404: If an Item matching the query does not exist.
    """
    if code is not None:
        kwargs["code"] = code
    try:
        if for_update:
            item = Item.get_item_for_update(**kwargs)
        else:
            item = Item.get_item(**kwargs)
    except Item.DoesNotExist:
        item = None

    if item is None:
        if code is None:
            f = kwargs.get("pk")
        else:
            f = "'%s'" % code
        raise Http404(_("No item found matching {0}").format(f))

    # vendor_event is assumed to be annotated by Item.get_item*
    if event is not None and item.vendor_event != event.id:
        raise AjaxError(RET_CONFLICT, "Item is not registered in this event!")

    return item


def get_box_or_404(box_number, event, for_update=False, **kwargs):
    """
    :param box_number: Number of the box to find.
    :type box_number: int|str
    :param event: Event object to match the Box by.
    :param for_update: If True, Box is retrieved for update.
    :param kwargs: Extra query filters.
    :rtype: Box
    :raises Http404: If a Box matching the query does not exist.
    :raises AjaxError: If `box_number` is not a valid number.
    """
    number = None
    try:
        number = int(box_number)
        query = Box.objects.filter(representative_item__vendor__event=event)
        if for_update:
            query = query.select_for_update()
        box = query.get(box_number=box_number, **kwargs)
        return box
    except ValueError as e:
        raise AjaxError(RET_BAD_REQUEST, "box_number must be a number")
    except Box.DoesNotExist as e:
        raise Http404(_("Box #{} does not exist.").format(number))


def item_state_conflict(item):
    raise AjaxError(
        RET_CONFLICT,
        _(u"Unexpected item state: {state_name} ({state})").format(
            state=item.state,
            state_name=item.get_state_display()
        ),
    )


def get_receipt(receipt_id, for_update=False):
    try:
        query = Receipt.objects
        if for_update:
            query = query.select_for_update()
        return query.get(pk=receipt_id, type=Receipt.TYPE_PURCHASE)
    except Receipt.DoesNotExist:
        raise AjaxError(500, "Receipt {} does not exist.".format(receipt_id))
