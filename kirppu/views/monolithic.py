from collections import namedtuple
from functools import wraps
import json
import typing

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import (
    PermissionDenied,
    ValidationError,
)
from django.contrib import messages
import django.urls as url
from django.db import transaction, models
from django.http.response import (
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseForbidden,
    HttpResponseRedirect,
)
from django.http import Http404
from django.shortcuts import (
    redirect,
    render,
    reverse,
    get_object_or_404,
)
from django.utils import timezone
from django.utils.formats import localize
from django.utils.translation import gettext as _
from django.views.csrf import csrf_failure as django_csrf_failure
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods
from django.views.generic import RedirectView

from ..checkout_api import clerk_logout_fn
from .. import ajax_util
from ..forms import BoxAdjustForm, ItemRemoveForm, VendorItemForm, VendorBoxForm, remove_item_from_receipt as _remove_item_from_receipt
from ..fields import ItemPriceField
from .menu import vendor_menu
from ..models import (
    Account,
    Box,
    Clerk,
    Event,
    EventPermission,
    Item,
    ItemType,
    Vendor,
    UserAdapter,
    UIText,
    Receipt,
)
from ..stats import ItemCountData, ItemEurosData
from ..util import get_form
from ..utils import (
    barcode_view,
    is_vendor_open,
    is_registration_closed_for_users,
    require_vendor_open,
)
from ..templatetags.kirppu_tags import get_dataurl
from .ui_text_utils import ui_text_vars
from .vendors import get_multi_vendor_values
import pubcode

__all__ = [
    "index",
    "MobileRedirect",
    "item_add",
    "item_hide",
    "item_to_not_printed",
    "item_to_printed",
    "item_update_price",
    "item_update_name",
    "item_update_type",
    "all_to_print",
    "box_add",
    "box_hide",
    "box_print",
    "box_content",
    "get_items",
    "get_boxes",
    "get_clerk_codes",
    "get_counter_commands",
    "get_boxes_codes",
    "checkout_view",
    "overseer_view",
    "stats_view",
    "type_stats_view",
    "statistical_stats_view",
    "vendor_view",
    "accept_terms",
    "remove_item_from_receipt",
    "lost_and_found_list",
    "kirppu_csrf_failure",
    "adjust_box_size",
]


class PlainResponse(HttpResponse):
    def __init__(self, content=b"", **kwargs):
        kwargs.setdefault("content_type", "text/plain; charset=utf-8")
        super().__init__(content, **kwargs)


def index(request):
    return redirect("kirppu:front_page")


class MobileRedirect(RedirectView):
    permanent = False
    pattern_name = "kirppu:mobile"


@login_required
@require_http_methods(["POST"])
@require_vendor_open
def item_add(request, event):
    if not Vendor.has_accepted(request, event):
        return HttpResponseBadRequest("Missing acceptance of terms.")
    vendor = Vendor.get_or_create_vendor(request, event)
    form = VendorItemForm(request.POST, event)
    if not form.is_valid():
        return HttpResponseBadRequest(form.get_any_error())

    item_cnt = Item.objects.filter(vendor=vendor).count()

    # Create the items and construct a response containing all the items that have been added.
    response = []
    max_items = settings.KIRPPU_MAX_ITEMS_PER_VENDOR
    data = form.db_values()
    name = data.pop("name")

    for suffix in form.cleaned_data["suffixes"]:
        if item_cnt >= max_items:
            error_msg = _(u"You have %(max_items)s items, which is the maximum. No more items can be registered.")
            return HttpResponseBadRequest(error_msg % {'max_items': max_items})
        item_cnt += 1

        suffixed_name = (name + u" " + suffix).strip() if suffix else name
        try:
            item = Item.new(
                name=suffixed_name,
                vendor=vendor,
                **data
            )
        except ValidationError as e:
            return HttpResponseBadRequest(" ".join(e.messages))

        item_dict = item.as_public_dict()
        item_dict['barcode_dataurl'] = get_dataurl(item.code, 'png')
        response.append(item_dict)

    return HttpResponse(json.dumps(response), 'application/json')


@login_required
@require_http_methods(["POST"])
def item_hide(request, event_slug, code):
    event = get_object_or_404(Event, slug=event_slug)
    with transaction.atomic():
        vendor = Vendor.get_vendor(request, event)
        item = get_object_or_404(Item.objects.select_for_update(), code=code, vendor=vendor)

        item.hidden = True
        item.save(update_fields=("hidden",))

    return PlainResponse()


