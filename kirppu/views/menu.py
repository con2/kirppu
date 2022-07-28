# -*- coding: utf-8 -*-
import functools
import typing
from urllib.parse import quote

from django.urls import reverse, NoReverseMatch
from django.utils.translation import gettext as _

from ..models import Event, EventPermission, UserAdapter


class MenuItem(typing.NamedTuple):
    name: typing.Optional[str]
    url: typing.Optional[str]
    active: typing.Optional[bool]
    sub_items: typing.Optional[typing.List["MenuItem"]]


def _fill(event: Event, active: str, name, func, sub=None, query=None, is_global=False):
    if not is_global:
        kwargs = {"event_slug": event.slug}
    else:
        kwargs = {}
    link = reverse(func, kwargs=kwargs) if func else None
    if query:
        link += "?" + "&".join(
            quote(k, safe="") + (("=" + quote(v, safe="")) if v else "")
            for k, v in query.items())
    return MenuItem(name, link, func == active, sub)


def management_menu(
        request,
        event: Event,
        permissions: typing.Optional[EventPermission] = None
) -> typing.List[MenuItem]:
    fill = functools.partial(_fill, event, request.resolver_match.view_name)

    manage_sub: typing.List[MenuItem] = []
    permissions = permissions or EventPermission.get(event, request.user)

    if not event.source_db and (request.user.is_staff or UserAdapter.is_clerk(request.user, event)):
        manage_sub.append(fill(_(u"Checkout commands"), "kirppu:commands"))
        if event.checkout_active:
            manage_sub.append(fill(_(u"Checkout"), "kirppu:checkout_view"))
            if event.use_boxes:
                manage_sub.append(fill(_("Box codes"), "kirppu:box_codes"))

    if not event.source_db and (request.user.is_staff or permissions.can_see_clerk_codes):
        manage_sub.append(fill(_(u"Clerk codes"), "kirppu:clerks"))

    if not event.source_db and (request.user.is_staff or permissions.can_see_accounting):
        manage_sub.append(fill(_(u"Lost and Found"), "kirppu:lost_and_found"))

    if request.user.is_staff \
            or UserAdapter.is_clerk(request.user, event) \
            or permissions.can_see_statistics:
        manage_sub.append(fill(_(u"Statistics"), "kirppu:stats_view"))

    if permissions.can_manage_event or request.user.is_superuser:
        manage_sub.append(fill(_(u"Manage event"), "kirppu:manage_event"))

    if request.user.is_staff:
        try:
            manage_sub.append(fill(_(u"Site administration"), "admin:index", is_global=True))
        except NoReverseMatch as e:
            pass

    return manage_sub


def vendor_menu(request, event: Event) -> typing.List[MenuItem]:
    """
    Generate menu for Vendor views.
    Returned tuple contains entries for the menu, each entry containing a
    name, url, and flag indicating whether the entry is currently active
    or not.

    :param event: The event.
    :param request: Current request being processed.
    :return: List of menu items containing name, url and active fields.
    """
    fill = functools.partial(_fill, event, request.resolver_match.view_name)

    items = [
        fill(_(u"Home"), "kirppu:vendor_view"),
    ]

    if not event.source_db:
        items.append(fill(_(u"Item list"), "kirppu:page"))
        if event.use_boxes:
            items.append(fill(_(u"Box list"), "kirppu:vendor_boxes"))

    if event.mobile_view_visible:
        items.append(fill(_("Mobile"), "kirppu:mobile"))

    permissions = EventPermission.get(event, request.user)
    manage_sub = management_menu(request, event, permissions=permissions)
    if manage_sub:
        items.append(fill(_(u"Management"), "", manage_sub))

    if permissions.can_see_accounting:
        accounting_sub = [
            fill(_("View"), "kirppu:accounting"),
            fill(_("Download"), "kirppu:accounting", query={"download": ""}),
            MenuItem(None, None, None, None),
            fill(_("View items"), "kirppu:item_dump", query={"txt": ""}),
            fill(_("View items (CSV)"), "kirppu:item_dump"),
        ]
        items.append(fill(_("Accounting"), "", accounting_sub))

    return items


def event_management_menu(
        request,
        event: Event,
) -> typing.List[MenuItem]:
    fill = functools.partial(_fill, event, request.resolver_match.view_name)

    items: typing.List[MenuItem] = [
        fill(_("People"), "kirppu:people_manage"),
    ]
    return items
