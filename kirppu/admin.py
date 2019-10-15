from __future__ import unicode_literals, print_function, absolute_import

import json

from django.core.exceptions import PermissionDenied
from django.conf import settings
from django.conf.urls import url
from django.contrib import admin, messages
from django.contrib.admin.options import get_content_type_for_model
from django.contrib.admin.models import LogEntry, ADDITION, CHANGE
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils.encoding import force_text
from django.utils.html import escape, format_html
from django.utils.translation import ugettext_lazy as ugettext, ngettext

from .forms import (
    ClerkGenerationForm,
    UITextForm,
    ClerkEditForm,
    ClerkSSOForm,
    VendorSetSelfForm,
)

from .models import (
    Clerk,
    Event,
    EventPermission,
    Item,
    ItemType,
    Vendor,
    Counter,
    Person,
    Receipt,
    ReceiptExtraRow,
    ReceiptItem,
    ReceiptNote,
    UIText,
    ItemStateLog,
    Box,
    TemporaryAccessPermit,
    TemporaryAccessPermitLog,
)

from .util import get_form

__author__ = 'jyrkila'


def with_description(short_description):
    def decorator(action_function):
        action_function.short_description = short_description
        return action_function
    return decorator


class FieldAccessor(object):
    """
    Abstract base class for field-links to be used in Admin.list_display.
    Sub-classes must implement __call__ that is used to generate the field text / link.
    """
    def __init__(self, field_name, description):
        """
        :param field_name: Field to link to.
        :type field_name: str
        :param description: Column description.
        :type description: str
        """
        self._field_name = field_name
        self._description = description

    def __call__(self, obj):
        """
        :param obj: Model object from the query.
        :rtype: str
        :return: Unsafe string containing the field value.
        """
        raise NotImplementedError

    @property
    def short_description(self):
        return self._description

    def __str__(self):
        # Django 1.9 converts the field to string for id.
        return self._field_name

    @property
    def __name__(self):
        # Django 1.10 lookups the field name via __name__.
        return self._field_name


class RefLinkAccessor(FieldAccessor):
    """
    Accessor function that returns a link to given FK-field admin.
    """
    def __call__(self, obj):
        field = getattr(obj, self._field_name)
        if field is None:
            return u"(None)"
        if callable(field):
            field = field()
        # noinspection PyProtectedMember
        info = field._meta.app_label, field._meta.model_name
        return format_html(
            u'<a href="{0}">{1}</a>',
            reverse("admin:%s_%s_change" % info, args=(field.id,)),
            escape(field)
        )


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "start_date", "end_date", "registration_end", "checkout_active")
    ordering = ("-start_date", "name")


"""
Admin UI list column that displays user name with link to the user model itself.

:param obj: Object being listed, such as Clerk or Vendor.
:type obj: Clerk | Vendor | T
:return: Contents for the field.
:rtype: unicode
"""
_user_link = RefLinkAccessor("user", ugettext(u"User"))

_person_link = RefLinkAccessor("person", ugettext(u"Person"))

_event_link = RefLinkAccessor("event", ugettext("Event"))


@admin.register(EventPermission)
class EventPermissionAdmin(admin.ModelAdmin):
    list_display = ("id", _event_link, _user_link, "combination")
    list_display_links = ("id", "combination")
    list_filter = (
        "event",
    )
    list_select_related = (
        "event",
        "user",
    )


@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    ordering = ('user__first_name', 'user__last_name')
    search_fields = ['id', 'user__first_name', 'user__last_name', 'user__username',
                     'person__first_name', 'person__last_name']
    list_display = ['id', _user_link, _person_link, "terms_accepted", "event"]
    list_filter = (
        "event",
    )
    list_select_related = (
        "event",
        "user",
    )

    @staticmethod
    def _can_set_user(request, obj):
        return obj is not None and\
            request.user.is_superuser and\
            not obj.user.is_superuser and\
            settings.KIRPPU_SU_AS_USER

    def get_form(self, request, obj=None, **kwargs):
        if self._can_set_user(request, obj):
            kwargs["form"] = VendorSetSelfForm
        return super(VendorAdmin, self).get_form(request, obj, **kwargs)

    def get_readonly_fields(self, request, obj=None):
        fields = ["user"] if obj is not None and not self._can_set_user(request, obj) else []
        fields.append("terms_accepted")
        fields.append("person")
        return fields


admin.site.register(Person)