@login_required
@require_http_methods(['POST'])
def item_to_not_printed(request, event_slug, code):
    event = get_object_or_404(Event, slug=event_slug)
    with transaction.atomic():
        vendor = Vendor.get_vendor(request, event)
        item = get_object_or_404(Item.objects.select_for_update(), code=code, vendor=vendor, box__isnull=True)

        if settings.KIRPPU_COPY_ITEM_WHEN_UNPRINTED:
            # Create a duplicate of the item with a new code and hide the old item.
            # This way, even if the user forgets to attach the new tags, the old
            # printed tag is still in the system.
            if not is_vendor_open(request, event):
                return HttpResponseForbidden("Registration is closed")

            new_item = Item.new(
                name=item.name,
                price=item.price,
                vendor=item.vendor,
                type=item.type,
                state=Item.ADVERTISED,
                itemtype=item.itemtype,
                adult=item.adult
            )
            item.hidden = True
        else:
            item.printed = False
            new_item = item
        item.save(update_fields=("hidden", "printed"))

    item_dict = new_item.as_public_dict()
    item_dict["barcode_dataurl"] = get_dataurl(new_item.code, "png")

    return HttpResponse(json.dumps(item_dict), 'application/json')


@login_required
@require_http_methods(["POST"])
def item_to_printed(request, event_slug, code):
    event = get_object_or_404(Event, slug=event_slug)
    with transaction.atomic():
        vendor = Vendor.get_vendor(request, event)
        item = get_object_or_404(Item.objects.select_for_update(), code=code, vendor=vendor, box__isnull=True)

        item.printed = True
        item.save(update_fields=("printed",))

    return PlainResponse()


@login_required
@require_http_methods(["POST"])
@require_vendor_open
def item_update_price(request, event, code):
    try:
        price = ItemPriceField().clean(request.POST.get('value'))
    except ValidationError as error:
        return HttpResponseBadRequest(u' '.join(error.messages))

    with transaction.atomic():
        vendor = Vendor.get_vendor(request, event)
        item = get_object_or_404(Item.objects.select_for_update(), code=code, vendor=vendor, box__isnull=True)

        if item.is_locked():
            return HttpResponseBadRequest("Item has been brought to event. Price can't be changed.")

        item.price = price
        item.save(update_fields=("price",))

    return PlainResponse(str(item.price_fmt).replace(".", ","))


@login_required
@require_http_methods(["POST"])
@require_vendor_open
def item_update_name(request, event, code):
    name = request.POST.get("value")
    if name is None or name == "":
        return HttpResponseBadRequest("Name is required.")

    max_len = Item._meta.get_field("name").max_length
    name = name.strip()[:max_len].strip()

    with transaction.atomic():
        vendor = Vendor.get_vendor(request, event)
        item = get_object_or_404(Item.objects.select_for_update(), code=code, vendor=vendor)

        if item.is_locked():
            return HttpResponseBadRequest("Item has been brought to event. Name can't be changed.")

        item.name = name
        item.save(update_fields=("name",))

    return PlainResponse(name)


@login_required
@require_http_methods(["POST"])
def item_update_type(request, event_slug, code):
    event = get_object_or_404(Event, slug=event_slug)
    tag_type = request.POST.get("tag_type", None)

    with transaction.atomic():
        vendor = Vendor.get_vendor(request, event)
        item = get_object_or_404(Item.objects.select_for_update(), code=code, vendor=vendor)
        item.type = tag_type
        item.save(update_fields=("type",))
    return PlainResponse()


@login_required
@require_http_methods(["POST"])
def all_to_print(request, event_slug):
    event = get_object_or_404(Event, slug=event_slug)
    vendor = Vendor.get_vendor(request, event)
    items = Item.objects.filter(vendor=vendor).filter(printed=False).filter(box__isnull=True)

    items.update(printed=True)

    return PlainResponse()


