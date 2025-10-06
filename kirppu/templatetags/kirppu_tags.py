from functools import lru_cache
import datetime
import json
import re
import typing
import warnings

from django import template
from django.conf import settings
from django.utils.html import format_html
from django.utils.safestring import mark_safe

import pubcode
from ..models import Event, Item, RemoteEvent, UIText, UserAdapter
from ..text_engine import mark_down

register = template.Library()


def _get_ui_text_query(context, id_):
    event = context["event"]  # type: Event
    source_event = context.get("source_event")  # type: typing.Union[Event, RemoteEvent]
    if source_event is None:
        warnings.warn("Missing source_event value when getting text " + id_)
        source_event = event
    database = source_event.get_real_database_alias()
    return UIText.objects.using(database).filter(event=source_event)


@register.simple_tag(takes_context=True)
def load_text(context: template.Context, id_: str) -> str:
    q = {"identifier": id_}
    previews = context.get("allow_preview", False)
    extra_context = {}
    if previews:
        preview_id = context["request"].GET.get("preview")
        if preview_id:
            q = {"pk": int(preview_id)}
            extra_context["colorize"] = True
    try:
        with context.update(extra_context):
            md = _get_ui_text_query(context, id_).get(**q).text
            return mark_safe(mark_down(md, context))
    except UIText.DoesNotExist:
        if settings.DEBUG:
            return format_html(
                '<span style="background-color: lightyellow;'
                ' color: black;'
                ' border: 1px solid gray;">'
                'Missing text {0}.</span>',
                id_
            )
        return ""


@register.simple_tag(takes_context=True)
def load_texts(context: template.Context, id_: str) -> str:
    """
    Output multiple UIText values. If id is not found, only empty string is returned.

    :param context: (Context supplied by Django)
    :param id_: Start of id string to find.
    """
    texts = (
        _get_ui_text_query(context, id_)
        .filter(identifier__startswith=id_)
        .order_by("identifier")
        .values_list("text", flat=True)
    )
    if not texts:
        return ""

    return mark_safe("".join(mark_down(text, context) for text in texts))


# Limit the size of the dict to a reasonable number so that we don't have
# millions of dataurls cached.
@lru_cache(maxsize=50000)
def get_dataurl(code, ext, expect_width=143):
    if not code:
        return ''

    # Code the barcode entirely with charset B to make sure that the bacode is
    # always the same width.
    barcode = pubcode.Code128(code, charset='B')
    data_url = barcode.data_url(image_format=ext, add_quiet_zone=True)

    # These measurements have to be exactly the same as the ones used in
    # price_tags.css. If they are not the image might be distorted enough
    # to not register on the scanner.
    assert(expect_width is None or barcode.width(add_quiet_zone=True) == expect_width)

    return data_url


@register.simple_tag
def barcode_dataurl(code, ext, expect_width=143):
    return get_dataurl(code, ext, expect_width)


@register.simple_tag
def barcode_css(
        low: int = 4, high: int = 6,
        target: typing.Optional[str] = None, container: typing.Optional[str] = None,
        compress: bool = False) -> str:
    """
    Generate CSS rules for various sizes of barcodes when using Code128.
    Expected DOM hierarchy:

       div class=container_{0}
          img class=target_{0}

    :param low: Minimum length of the code.
    :param high: Maximum length of the code.
    :param target: CSS selector for the img, having `{0}` in the img class.
    :param container: CSS selector for container of the img, having `{0}` in the container class.
    :param compress: Remove spaces from the result?
    :return: CSS string.
    """
    target = target or ".barcode_img.barcode_img{0}"
    container = container or ".barcode_container.barcode_container{0}"

    css = """
        {target}, {container} {{
            width: {px}px;
            background-color: white;
        }}
"""

    def gen():
        for code_length in range(low, high + 1):
            example_code = pubcode.Code128('A' * code_length, charset='B')
            px = example_code.width(add_quiet_zone=True)

            for multiplier in range(1, 3):
                suffix = "_" + str(code_length) + "_" + str(multiplier)
                mpx = px * multiplier
                rule = css.format(
                    target=target.format(suffix),
                    container=container.format(suffix),
                    px=mpx,
                )
                if compress:
                    rule = re.sub(r'\s+', "", rule)
                yield rule
    return "".join(gen())


@register.filter
def user_adapter(user, getter: str):
    """
    Filter for using UserAdapter for user objects.

    :param user: User to filter, class of `settings.USER_MODEL`.
    :param getter: Getter function to apply to the user via adapter.
    """
    if not isinstance(getter, str) or getter.startswith("_"):
        raise AttributeError("Invalid adapter attribute.")

    getter = getattr(UserAdapter, getter)
    return getter(user)


# https://djangosnippets.org/snippets/660/
class SplitListNode(template.Node):
    def __init__(self, list_string, chunk_size, new_list_name):
        self.list = list_string
        self.chunk_size = chunk_size
        self.new_list_name = new_list_name

    @staticmethod
    def split_seq(seq, size):
        """ Split up seq in pieces of size, from
        http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/425044"""
        return [seq[i:i+size] for i in range(0, len(seq), size)]

    def render(self, context):
        context[self.new_list_name] = self.split_seq(context[self.list], int(self.chunk_size))
        return ''


def split_list(parser, token):
    """<% split_list list as new_list 5 %>"""
    bits = token.contents.split()
    if len(bits) != 5:
        raise template.TemplateSyntaxError("split_list list as new_list 5")
    return SplitListNode(bits[1], bits[4], bits[3])

split_list = register.tag(split_list)


# From django.utils.html
_json_script_escapes = {
    ord('>'): '\\u003E',
    ord('<'): '\\u003C',
    ord('&'): '\\u0026',
}


@register.filter("json")
def as_json(obj):
    from django.core.serializers.json import DjangoJSONEncoder
    json_str = json.dumps(obj, separators=(",", ":"), cls=DjangoJSONEncoder).translate(_json_script_escapes)
    return mark_safe(json_str)


@register.filter
def format_price(value, format_type="raw"):
    return "{}{}{}".format(
        settings.KIRPPU_CURRENCY[format_type][0],
        str(value),
        settings.KIRPPU_CURRENCY[format_type][1]
    )


@register.filter
def quantize_price(value):
    return Item.price_fmt_for(value)


@register.filter("isInPastDays")
def is_in_past_days(date: datetime.date, days: int) -> bool:
    # XXX: In near past, or in the future.
    now = datetime.date.today()
    diff = datetime.timedelta(days=days)
    return date + diff >= now


@register.filter("replaceCurrency")
def replace_one(value: str) -> str:
    pre, post = settings.KIRPPU_CURRENCY["raw"]
    pre = pre.strip(" \t\n\u00a0")
    post = post.strip(" \t\n\u00a0")
    if post:
        replacement = post
    else:
        replacement = pre
    return value.replace("%s", replacement)
