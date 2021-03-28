from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from .fields import ItemPriceField, SuffixField, StripField
from .models import (
    Clerk,
    Event,
    ReceiptItem,
    Receipt,
    Item,
    ItemType,
    UIText,
    Vendor,
    Person,
    ItemStateLog,
)
from .util import shorten_text
from .utils import StaticText, ButtonWidget, model_dict_fn


class ClerkGenerationForm(forms.Form):
    event = forms.ModelChoiceField(Event.objects.all())
    count = forms.IntegerField(
        min_value=0,
        initial=1,
        help_text=u"Count of empty Clerks to generate")

    def __init__(self, *args, **kwargs):
        super(ClerkGenerationForm, self).__init__(*args, **kwargs)

    def get_fieldsets(self):
        return [(None, {'fields': self.base_fields})]

    def generate(self, commit=True):
        return Clerk.generate_empty_clerks(self.get_event(), self.get_count(), commit=commit)

    def get_event(self):
        return self.cleaned_data["event"]

    def get_count(self):
        return self.cleaned_data["count"]


class ClerkSSOForm(forms.ModelForm):
    user = forms.CharField(
        max_length=30,
        validators=[
            AbstractUser.username_validator
        ],
        label=_("Username"),
    )

    def __init__(self, *args, **kwargs):
        super(ClerkSSOForm, self).__init__(*args, **kwargs)
        self._sso_user = None

    def get_fieldsets(self):
        return [(None, {'fields': self.base_fields})]

    def clean(self):
        cleaned_data = super().clean()
        username = cleaned_data["user"]
        event = cleaned_data["event"]
        user = get_user_model().objects.filter(username=username)
        if len(user) > 0:
            clerk = Clerk.objects.filter(user=user[0], event=event)
            if len(clerk) > 0:
                raise forms.ValidationError("Clerk {username} already exists for event {event}.".format(
                    **locals())
                )

        from kompassi_crowd.kompassi_client import KompassiError, kompassi_get
        try:
            self._sso_user = kompassi_get('people', username)
        except KompassiError as e:
            raise forms.ValidationError(u'Failed to get Kompassi user {username}: {e}'.format(
                username=username, e=e)
            )

        return cleaned_data

    def save(self, commit=True):
        event = self.cleaned_data["event"]
        username = self.cleaned_data["user"]
        user = get_user_model().objects.filter(username=username)
        if len(user) > 0 and user[0].password != "":
            clerk = Clerk(user=user[0])
            if commit:
                clerk.save()
            return clerk

        from kompassi_crowd.kompassi_client import user_defaults_from_kompassi
        user, created = get_user_model().objects.get_or_create(
            username=username,
            defaults=user_defaults_from_kompassi(self._sso_user)
        )

        clerk = Clerk(event=event, user=user)
        if commit:
            clerk.save()
        return clerk

    class Meta:
        model = Clerk
        exclude = ("user", "access_key")