@login_required
@require_http_methods(["POST"])
@require_vendor_open
def box_add(request, event):
    if not event.use_boxes:
        raise Http404()

    if not Vendor.has_accepted(request, event):
        return HttpResponseBadRequest("Missing acceptance of terms.")
    vendor = Vendor.get_vendor(request, event)
    form = VendorBoxForm(request.POST, event)
    if not form.is_valid():
        return HttpResponseBadRequest(form.get_any_error())

    data = form.db_values()

    # Verify that user doesn't exceed his/hers item quota with the box.
    max_items = settings.KIRPPU_MAX_ITEMS_PER_VENDOR
    item_cnt = Item.objects.filter(vendor=vendor).count()
    count = data["count"]
    if count < event.min_box_size:
        error_msg = "Box size must be greater or equal than %(box_size)d."
        return HttpResponseBadRequest(error_msg % {"box_size": event.min_box_size})
    if item_cnt >= max_items:
        error_msg = _(u"You have %(max_items)s items, which is the maximum. No more items can be registered.")
        return HttpResponseBadRequest(error_msg % {'max_items': max_items})
    elif max_items < count + item_cnt:
        error_msg = _(u"You have %(item_cnt)s items. "
                      u"Creating this box would cause the items to exceed the maximum number of allowed items.")
        return HttpResponseBadRequest(error_msg % {'item_cnt': item_cnt})

    # Create the box and items. and construct a response containing box and all the items that have been added.
    box = Box.new(
        vendor=vendor,
        **data
    )

    box_dict = box.as_public_dict()
    box_dict["vendor_id"] = vendor.id
    box_dict["event"] = event

    return render(request, "kirppu/app_boxes_box.html", box_dict)


@login_required
@require_http_methods(["POST"])
def box_hide(request, event_slug, box_id):
    event = get_object_or_404(Event, slug=event_slug)
    if not event.use_boxes:
        raise Http404()

    with transaction.atomic():

        vendor = Vendor.get_vendor(request, event)
        box = get_object_or_404(Box.objects, id=box_id)
        box_vendor = box.get_vendor()
        if box_vendor.id != vendor.id:
            raise Http404()

        box.set_hidden(True)

    return PlainResponse()


@login_required
@require_http_methods(["POST"])
def box_print(request, event_slug, box_id):
    event = get_object_or_404(Event, slug=event_slug)
    if not event.use_boxes:
        raise Http404()

    with transaction.atomic():

        vendor = Vendor.get_vendor(request, event)
        box = get_object_or_404(Box.objects, id=box_id)
        box_vendor = box.get_vendor()
        if box_vendor.id != vendor.id:
            raise Http404()

        box.set_printed(True)

    return PlainResponse()


@login_required
@require_http_methods(["GET"])
@barcode_view
def box_content(request, event_slug, box_id, bar_type):

    """
    Get a page containing the contents of one box for printing

    :param request: HttpRequest object.
    :type request: django.http.request.HttpRequest
    :param bar_type: Image type of the generated bar. See `kirppu_tags.barcode_dataurl`.
    :type bar_type: str
    :return: HttpResponse or HttpResponseBadRequest
    """

    event = get_object_or_404(Event, slug=event_slug)
    if not event.use_boxes:
        raise Http404()

    vendor = Vendor.get_vendor(request, event)
    boxes = Box.objects.filter(id=box_id, item__vendor=vendor, item__hidden=False).distinct()
    if boxes.count() == 0:
        raise Http404()
    box = boxes[0]
    item = box.get_representative_item()

    render_params = {
        'box': box,
        'item': item,
        'bar_type': bar_type,
        'CURRENCY': settings.KIRPPU_CURRENCY,
    }

    return render(request, "kirppu/app_boxes_content.html", render_params)


@login_required
@require_http_methods(["GET"])
@barcode_view
def get_items(request, event_slug, bar_type):
    """
    Get a page containing all items for vendor.

    :param request: HttpRequest object.
    :type request: django.http.request.HttpRequest
    :return: HttpResponse or HttpResponseBadRequest
    """

    event = get_object_or_404(Event, slug=event_slug)
    event.require_default_db()

    user = request.user
    if user.is_staff and "user" in request.GET:
        user = get_object_or_404(get_user_model(), username=request.GET["user"])

    vendor = Vendor.get_vendor(request, event)

    vendor_data = get_multi_vendor_values(request, event)
    if event.multiple_vendors_per_user and user.is_staff and "user" in request.GET:
        raise NotImplementedError  # FIXME: Decide how this should work.

    vendor_items = Item.objects.filter(vendor=vendor, hidden=False, box__isnull=True)
    items = vendor_items.filter(printed=False).annotate(item_type=models.F("itemtype__title"))
    printed_items = vendor_items.filter(printed=True)

    # Order from newest to oldest, because that way new items are added
    # to the top and the user immediately sees them without scrolling
    # down.
    items = items.order_by('-id')

    item_name_placeholder = UIText.get_text(event, "item_placeholder", _("Ranma ½ Vol."))

    render_params = {
        'event': event,
        'source_event': event.get_real_event(),
        'items': items,
        'printed_items': printed_items,
        'bar_type': bar_type,
        'item_name_placeholder': item_name_placeholder,

        'profile_url': settings.PROFILE_URL,
        'terms_accepted': vendor.terms_accepted if vendor is not None else False,

        'is_registration_open': is_vendor_open(request, event),
        'is_registration_closed_for_users': is_registration_closed_for_users(event=event),
        'menu': vendor_menu(request, event),
        'itemTypes': ItemType.as_tuple(event),
        'CURRENCY': settings.KIRPPU_CURRENCY,
        'PRICE_MIN_MAX': settings.KIRPPU_MIN_MAX_PRICE,
        'name_max_len': Item._meta.get_field('name').max_length,
        "logout_next": reverse("kirppu:vendor_view", kwargs={"event_slug": event.slug}),
    }
    render_params.update(vendor_data)

    return render(request, "kirppu/app_items.html", render_params)


