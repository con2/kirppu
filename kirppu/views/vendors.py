# -*- coding: utf-8 -*-
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import HttpResponseRedirect, JsonResponse, HttpResponseBadRequest, Http404
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods

from ..forms import PersonCreationForm
from ..models import Event, EventPermission, Vendor
from ..util import get_form

__author__ = 'codez'

__all__ = [
    "get_multi_vendor_values",
    "change_vendor",
    "create_vendor",
]


def get_multi_vendor_values(request, event):
    """
    Get values for multi-vendor template operations.

    :param request: Request to read values from.
    :type event: Event
    :return: Dict for template.
    :rtype: dict
    """
    user = request.user
    can_create_vendor = False
    can_switch_vendor = False

    database = event.get_real_database_alias()
    source_event = event.get_real_event()

    if event.multiple_vendors_per_user and user.is_authenticated:
        if user.is_staff and "user" in request.GET:
            raise NotImplementedError  # FIXME: Decide how this should work.
        user_query = event.get_user_query(user)
        permissions = EventPermission.get(event, user)
        multi_vendor = Vendor.objects.using(database).filter(person__isnull=False, event=source_event, **user_query)
        self_vendor = Vendor.objects.using(database).filter(person__isnull=True, event=source_event, **user_query)\
            .first()
        can_create_vendor = permissions.can_create_sub_vendor
        can_switch_vendor = can_create_vendor or permissions.can_switch_sub_vendor
    else:
        multi_vendor = []
        self_vendor = None

    if user.is_authenticated:
        vendor = Vendor.get_vendor(request, source_event)
    else:
        vendor = None

    return {
        'self_vendor': self_vendor,
        'self_name': self_vendor.printable_name if self_vendor is not None else str(user),
        'multi_vendor': multi_vendor,
        'current_vendor': vendor,
        'can_create_vendor': can_create_vendor,
        'can_switch_vendor': can_switch_vendor,
    }


@login_required
@require_http_methods(["POST"])
def change_vendor(request, event_slug):
    event = get_object_or_404(Event, slug=event_slug)
    if not event.multiple_vendors_per_user:
        raise Http404()

    user = request.user
    permissions = EventPermission.get(event, user)
    if not (permissions.can_create_sub_vendor or permissions.can_switch_sub_vendor):
        raise PermissionDenied

    vendor_id_str = request.POST["vendor"]
    if vendor_id_str:
        new_vendor_id = int(vendor_id_str)
        new_vendor = get_object_or_404(Vendor, event=event, id=new_vendor_id, user=user)
    else:
        # User is not a vendor even though they have persons.
        new_vendor = Vendor.objects.filter(event=event, user=user, person__isnull=True).first()
    if new_vendor is not None and new_vendor.person:
        request.session["vendor_id"] = new_vendor.id
    elif "vendor_id" in request.session:
        del request.session["vendor_id"]

    ref = request.META.get("HTTP_REFERER")
    if not (ref and url_has_allowed_host_and_scheme(ref, allowed_hosts={request.get_host()})):
        ref = reverse("kirppu:page", kwargs={"event_slug": event_slug})

    return HttpResponseRedirect(ref)


@login_required
@require_http_methods(["POST"])
def create_vendor(request, event_slug):
    event = get_object_or_404(Event, slug=event_slug)
    if not event.multiple_vendors_per_user:
        raise Http404()

    if not EventPermission.get(event, request.user).can_create_sub_vendor:
        raise PermissionDenied

    form = get_form(PersonCreationForm, request)
    if form.is_valid():
        with transaction.atomic():
            instance = form.save()
            new_vendor = Vendor(
                event=event,
                user=request.user,
                person=instance,
            )
            new_vendor.save(force_insert=True)
        return JsonResponse({
            "result": "ok",
            "id": new_vendor.id,
        })

    return HttpResponseBadRequest(
        form.errors.as_json(),
        content_type="application/json",
    )
