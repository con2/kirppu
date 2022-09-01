# -*- coding: utf-8 -*-
from decimal import Decimal

from django.db import transaction, IntegrityError
from django.db.models import F
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext as _
from django.utils import timezone

from ..ajax_util import (
    ajax_func_factory,
    AjaxError,
    RET_CONFLICT,
    RET_BAD_REQUEST,
    RET_FORBIDDEN,
    get_clerk,
    get_counter,
    require_user_features,
)
from ..models import Account, Clerk, EventPermission, Item, Receipt, ReceiptItem, ReceiptNote

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
    clerk = get_clerk(request)
    counter = get_counter(request)
    item = Item.get_item(code=code)
    receipt = get_object_or_404(Receipt, status=Receipt.SUSPENDED,
                                type=Receipt.TYPE_PURCHASE,
                                receiptitem__item=item, receiptitem__action=ReceiptItem.ADD)

    update_fields = ["status"]
    receipt.status = Receipt.PENDING

    if receipt.clerk_id != clerk.id:
        receipt.clerk = clerk
        update_fields.append("clerk")

    if receipt.counter_id != counter.id:
        receipt.counter = counter
        update_fields.append("counter")
    receipt.save(update_fields=update_fields)

    request.session["receipt"] = receipt.id
    data = receipt.as_dict()
    data["items"] = receipt.items_list()
    return data


def _check_access(request, event):
    try:
        # Access from overseer.
        require_user_features(overseer=True)(lambda r: None)(request)
    except AjaxError as e:
        # Access from public side.
        if not EventPermission.get(event, request.user).can_see_accounting:
            raise AjaxError(RET_FORBIDDEN)
    return event


@ajax_func('^accounts/$', method="GET", counter=False, clerk=False)
def list_accounts(request, event):
    _check_access(request, event)
    accounts = Account.objects.filter(event=event)
    return [a.as_dict() for a in accounts]


def _with_note(receipt, receipt_note=None):
    r = receipt.as_transfer_dict()
    # XXX: Unusual attribute. Assuming there is exactly one note.
    r["note"] = receipt_note.as_dict() if receipt_note is not None else receipt.receiptnote_set.first().as_dict()
    return r


@ajax_func("accounts/transfers$", method="GET", counter=False, clerk=False)
def list_transfers(request, event):
    _check_access(request, event)
    transfers = (
        Receipt.objects
        .filter(type=Receipt.TYPE_TRANSFER, counter__event=event)
        .order_by("start_time")
    )
    return [_with_note(t) for t in transfers]


@ajax_func('^accounts/transfer$', method="POST", overseer=True)
def transfer_money(request, event, src_id, dst_id, amount, note, auth, commit=False):
    # Session clerk is mostly just stored into the note.
    session_clerk = get_clerk(request)
    clerk = Clerk.by_code(auth, event=event)

    amount_d = Decimal(amount)
    if amount_d <= Decimal(0):
        raise AjaxError(RET_BAD_REQUEST, "Amount must be positive")

    perms = EventPermission.get(event, clerk.user)
    if not perms.can_perform_overseer_actions:
        raise AjaxError(RET_FORBIDDEN, _("You don't have permission to do this"))

    try:
        src = Account.objects.get(pk=src_id, event=event)
    except Account.DoesNotExist:
        raise AjaxError(RET_BAD_REQUEST, "Source account doesn't exist")

    try:
        dst = Account.objects.get(pk=dst_id, event=event)
    except Account.DoesNotExist:
        raise AjaxError(RET_BAD_REQUEST, "Destination account doesn't exist")

    if src.pk == dst.pk:
        raise AjaxError(RET_BAD_REQUEST, _("Source and destination cannot be the same"))

    if src.allow_negative_balance and not perms.can_manage_event:
        raise AjaxError(RET_FORBIDDEN, _("Not allowing more loan without manage permission"))

    receipt = Receipt()
    receipt.clerk = clerk
    receipt.counter = get_counter(request)
    receipt.type = Receipt.TYPE_TRANSFER
    receipt.total = amount_d

    receipt.src_account = src
    receipt.dst_account = dst

    receipt_note = ReceiptNote(receipt=receipt, clerk=session_clerk, text=note)

    if commit not in ("true", "1"):
        # XXX: Doesn't check balance, so 200 even if the result would be negative.
        return _with_note(receipt, receipt_note)

    receipt.save()

    try:
        with transaction.atomic():
            try:
                Account.objects.filter(pk=src.pk).update(balance=F("balance") - amount_d)
            except IntegrityError:
                raise AjaxError(RET_CONFLICT, "Out of balance")
            Account.objects.filter(pk=dst.pk).update(balance=F("balance") + amount_d)

    except AjaxError as e:
        receipt.status = Receipt.ABORTED
        receipt.end_time = timezone.now()
        receipt.save(update_fields=("status", "end_time"))
        raise e

    receipt_note.save()

    receipt.status = Receipt.FINISHED
    receipt.end_time = timezone.now()
    receipt.save(update_fields=("status", "end_time"))

    return receipt.as_transfer_dict()