@login_required
@require_http_methods(["GET"])
def get_boxes(request, event_slug):
    """
    Get a page containing all boxes for vendor.

    :param request: HttpRequest object.
    :type request: django.http.request.HttpRequest
    :return: HttpResponse or HttpResponseBadRequest
    """
    event = get_object_or_404(Event, slug=event_slug)
    event.require_default_db()
    if not event.use_boxes:
        raise Http404()

    user = request.user
    if user.is_staff and "user" in request.GET:
        user = get_object_or_404(get_user_model(), username=request.GET["user"])

    vendor = Vendor.get_vendor(request, event)
    vendor_data = get_multi_vendor_values(request, event)

    boxes = Box.objects.filter(item__vendor=vendor, item__hidden=False).distinct()
    boxes = boxes.select_related("representative_item__itemtype")

    # Order from newest to oldest, because that way new boxes are added
    # to the top and the user immediately sees them without scrolling
    # down.
    boxes = boxes.order_by('-id')

    box_name_placeholder = UIText.get_text(event, "box_placeholder", _("Box full of Ranma"))

    render_params = {
        'event': event,
        'source_event': event.get_real_event(),
        'boxes': boxes,
        'box_name_placeholder': box_name_placeholder,
        'min_box_size_placeholder': max(event.min_box_size, 10),

        'profile_url': settings.PROFILE_URL,
        'terms_accepted': vendor.terms_accepted if vendor is not None else False,

        'is_registration_open': is_vendor_open(request, event),
        'is_registration_closed_for_users': is_registration_closed_for_users(event),
        'menu': vendor_menu(request, event),
        'itemTypes': ItemType.as_tuple(event),
        'CURRENCY': settings.KIRPPU_CURRENCY,
        'PRICE_MIN_MAX': settings.KIRPPU_MIN_MAX_PRICE,
        "logout_next": reverse("kirppu:vendor_view", kwargs={"event_slug": event.slug}),
    }
    render_params.update(vendor_data)

    return render(request, "kirppu/app_boxes.html", render_params)


@login_required
@barcode_view
def get_clerk_codes(request, event_slug, bar_type):
    event = get_object_or_404(Event, slug=event_slug)
    if not (request.user.is_staff or EventPermission.get(event, request.user).can_see_clerk_codes):
        return HttpResponseForbidden()

    bound = []
    unbound = []
    code_item = namedtuple("CodeItem", "name code")

    for c in Clerk.objects.filter(event=event, access_key__isnull=False):
        if not c.is_valid_code:
            continue
        code = c.get_code()
        if c.user is not None:
            name = c.user.get_short_name()
            if len(name) == 0:
                name = c.user.get_username()
            bound.append(code_item(name=name, code=code))
        else:
            unbound.append(code_item(name="", code=code))

    items = None
    if bound or unbound:
        bound.sort(key=lambda a: a.name + a.code)
        unbound.sort(key=lambda a: a.code)
        items = bound + unbound

        # Generate a code to check it's length.
        name, code = items[0]
        width = pubcode.Code128(code, charset='B').width(add_quiet_zone=True)
    else:
        width = None  # Doesn't matter.

    return render(request, "kirppu/app_clerks.html", {
        'event': event,
        'items': items,
        'bar_type': bar_type,
        'repeat': range(1),
        'barcode_width': width,
    })


@login_required
@barcode_view
def get_counter_commands(request, event_slug, bar_type):
    event = get_object_or_404(Event, slug=event_slug)
    if not (request.user.is_staff or UserAdapter.is_clerk(request.user, event)):
        raise PermissionDenied()

    return render(request, "kirppu/app_commands.html", {
        'event_slug': event_slug,
        'title': _(u"Counter commands"),
    })


