from django.urls import path, re_path, include

from .ajax_util import get_all_ajax_functions
from .views import (
    get_boxes_codes,
    get_clerk_codes,
    get_counter_commands,
    checkout_view,
    overseer_view,
    vendor_view,
    accept_terms,
    get_items,
    all_to_print,
    item_add,
    item_hide,
    item_to_printed,
    item_to_not_printed,
    item_update_name,
    item_update_type,
    item_update_price,
    remove_item_from_receipt,
    get_boxes,
    box_add,
    box_content,
    box_hide,
    box_print,
    stats_view,
    type_stats_view,
    statistical_stats_view,
    lost_and_found_list,
)
from .views.frontpage import front_page
from .checkout_api import checkout_js
from .views.mobile import index as mobile_index, logout as mobile_logout
from .views.vendors import change_vendor, create_vendor
from .views.accounting import accounting_receipt_view
from .views.item_dump import dump_items_view

__author__ = 'jyrkila'

app_name = "kirppu"

event_urls = [
    path(r'accounting/', accounting_receipt_view, name="accounting"),
    path(r'itemdump/', dump_items_view, name="item_dump"),
    path(r'clerks/', get_clerk_codes, name='clerks'),
    path(r'boxes/', get_boxes_codes, name="box_codes"),
    path(r'checkout/', checkout_view, name='checkout_view'),
    path(r'overseer/', overseer_view, name='overseer_view'),
    path(r'stats/', stats_view, name='stats_view'),
    path(r'stats/type/<str:type_id>', type_stats_view, name='type_stats_view'),
    path(r'stats/statistical/', statistical_stats_view, name='statistical_stats_view'),
    path(r'', vendor_view, name='vendor_view'),
    path(r'vendor/', vendor_view),
    path(r'vendor/accept_terms', accept_terms, name='accept_terms'),
    path(r'vendor/items/', get_items, name='page'),
    path(r'vendor/items/move_to_print', all_to_print, name='all_to_print'),
    path(r'vendor/item/', item_add, name='item_add'),
    path(r'vendor/item/<str:code>/to_printed', item_to_printed, name='item_to_printed'),
    path(r'vendor/item/<str:code>/price', item_update_price, name='item_update_price'),
    path(r'vendor/item/<str:code>/name', item_update_name, name='item_update_name'),
    path(r'vendor/item/<str:code>/type', item_update_type, name='item_update_type'),
    path(r'vendor/item/<str:code>/to_not_printed', item_to_not_printed, name='item_to_not_printed'),
    path(r'vendor/item/<str:code>/hide', item_hide, name='item_hide'),
    path(r'remove_item', remove_item_from_receipt, name='remove_item_from_receipt'),
    path(r'lost_and_found/', lost_and_found_list, name='lost_and_found'),
    path(r'vendor/boxes/', get_boxes, name='vendor_boxes'),
    path(r'vendor/box/', box_add, name='box_add'),
    path(r'vendor/box/<str:box_id>/content', box_content, name='box_content'),
    path(r'vendor/box/<str:box_id>/hide', box_hide, name='box_hide'),
    path(r'vendor/box/<str:box_id>/print', box_print, name='box_print'),

    path(r'vendor/status/', mobile_index, name='mobile'),
    path(r'vendor/status/logout/', mobile_logout, name='mobile_logout'),

    path('vendor/change', change_vendor, name="change_vendor"),
    path('vendor/create', create_vendor, name="create_vendor"),

    path('api/checkout.js', checkout_js, name='checkout_js'),
    path(r'commands/', get_counter_commands, name='commands'),
]

common_urls = [
    path(r'', front_page, name="front_page"),
]

event_urls.extend([
    re_path(func.url, func.func, name=func.view_name)
    for _, func in get_all_ajax_functions()
])

urlpatterns = [path(r'<slug:event_slug>/', include(event_urls))] + common_urls
