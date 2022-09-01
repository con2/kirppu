# -*- coding: utf-8 -*-
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404

from ..ajax_util import ajax_func_factory, get_clerk
from ..models import Vendor, VendorNote

ajax_func = ajax_func_factory("checkout")


@ajax_func("vendor/notes/$")
def vendor_note_add(request, event, vendor_id: int, note: str):
    clerk = get_clerk(request)
    vendor = get_object_or_404(Vendor, id=int(vendor_id), event=event)

    VendorNote.objects.create(
        vendor=vendor,
        clerk=clerk,
        text=note,
    )

    return [n.as_dict() for n in VendorNote.objects.filter(vendor=vendor)]


@ajax_func("vendor/notes$", method="GET")
def vendor_notes(request, event, vendor_id: int):
    vendor = get_object_or_404(Vendor, id=int(vendor_id), event=event)
    notes = VendorNote.objects.filter(vendor=vendor)
    return [note.as_dict() for note in notes]


@ajax_func("vendor/notes/complete$")
def vendor_note_complete(request, event, vendor_id: int, note_id: int):
    vendor = get_object_or_404(Vendor, id=int(vendor_id), event=event)
    with transaction.atomic():
        VendorNote.objects.filter(id=int(note_id), vendor=vendor).update(erased=Q(erased=False))

    return "ok"