@login_required
@barcode_view
def get_boxes_codes(request, event_slug, bar_type):
    event = get_object_or_404(Event, slug=event_slug)
    if not event.use_boxes:
        raise Http404()
    if not (request.user.is_staff or UserAdapter.is_clerk(request.user, event)):
        raise PermissionDenied()

    boxes = Box.objects.filter(representative_item__vendor__event=event, box_number__isnull=False).order_by("box_number")
    vm = []
    for box in boxes:
        code = "box%d" % box.box_number
        img = pubcode.Code128(code, charset='B').data_url(image_format=bar_type, add_quiet_zone=True)
        r = box.get_representative_item()  # type: Item

        vm.append({
            "name": box.description,
            "code": code,
            "data_url": img,
            "adult": r.adult,
            "vendor_id": r.vendor_id,
            "price": r.price_fmt,
            "bundle_size": box.bundle_size,
            "box_number": box.box_number,
        })

    return render(request, "kirppu/boxes_list.html", {
        "bar_type": bar_type,
        "boxes": vm,
        "event": event,
    })


@ensure_csrf_cookie
def checkout_view(request, event_slug):
    """
    Checkout view.

    :param request: HttpRequest object
    :type request: django.http.request.HttpRequest
    :return: Response containing the view.
    :rtype: HttpResponse
    """
    event = get_object_or_404(Event, slug=event_slug)
    if not event.checkout_active:
        raise PermissionDenied()

    clerk_logout_fn(request)
    context = {
        'CURRENCY': settings.KIRPPU_CURRENCY,
        'PURCHASE_MAX': settings.KIRPPU_MAX_PURCHASE,
        'event': event,
    }
    if settings.KIRPPU_AUTO_CLERK and settings.DEBUG:
        if settings.KIRPPU_AUTO_CLERK != "*":
            real_clerks = Clerk.objects.filter(event=event, user__username=settings.KIRPPU_AUTO_CLERK)
        else:
            real_clerks = Clerk.objects.filter(event=event, user__isnull=False)
        for clerk in real_clerks:
            if clerk.is_enabled:
                context["auto_clerk"] = clerk.get_code()
                break

    return render(request, "kirppu/app_checkout.html", context)


@ensure_csrf_cookie
def overseer_view(request, event_slug):
    """Overseer view."""
    event = get_object_or_404(Event, slug=event_slug)
    if not event.checkout_active:
        raise PermissionDenied()

    try:
        ajax_util.require_user_features(counter=True, clerk=True, overseer=True)(lambda _: None)(request)
    except ajax_util.AjaxError:
        return redirect('kirppu:checkout_view', event_slug=event.slug)
    else:
        context = {
            'event': event,
            'itemtypes': ItemType.as_tuple(event),
            'itemstates': Item.STATE,
            'CURRENCY': settings.KIRPPU_CURRENCY,
        }
        return render(request, 'kirppu/app_overseer.html', context)


def _statistics_access(fn):
    @wraps(fn)
    def inner(request, event_slug, *args, **kwargs):
        event = get_object_or_404(Event, slug=event_slug)
        try:
            if not EventPermission.get(event, request.user).can_see_statistics:
                ajax_util.require_user_features(counter=True, clerk=True, staff_override=True)(lambda _: None)(request)
            # else: User has permissions, no further checks needed.
        except ajax_util.AjaxError:
            if event.checkout_active:
                return redirect('kirppu:checkout_view', event_slug=event.slug)
            else:
                raise PermissionDenied()
        return fn(request, event, *args, **kwargs)
    return inner


@ensure_csrf_cookie
@_statistics_access
def stats_view(request, event: Event):
    """Stats view."""
    original_event = event
    event = event.get_real_event()
    ic = ItemCountData(ItemCountData.GROUP_ITEM_TYPE, event=event)
    ie = ItemEurosData(ItemEurosData.GROUP_ITEM_TYPE, event=event)
    sum_name = _("Sum")
    item_types = (ItemType.objects
                  .using(event.get_real_database_alias())
                  .filter(event=event)
                  .order_by("order")
                  .values_list("id", "title"))

    number_of_items = [
        ic.data_set(item_type, type_name)
        for item_type, type_name in item_types
    ]
    number_of_items.append(ic.data_set("sum", sum_name))

    number_of_euros = [
        ie.data_set(item_type, type_name)
        for item_type, type_name in item_types
    ]
    number_of_euros.append(ie.data_set("sum", sum_name))

    vendor_item_data_counts = []
    vendor_item_data_euros = []
    vic = ItemCountData(ItemCountData.GROUP_VENDOR, event=event)
    vie = ItemEurosData(ItemEurosData.GROUP_VENDOR, event=event)
    vie.use_cents = True
    vendor_item_data_row_size = 0

    for vendor_id in vic.keys():
        name = _("Vendor %i") % vendor_id
        counts = vic.data_set(vendor_id, name)
        euros = vie.data_set(vendor_id, name)
        if vendor_item_data_row_size == 0:
            vendor_item_data_row_size = len(list(counts.property_names))

        vendor_item_data_counts.append(counts)
        vendor_item_data_euros.append(euros)

    context = {
        'event': event,
        'event_slug': original_event.slug,
        'number_of_items': number_of_items,
        'number_of_euros': number_of_euros,
        'vendor_item_data_counts': vendor_item_data_counts,
        'vendor_item_data_euros': vendor_item_data_euros,
        'vendor_item_data_row_size': vendor_item_data_row_size,
        'vendor_item_data_order': json.dumps(ItemCountData.columns()),
        'CURRENCY': settings.KIRPPU_CURRENCY["raw"],
    }

    return render(request, 'kirppu/app_stats.html', context)