class ClerkEditForm(forms.ModelForm):
    """
        Edit form for Clerks in Admin-site.
        Does not allow editing user or access_key, but access_key is updated based on
        selection of disabled and regen_code fields.
    """
    user = forms.CharField(
        widget=forms.TextInput(attrs=dict(readonly="readonly", size=60)),
        help_text=u"Read only",
    )
    access_key = forms.CharField(
        widget=forms.TextInput(attrs=dict(readonly="readonly", size=60)),
        help_text=u"Read only",
    )
    disabled = forms.BooleanField(
        required=False,
        label=_("Disabled"),
        help_text=_("Clerk will be disabled or enabled on save."),
    )
    regen_code = forms.BooleanField(
        required=False,
        label=_("Regenerate access code"),
        help_text=_("Enabled Clerk access code will be randomized on save."),
    )
    change_code = forms.ModelChoiceField(
        queryset=Clerk.objects.filter(user__isnull=True),
        label=_("Change access code"),
        help_text=_("Clerk access code will be changed to this on save."),
        required=False,
    )

    def __init__(self, *args, **kwargs):
        instance = kwargs["instance"]
        """:type: Clerk"""

        self._access_key = instance.access_key
        self._disabled = not instance.is_valid_code
        if instance.user is not None:
            user = u"{0} (id={1})".format(str(instance.user.username), instance.user.id)
        else:
            user = u"<Unbound>"

        kwargs["initial"] = dict(
            user=user,
            access_key=u"{0} (raw={1})".format(instance.access_code, instance.access_key).strip(),
            disabled=self._disabled,
        )
        super(ClerkEditForm, self).__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super(ClerkEditForm, self).clean()
        is_disabled = cleaned_data["disabled"]
        is_regen_code = cleaned_data["regen_code"]
        is_change_code = cleaned_data["change_code"]
        msg = None

        labels = {
            "disabled": self.fields["disabled"].label,
            "regen": self.fields["regen_code"].label,
            "change": self.fields["change_code"].label,
        }

        msg_template = _('Either "%(0)s" or "%(1)s" must be cleared.')

        def _map(*args):
            return {str(i): v for i, v in enumerate(args)}

        if is_disabled and is_change_code:
            msg = ValidationError(msg_template,
                                  params=_map(labels["disabled"], labels["change"]),
                                  code="set_disabled_and_change_code")
            self.add_error("disabled", msg)
            self.add_error("change_code", msg)

        if is_regen_code and is_change_code:
            msg = ValidationError(msg_template,
                                  params=_map(labels["regen"], labels["change"]),
                                  code="regenerate_and_change_code")
            self.add_error("regen_code", msg)
            self.add_error("change_code", msg)

        if is_regen_code and is_disabled:
            msg = ValidationError(msg_template,
                                  params=_map(labels["disabled"], labels["regen"]),
                                  code="set_disabled_and_regenerate_code")
            self.add_error("disabled", msg)
            self.add_error("regen_code", msg)

        if msg is not None:
            raise ValidationError(_("Only one option may be selected at a time."),
                                  code="operation_conflict")

        return cleaned_data

    def save(self, commit=True):
        # Save only if disabled has changed.

        disabled = self.cleaned_data["disabled"]
        regen = self.cleaned_data["regen_code"]
        change = self.cleaned_data["change_code"]
        if disabled and self._disabled == disabled and self.instance.access_key is not None:
            # Do nothing if setting disabled to a clerk that is disabled (but not None).
            return self.instance
        elif self._disabled == disabled and not regen and not change:
            # Do nothing if not changing disabled and there is no other operation too.
            return self.instance

        if change:
            self.instance.access_key = change.access_key
            if commit:
                change.delete()
        else:
            self.instance.generate_access_key(disabled=disabled)

        if commit:
            self.instance.save()
        return self.instance

    @property
    def changed_data(self):
        """Overridden function to create a little more descriptive log info into admin log."""

        disabled = self.cleaned_data["disabled"]
        if disabled == self._disabled:
            if self.instance.access_key == self._access_key:
                return []
            else:
                return ["access_key"]
        if disabled:
            return ["setDisabled"]
        return ["setEnabled"]

    class Meta:
        model = Clerk
        # Exclude model functionality for these fields.
        exclude = ("user", "access_key")


class UITextForm(forms.ModelForm):
    class Meta:
        model = UIText
        fields = "__all__"
        widgets = {
            "text": forms.Textarea(attrs={"cols": 100}),
        }

    format_help = StaticText(
        label=_("Text formatting"),
        text=_("""<div style="float: left;">The text is formatted with standard Markdown syntax. Quick reference:<br/>
# Heading<br/>
## Subheading<br/>
### Sub-subheading<br/>
- Un-ordered list item<br/>
1. Ordered list item<br/>
*<em>text</em>*<br/>
**<strong>text</strong>**<br/>
[<em>Link title</em>](<em>https://...</em>)<br/>
&lt;email&gt;<em>email@address.org</em>&lt;/email&gt;<br/>
&lt;glyph <em>glyph-name</em> /&gt;<br/>
&lt;alertbox <em>type</em>&gt;<em>alert text content</em>&lt;/alertbox&gt; Types: danger, warning, info, success<br/>
&lt;itemlist /&gt;
</div>""")
    )

    def clean_text(self):
        data = self.cleaned_data["text"]
        try:
            from .text_engine import mark_down
            mark_down(data)
        except ValueError as e:
            raise ValidationError(e.args[0])
        return data


class ItemRemoveForm(forms.Form):
    receipt = forms.IntegerField(min_value=0, label=u"Receipt ID")
    code = forms.CharField(label=u"Item code")

    def __init__(self, *args, event, **kwargs):
        self._event = event
        super(ItemRemoveForm, self).__init__(*args, **kwargs)

    def clean_receipt(self):
        data = self.cleaned_data["receipt"]
        if not Receipt.objects.filter(pk=data).exists():
            raise forms.ValidationError(u"Receipt {pk} not found.".format(pk=data))
        return data

    def clean_item(self):
        data = self.cleaned_data["code"]
        if not Item.objects.filter(code=data, vendor__event=self._event).exists():
            raise forms.ValidationError(u"Item with code {code} not found.".format(code=data))
        return data