class ClerkEditLink(FieldAccessor):
    def __call__(self, obj):
        """
        :type obj: Clerk
        :return:
        """
        value = getattr(obj, self._field_name)
        info = obj._meta.app_label, obj._meta.model_name
        if obj.user is None:
            return escape(value)
        else:
            return format_html(
                u'<a href="{0}">{1}</a>',
                reverse("admin:%s_%s_change" % info, args=(obj.id,)),
                escape(value)
            )


_clerk_id_link = ClerkEditLink("id", ugettext("ID"))
_clerk_access_code_link = ClerkEditLink("access_code_str", ugettext("Access code"))


# noinspection PyMethodMayBeStatic
@admin.register(Clerk)
class ClerkAdmin(admin.ModelAdmin):
    uses_sso = settings.KIRPPU_USE_SSO  # Used by the overridden template.
    actions = ["_gen_clerk_code", "_del_clerk_code", "_move_clerk_code"]
    ordering = ("event", 'user__first_name', 'user__last_name')
    search_fields = ['user__first_name', 'user__last_name', 'user__username']
    exclude = ['access_key']
    list_filter = ("event",)
    list_display_links = None

    def get_list_display(self, request):
        if settings.DEBUG:
            return _clerk_id_link, _user_link, _clerk_access_code_link, 'access_key', 'is_enabled', 'event'
        else:
            return _clerk_id_link, _user_link, _clerk_access_code_link, 'is_enabled', 'event'

    @with_description(ugettext(u"Generate missing Clerk access codes"))
    def _gen_clerk_code(self, request, queryset):
        for clerk in queryset:
            if not clerk.is_valid_code:
                clerk.generate_access_key()
                clerk.save(update_fields=["access_key"])

    @with_description(ugettext(u"Delete Clerk access codes"))
    def _del_clerk_code(self, request, queryset):
        for clerk in queryset:
            while True:
                clerk.generate_access_key(disabled=True)
                try:
                    clerk.save(update_fields=["access_key"])
                except IntegrityError:
                    continue
                else:
                    break

    def _move_error(self, request, error):
        if error == "count":
            msg = ugettext(u"Must select exactly one 'unbound' and one 'bound' Clerk for this operation")
        elif error == "event":
            msg = ugettext("Must select unbound and bound rows from same Event")
        else:
            msg = "Unknown error key: " + error
        self.message_user(request, msg, messages.ERROR)

    @with_description(ugettext(u"Move unused access code to existing Clerk."))
    @transaction.atomic
    def _move_clerk_code(self, request, queryset):
        if len(queryset) != 2:
            self._move_error(request, "count")
            return

        # Guess the order.
        unbound = queryset[0]
        bound = queryset[1]
        if queryset[1].user is None:
            # Was wrong, swap around.
            bound, unbound = unbound, bound

        if unbound.user is not None or bound.user is None:
            # Selected wrong rows.
            self._move_error(request, "count")
            return

        if unbound.event != bound.event:
            # Must move inside same event.
            self._move_error(request, "event")
            return

        # Assign the new code to be used. Remove the unbound item first, so unique-check doesn't break.
        bound.access_key = unbound.access_key

        self.log_access_key_move(request, unbound, bound)
        unbound.delete()
        bound.save(update_fields=["access_key"])

        self.message_user(request, ugettext(u"Access code set for '{0}' in '{1}'").format(bound.user, bound.event.name))

    def get_form(self, request, obj=None, **kwargs):
        # Custom form for editing already created Clerks.
        if obj is not None:
            return ClerkEditForm

        return super(ClerkAdmin, self).get_form(request, obj, **kwargs)

    def has_change_permission(self, request, obj=None):
        # Don't allow changing unbound Clerks. That might create unusable codes (because they are not printed).
        if obj is not None and obj.user is None:
            return False
        return True

    def save_related(self, request, form, formsets, change):
        if isinstance(form, (ClerkEditForm, ClerkSSOForm)):
            # No related fields...
            return
        return super(ClerkAdmin, self).save_related(request, form, formsets, change)

    def save_model(self, request, obj, form, change):
        if change and isinstance(form, ClerkEditForm):
            # Need to save the form instead of obj.
            form.save()
        else:
            super(ClerkAdmin, self).save_model(request, obj, form, change)

    def get_urls(self):
        info = self.opts.app_label, self.opts.model_name
        return super(ClerkAdmin, self).get_urls() + [
            url(r'^add/bulk_unbound$', self.bulk_add_unbound, name="%s_%s_bulk" % info),
            url(r'^add/sso$', self.add_from_sso, name="%s_%s_sso" % info),
        ]

    def add_from_sso(self, request):
        if not self.has_add_permission(request) or not self.uses_sso:
            raise PermissionDenied

        form = get_form(ClerkSSOForm, request)  # type: ClerkSSOForm

        if request.method == 'POST' and form.is_valid():
            clerk = form.save()
            self.log_addition(request, clerk, {"added": {}})

            msg = format_html(
                ugettext("Clerk {name} added into {event}."),
                name=form.cleaned_data["user"],
                event=form.cleaned_data["event"],
            )
            self.message_user(request, msg, messages.SUCCESS)

            from django.http import HttpResponseRedirect
            return HttpResponseRedirect(reverse("admin:%s_%s_changelist" % (self.opts.app_label, self.opts.model_name)))

        return self._get_custom_form(request, form, ugettext('Add clerk from SSO provider'))

    def bulk_add_unbound(self, request):
        if not self.has_add_permission(request):
            raise PermissionDenied

        form = get_form(ClerkGenerationForm, request)

        if request.method == 'POST' and form.is_valid():
            objs = form.generate()
            self.log_bulk_addition(request, objs)

            msg = format_html(
                ngettext('One unbound clerk added.', '{count} unbound clerks added.', form.get_count()),
                count=form.get_count()
            )
            self.message_user(request, msg, messages.SUCCESS)

            from django.http import HttpResponseRedirect
            return HttpResponseRedirect(reverse("admin:%s_%s_changelist" % (self.opts.app_label, self.opts.model_name)))

        return self._get_custom_form(request, form, ugettext('Add unbound clerk'))

    def _get_custom_form(self, request, form, title):
        from django.contrib.admin.helpers import AdminForm, AdminErrorList
        admin_form = AdminForm(
            form,
            form.get_fieldsets(),
            {},
            model_admin=self)
        media = self.media + admin_form.media

        inline_formsets = []
        context = dict(
            self.admin_site.each_context(request),
            title=force_text(title),
            media=media,
            adminform=admin_form,
            is_popup=False,
            show_save_and_continue=False,
            inline_admin_formsets=inline_formsets,
            errors=AdminErrorList(form, inline_formsets),
        )

        return self.render_change_form(request, context, add=True)

    def log_bulk_addition(self, request, objects):
        # noinspection PyProtectedMember
        change_message = json.dumps([{
            'added': {
                'name': force_text(added_object._meta.verbose_name),
                'object': force_text(added_object),
            }
        } for added_object in objects])

        from .util import shorten_text
        object_repr = ", ".join([shorten_text(force_text(added_object), 5) for added_object in objects])

        return LogEntry.objects.create(
            user_id=request.user.pk,
            content_type_id=get_content_type_for_model(objects[0]).pk,
            object_repr=object_repr[:200],
            action_flag=ADDITION,
            change_message=change_message,
        )

    def log_access_key_move(self, request, unbound, target):
        # noinspection PyProtectedMember
        change_message = [{
            'changed': {
                'name': force_text(target._meta.verbose_name),
                'object': force_text(target),
                'fields': ["access_key"],
            },
            'deleted': {
                'name': force_text(unbound._meta.verbose_name),
                'object': force_text(unbound)
            }
        }]
        return LogEntry.objects.log_action(
            user_id=request.user.pk,
            content_type_id=get_content_type_for_model(target).pk,
            object_id=target.pk,
            object_repr=force_text(target),
            action_flag=CHANGE,
            change_message=change_message,
        )