@ensure_csrf_cookie
@_statistics_access
def type_stats_view(request, event: Event, type_id):
    original_event = event
    event = event.get_real_event()
    item_type = get_object_or_404(ItemType.objects.using(event.get_real_database_alias()), event=event, id=int(type_id))

    return render(request, "kirppu/type_stats.html", {
        "event": original_event,
        "type_id": item_type.id,
        "type_title": item_type.title,
    })


def _float_array(array):
    # noinspection PyPep8Naming
    INFINITY = float('inf')

    def _float(f):
        if f != f:
            return "NaN"
        elif f == INFINITY:
            return 'Infinity'
        elif f == -INFINITY:
            return '-Infinity'
        return float.__repr__(f)

    line_length = 20

    o = [
        ", ".join(_float(e) for e in array[i:i + line_length])
        for i in range(0, len(array), line_length)
    ]

    return "[\n" + ",\n".join(o) + "]"


@ensure_csrf_cookie
@_statistics_access
def statistical_stats_view(request, event: Event):
    original_event = event
    event = event.get_real_event()
    database = event.get_real_database_alias()
    brought_states = (Item.BROUGHT, Item.STAGED, Item.SOLD, Item.COMPENSATED, Item.RETURNED)

    _items = Item.objects.using(database).filter(vendor__event=event)
    _vendors = Vendor.objects.using(database).filter(event=event)
    _boxes = Box.objects.using(database).filter(representative_item__vendor__event=event)

    registered = _items.count()
    deleted = _items.filter(hidden=True).count()
    brought_q = _items.filter(state__in=brought_states)
    brought = brought_q.count()
    sold = _items.filter(state__in=(Item.STAGED, Item.SOLD, Item.COMPENSATED)).count()
    printed_deleted = _items.filter(hidden=True, printed=True).count()
    printed_not_brought = _items.filter(printed=True, state=Item.ADVERTISED).count()

    items_in_box = _items.filter(box__isnull=False).count()
    items_not_in_box = _items.filter(box__isnull=True).count()
    brought_box_items = brought_q.filter(box__isnull=False).count()
    registered_boxes = _boxes.count()
    deleted_boxes = _boxes.filter(representative_item__hidden=True).count()
    brought_boxes = _boxes.filter(representative_item__state__in=brought_states).count()
    items_in_deleted_boxes = _items.filter(box__representative_item__hidden=True).count()

    general = {
        "registered": registered,
        "deleted": deleted,
        "deletedOfRegistered": (deleted * 100.0 / registered) if registered > 0 else 0,
        "brought": brought,
        "broughtOfRegistered": (brought * 100.0 / registered) if registered > 0 else 0,
        "broughtBoxItems": brought_box_items,
        "broughtBoxItemsOfRegistered": (brought_box_items * 100.0 / items_in_box) if items_in_box > 0 else 0,
        "printedDeleted": printed_deleted,
        "printedNotBrought": printed_not_brought,
        "sold": sold,
        "soldOfBrought": (sold * 100.0 / brought) if brought > 0 else 0,
        "vendors": _vendors.filter(item__state__in=brought_states).distinct().count(),
        "vendorsTotal": _vendors.annotate(items=models.Count("item__id")).filter(items__gt=0).count(),
        "vendorsInMobileView": _vendors.filter(mobile_view_visited=True).count(),

        "itemsInBox": items_in_box,
        "itemsNotInBox": items_not_in_box,
        "broughtBoxes": brought_boxes,
        "broughtBoxesOfRegistered": (brought_boxes * 100.0 / registered_boxes) if registered_boxes > 0 else 0,
        "registeredBoxes": registered_boxes,
        "deletedBoxes": deleted_boxes,
        "deletedOfRegisteredBoxes": (deleted_boxes * 100.0 / registered_boxes) if registered_boxes > 0 else 0,
        "itemsInDeletedBoxes": items_in_deleted_boxes,
        "itemsInDeletedBoxesOfRegistered": (items_in_deleted_boxes * 100.0 / registered) if registered > 0 else 0,
    }

    compensations = _vendors.filter(item__state=Item.COMPENSATED) \
        .annotate(v_sum=models.Sum("item__price")).order_by("v_sum").values_list("v_sum", flat=True)
    compensations = [float(e) for e in compensations]

    purchases = list(
        Receipt.objects.using(database).filter(counter__event=event, status=Receipt.FINISHED, type=Receipt.TYPE_PURCHASE)
        .order_by("total")
        .values_list("total", flat=True)
    )
    purchases = [float(e) for e in purchases]
    general["purchases"] = len(purchases)

    brought_distribution = (
        _vendors
        .filter(item__state__in=brought_states)
        .annotate(item_count=models.Count("item__id"))
        .filter(item_count__gt=0)
        .order_by("item_count")
        .values_list("item_count", flat=True)
    )
    brought_price_distribution = (
        _items
        .filter(state__in=brought_states)
        .values_list("price", flat=True)
    )

    return render(request, "kirppu/general_stats.html", {
        "event": original_event,
        "compensations": _float_array(compensations),
        "purchases": _float_array(purchases),
        "brought": "[" + ",".join(str(e) for e in brought_distribution) + "]",
        "brought_prices": "[" + ",".join(str(e) for e in brought_price_distribution) + "]",
        "general": general,
        "CURRENCY": settings.KIRPPU_CURRENCY["raw"],
    })


