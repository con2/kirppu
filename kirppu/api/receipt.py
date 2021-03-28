# -*- coding: utf-8 -*-
from django.shortcuts import get_object_or_404

from ..ajax_util import ajax_func_factory, AjaxError, RET_CONFLICT, get_clerk
from ..models import Receipt, Item, ReceiptItem, Clerk, ReceiptNote

__author__ = 'codez'

ajax_func = ajax_func_factory("checkout")


@ajax_func('^receipt/suspend', atomic=True)
def receipt_suspend(request, note):
    receipt_id = request.session["receipt"]
    receipt = get_object_or_404(Receipt, pk=receipt_id)

    if receipt.status != Receipt.PENDING or receipt.type != Receipt.TYPE_PURCHASE:
        raise AjaxError(RET_CONFLICT)

    if note:
        clerk = get_clerk(request)
        note = ReceiptNote(receipt=receipt, clerk=clerk, text=note)
        note.save()

    receipt.status = Receipt.SUSPENDED
    receipt.save()

    del request.session["receipt"]
    return receipt.as_dict()


@ajax_func('^receipt/continue')
def receipt_continue(request, code):
    clerk = request.session["clerk"]
    item = Item.get_item_by_barcode(code)
    receipt = get_object_or_404(Receipt, status=Receipt.SUSPENDED,
                                type=Receipt.TYPE_PURCHASE,
                                receiptitem__item=item, receiptitem__action=ReceiptItem.ADD)

    receipt.status = Receipt.PENDING
    if receipt.clerk_id != clerk:
        receipt.clerk = Clerk.objects.get(id=clerk)
    receipt.save()

    request.session["receipt"] = receipt.id
    data = receipt.as_dict()
    data["items"] = receipt.items_list()
    return data