@admin.register(Counter)
class CounterAdmin(admin.ModelAdmin):
    list_display = ("name", "identifier", "event")


admin.site.register(ReceiptExtraRow)


@admin.register(UIText)
class UITextAdmin(admin.ModelAdmin):
    model = UIText
    ordering = ["event", "identifier"]
    form = UITextForm
    list_display = ["identifier", "text_excerpt", "event"]
    list_filter = ("event",)


@admin.register(ItemType)
class ItemTypeAdmin(admin.ModelAdmin):
    ordering = ["event", "order"]
    list_display = ["title", "order", "event", "key"]
    list_editable = ["order"]
    list_filter = ("event",)
    list_display_links = ["title"]


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    @with_description(ugettext(u"Re-generate bar codes for items"))
    def _regen_barcode(self, request, queryset):
        for item in queryset:
            item.code = Item.gen_barcode()
            item.save(update_fields=["code"])

    def get_actions(self, request):
        s = super().get_actions(request)
        if settings.DEBUG:
            for f in [ItemAdmin._regen_barcode]:
                (func, name, desc) = self.get_action(f)
                s[name] = (func, name, desc)
        return s

    list_display = ('name', 'code', 'price', 'state', RefLinkAccessor('vendor', ugettext("Vendor")))
    ordering = ('vendor', 'name')
    search_fields = ['name', 'code']
    list_select_related = ("vendor", "vendor__user")
    list_filter = (
        "vendor__event",
        "state",
    )