def vendor_view(request, event_slug):
    """
    Render main view for vendors.

    :rtype: HttpResponse
    """
    event = get_object_or_404(Event, slug=event_slug)
    user = request.user
    source_event = event.get_real_event()

    vendor_data = get_multi_vendor_values(request, event)
    if user.is_authenticated:
        database = source_event.get_real_database_alias()
        vendor = vendor_data["current_vendor"]
        items = Item.objects.using(database).filter(vendor=vendor, hidden=False, box__isnull=True)
        boxes = Box.objects.using(database).filter(item__vendor=vendor, item__hidden=False).distinct()
        boxed_items = Item.objects.using(database).filter(vendor=vendor, hidden=False, box__isnull=False)
    else:
        vendor = None
        items = []
        boxes = []
        boxed_items = Item.objects.none()

    box_info = boxed_items.aggregate(sum=models.Sum("price"), count=models.Count("id"))
    is_manager = request.user.is_superuser or EventPermission.get(event, request.user).can_manage_event

    context = {
        'event': event,
        'source_event': source_event,
        'user': user,
        'items': items,

        'total_price': sum(i.price for i in items),
        'num_total': len(items),
        'num_printed': len(list(filter(lambda i: i.printed, items))),

        'boxes': boxes,
        'boxes_count': len(boxes),
        'boxes_total_price': box_info["sum"],
        'boxes_item_count': box_info["count"],
        'boxes_printed': len(list(filter(lambda i: i.is_printed(), boxes))),

        'profile_url': settings.PROFILE_URL,
        'menu': vendor_menu(request, event),
        'CURRENCY': settings.KIRPPU_CURRENCY,
        "allow_preview": is_manager,
        "uiTextVars": ui_text_vars(event),
        "logout_next": request.path,
    }
    context.update(vendor_data)
    return render(request, "kirppu/app_frontpage.html", context)


@login_required
@require_http_methods(["POST"])
def accept_terms(request, event_slug):
    event = get_object_or_404(Event, slug=event_slug)
    event.require_default_db()

    vendor = Vendor.get_or_create_vendor(request, event)
    if vendor.terms_accepted is None:
        vendor.terms_accepted = timezone.now()
        vendor.save(update_fields=("terms_accepted",))

    result = timezone.template_localtime(vendor.terms_accepted)
    result = localize(result)

    return HttpResponse(json.dumps({
        "result": "ok",
        "time": result,
    }), "application/json")


@login_required
def remove_item_from_receipt(request, event_slug):
    event = get_object_or_404(Event, slug=event_slug)
    if not request.user.is_staff:
        raise PermissionDenied()

    form = get_form(ItemRemoveForm, request, event=event)

    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                removal = _remove_item_from_receipt(request, form.cleaned_data["code"], form.cleaned_data["receipt"])
                account_id = removal.receipt.dst_account_id
                Account.objects.filter(pk=account_id).update(balance=models.F("balance") - removal.item.price)
        except (ValueError, AssertionError) as e:
            form.add_error(None, e.args[0])
        else:
            messages.add_message(request, messages.INFO, "Item {0} removed from {1}".format(
                form.cleaned_data["code"], removal.receipt
            ))
            return HttpResponseRedirect(url.reverse('kirppu:remove_item_from_receipt',
                                                    kwargs={"event_slug": event.slug}))

    return render(request, "kirppu/admin_edit.html", {
        "title": "Remove item from receipt",
        "form": form,
    })