@transaction.atomic
def remove_item_from_receipt(request, item_or_code, receipt_id, update_receipt=True):
    if isinstance(item_or_code, Item):
        item = item_or_code
    else:
        item = Item.objects.select_for_update().get(code=item_or_code)

    if item.state not in (Item.SOLD, Item.STAGED):
        raise ValueError("Item is not sold or staged, but {}".format(item.state))

    if isinstance(receipt_id, Receipt):
        receipt = receipt_id
        assert receipt.type == Receipt.TYPE_PURCHASE, "This function cannot be used for non-purchase receipts."
    else:
        receipt = Receipt.objects.select_for_update().get(pk=receipt_id, type=Receipt.TYPE_PURCHASE)
        assert update_receipt, "Receipt must be updated if accessed by id."

    last_added_item = ReceiptItem.objects \
        .filter(receipt=receipt, item=item, action=ReceiptItem.ADD) \
        .select_for_update() \
        .order_by("-add_time")

    if len(last_added_item) == 0:
        raise ValueError("Item {} is not added to receipt.".format(item))
    assert len(last_added_item) == 1, "Receipt content conflict."

    last_added_item = last_added_item[0]
    last_added_item.action = ReceiptItem.REMOVED_LATER
    last_added_item.save(update_fields=("action",))

    removal_entry = ReceiptItem(item=item, receipt=receipt, action=ReceiptItem.REMOVE)
    removal_entry.save()

    if update_receipt:
        receipt.calculate_total()
        receipt.save(update_fields=("total",))

    if item.state != Item.BROUGHT:
        ItemStateLog.objects.log_state(item=item, new_state=Item.BROUGHT, request=request)
        item.state = Item.BROUGHT
        item.save(update_fields=("state",))
    return removal_entry


class VendorSetSelfForm(forms.ModelForm):

    set_user = StaticText(
        u"Set self as this user.",
        label="",
        widget=ButtonWidget,
    )
    username = forms.CharField(
        widget=forms.TextInput(attrs={'readonly': 'readonly'}),
    )

    def __init__(self, *args, **kwargs):
        instance = kwargs.get("instance", None)
        """:type: Vendor"""

        kwargs["initial"] = {
            "username": instance.user.username,
        }

        super(VendorSetSelfForm, self).__init__(*args, **kwargs)

        from django.urls import reverse
        url = reverse("kirppuauth:local_admin_login")
        click = u"""document.forms[0].action='{0}'; document.forms[0].submit();""".format(url)
        self.fields["set_user"].widget.set_click(click)

    class Meta:
        model = Vendor
        fields = ()


class VendorItemForm(forms.Form):
    name = StripField(error_messages={"required": _("Name is required.")}, max_length=256)
    price = ItemPriceField()
    tag_type = forms.ChoiceField(
        required=False,
        choices=[i for i in Item.TYPE if i != "long"],
    )
    suffixes = SuffixField()
    item_type = forms.ChoiceField(
        error_messages={
            "required": _(u"Item must have a type."),
            "invalid_choice": _(u"Invalid item type.")
        }
    )
    adult = forms.BooleanField(required=False)

    def __init__(self, data, event):
        super().__init__(data)
        self.fields["item_type"].choices = ItemType.as_tuple(event)
        self._event = event

    def get_any_error(self):
        errors = self.errors.as_data()
        keys = errors.keys()
        if len(keys) == 0:
            return None
        some_error = errors[list(keys)[0]]
        return u" ".join([u" ".join(error.messages) for error in some_error])

    def clean_tag_type(self):
        value = self.cleaned_data["tag_type"]
        if not value:
            return Item.TYPE_SHORT
        return value

    def clean_item_type(self):
        value = int(self.cleaned_data["item_type"])
        return ItemType.objects.get(id=value, event=self._event)

    db_values = model_dict_fn(
        "name",
        type="tag_type",
        itemtype="item_type",
        adult=lambda self: "yes" if self.cleaned_data["adult"] else "no",
        price=lambda self: str(self.cleaned_data["price"]),
        __access_fn=lambda self, value: self.cleaned_data[value],
    )


class VendorBoxForm(VendorItemForm):
    description = StripField(max_length=256)
    name = None
    tag_type = None
    suffixes = None
    count = forms.IntegerField(min_value=1)
    bundle_size = forms.IntegerField(min_value=1)

    db_values = model_dict_fn(
        "description",
        "count",
        "bundle_size",
        type=None,
        name=lambda self: shorten_text(self.cleaned_data["description"], 32),
        __extend=VendorItemForm.db_values,
        __access_fn=lambda self, value: self.cleaned_data[value],
    )


class PersonCreationForm(forms.ModelForm):
    class Meta:
        model = Person
        fields = forms.ALL_FIELDS