class ReceiptItemAdmin(admin.TabularInline):
    model = ReceiptItem
    ordering = ["add_time"]
    readonly_fields = ["item", "price_str"]

    @with_description(Item._meta.get_field("price").name)
    def price_str(self, instance: ReceiptItem):
        return instance.item.price


class ReceiptExtraAdmin(admin.TabularInline):
    model = ReceiptExtraRow


class ReceiptNoteAdmin(admin.TabularInline):
    model = ReceiptNote
    ordering = ["timestamp"]
    readonly_fields = ["clerk", "text"]


@admin.register(Receipt)
class ReceiptAdmin(admin.ModelAdmin):
    inlines = [
        ReceiptItemAdmin,
        ReceiptExtraAdmin,
        ReceiptNoteAdmin,
    ]
    ordering = ["clerk", "-start_time"]
    list_display = ["__str__", "status", "total", "counter", "end_time"]
    list_filter = [
        ("type", admin.ChoicesFieldListFilter),
        "clerk",
        "counter",
        "status",
    ]
    search_fields = ["items__code", "items__name"]
    actions = ["re_calculate_total"]
    readonly_fields = ["start_time_str"]

    @with_description("Re-calculate total sum of receipt")
    def re_calculate_total(self, request, queryset):
        for i in queryset:  # type: Receipt
            i.calculate_total()
            i.save(update_fields=["total"])

    def has_delete_permission(self, request, obj=None):
        return False

    @with_description(Receipt._meta.get_field("start_time").name)
    def start_time_str(self, instance: Receipt):
        return str(instance.start_time)


@admin.register(ItemStateLog)
class ItemStateLogAdmin(admin.ModelAdmin):
    model = ItemStateLog
    ordering = ["-id"]
    search_fields = ['item__code', 'clerk__user__username']
    list_display = ['id', 'time',
                    RefLinkAccessor("item", ugettext("Item")),
                    'old_state', 'new_state',
                    RefLinkAccessor("clerk", ugettext("Clerk")),
                    'counter']
    list_select_related = (
        "clerk", "counter", "item", "clerk__user",
    )
    readonly_fields = ["time_str"]
    list_filter = (
        "old_state", "new_state", "clerk", "counter",
    )

    @with_description(ItemStateLog._meta.get_field("time").name)
    def time_str(self, instance: ItemStateLog):
        return str(instance.time)


class BoxItemAdmin(admin.TabularInline):
    model = Item
    exclude = ["name", "price", "type", "itemtype", "adult", "vendor"]
    readonly_fields = ["code", "state", "printed", "hidden", "abandoned", "lost_property"]
    can_delete = False
    extra = 0
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Box)
class BoxAdmin(admin.ModelAdmin):
    model = Box
    inlines = [
        BoxItemAdmin,
    ]
    readonly_fields = ['representative_item', 'get_item_type_for_display', 'get_item_adult_for_display', 'bundle_size']
    search_fields = ['box_number', 'description', 'representative_item__code']
    ordering = ['box_number']
    list_display = [
        'box_number',
        'description',
        'code',
        'get_price',
        'get_item_count',
        'bundle_size',
        RefLinkAccessor("get_vendor", ugettext("Vendor")),
    ]
    list_display_links = ['box_number', 'description']
    list_select_related = (
        "representative_item",
        "representative_item__vendor",
        "representative_item__vendor__event",
        "representative_item__vendor__user"
    )
    list_filter = (
        "representative_item__vendor__event",
    )


@admin.register(TemporaryAccessPermit)
class TemporaryAccessPermitAdmin(admin.ModelAdmin):
    model = TemporaryAccessPermit
    readonly_fields = ("vendor", "creator", "short_code")
    list_display = (
        "__str__",
        RefLinkAccessor("vendor", ugettext("Vendor")),
    )


@admin.register(TemporaryAccessPermitLog)
class TemporaryAccessPermitLogAdmin(admin.ModelAdmin):
    model = TemporaryAccessPermitLog
    readonly_fields = ("permit", "timestamp", "action", "address", "peer")
    list_display = (
        "__str__",
        RefLinkAccessor("permit", ugettext("Permit")),
        "timestamp",
        "action",
    )