@login_required
def lost_and_found_list(request, event_slug):
    event = Event.objects.get(slug=event_slug)
    event.require_default_db()
    if not EventPermission.get(event, request.user).can_see_accounting:
        raise PermissionDenied
    items = Item.objects \
        .select_related("vendor") \
        .filter(vendor__event=event, lost_property=True, abandoned=False) \
        .order_by("vendor", "name")

    vendor_object = namedtuple("VendorItems", "vendor vendor_id items")

    vendor_list = {}
    for item in items:
        vendor_id = item.vendor_id
        if vendor_id not in vendor_list:
            vendor_list[vendor_id] = vendor_object(item.vendor.user, item.vendor_id, [])

        vendor_list[vendor_id].items.append(item)

    return render(request, "kirppu/lost_and_found.html", {
        'menu': vendor_menu(request, event),
        'event': event,
        'items': vendor_list,
    })


def kirppu_csrf_failure(request, reason=""):
    if request.META.get("HTTP_ACCEPT", "") in ("text/json", "application/json"):
        # TODO: Unify the response to match requested content type.
        return HttpResponseForbidden(
            _("CSRF verification failed. Request aborted."),
            content_type="text/plain; charset=utf-8",
        )
    else:
        return django_csrf_failure(request, reason=reason)


@login_required
def adjust_box_size(request, event_slug):
    event = get_object_or_404(Event, slug=event_slug)
    if not request.user.is_staff:
        raise PermissionDenied

    form = get_form(BoxAdjustForm, request, event=event)

    if request.method == "POST" and form.is_valid():
        code = form.cleaned_data["code"]
        item_count = form.cleaned_data["item_count"]

        representative_item = Item.objects.get(code=code)
        box = representative_item.box

        if representative_item.id != box.representative_item_id:
            representative_item = box.representative_item

        existing_count = box.get_item_count()

        # If box hasn't been brought (i.e. is AD), the new items should also be AD. Parts can be hidden.
        # If box is brought, staged, sold or compensated, the new items should be BR. Parts to hide must be BR.
        # If box is returned or missing, abort. (Checked in form clean)

        if existing_count == item_count:
            messages.add_message(request, messages.INFO, "Nothing to do.")
        elif existing_count < item_count:
            to_add = item_count - existing_count

            # Unhide first up to to_add items.
            hidden_items = Item.objects.filter(box=box, hidden=True).order_by("id")
            unhide = min(len(hidden_items), to_add)
            for i in range(unhide):
                item = hidden_items[i]
                item.hidden = False
                item.save(update_fields=["hidden"])

            new_state = Item.ADVERTISED if representative_item.state == Item.ADVERTISED else Item.BROUGHT

            # If we need more items, clone them.
            add = max(to_add - len(hidden_items), 0)
            for i in range(add):
                Item.new(
                    name=representative_item.name,
                    box=box,
                    no_code=True,

                    price=representative_item.price,
                    vendor=representative_item.vendor,
                    state=new_state,
                    type=representative_item.type,
                    itemtype=representative_item.itemtype,
                    adult=representative_item.adult,
                    abandoned=representative_item.abandoned,
                    printed=representative_item.printed,
                    hidden=representative_item.hidden,
                )
            messages.add_message(request, messages.INFO, "Unhidden {0} and added {1} items to box {2}".format(
                unhide, add, code))
        else:
            to_remove = existing_count - item_count

            visible_items = Item.objects.filter(box=box, hidden=False,
                                                state__in=(Item.ADVERTISED, Item.BROUGHT)).order_by("-id")[:to_remove]
            for item in visible_items:
                item.hidden = True
                item.save(update_fields=["hidden"])

            if len(visible_items) != to_remove:
                to_remove = "(only) {}/{}".format(len(visible_items), to_remove)
            messages.add_message(request, messages.INFO, "Hide {0} items from box {1}".format(to_remove, code))
        return HttpResponseRedirect(url.reverse("kirppu:adjust_box_size",
                                                kwargs={"event_slug": event.slug}))

    return render(request, "kirppu/admin_edit.html", {
        "title": "Adjust box size",
        "form": form,
    })
