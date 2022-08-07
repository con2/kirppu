# -*- coding: utf-8 -*-

import base64
import itertools
import re
import typing

import mistune
from django.template import loader
from django.template.context import Context, RequestContext


__all__ = [
    "mark_down",
]


# Also check customtexts_front.js that does the reverse with these.
EMAIL_CLASS = "yv8k02zi"
EMAIL_KEY = "yJrx6Rvvyn39u4La"


def insert_before_or_append(the_list: typing.List[str], before: str, item: str):
    i = the_list.index(before)
    if i >= 0:
        the_list.insert(i, item)
    else:
        the_list.append(item)


def kirppu_plugin(md: mistune.Markdown):
    md.inline.register_rule("email", r"<email>\s*([^<]*)\s*</email>", _make_email)
    insert_before_or_append(md.inline.rules, "inline_html", "email")

    md.inline.register_rule("glyph", r"<glyph \s*([\w-]+)\s*/>", _make_glyph)
    insert_before_or_append(md.inline.rules, "inline_html", "glyph")

    # register_rule makes wrong kind of lambda for _start rules.
    md.block.rule_methods["alertbox_start"] = (
        re.compile(r"<alertbox \s*(\w+)\s*>"),
        lambda m, state, string: _make_alertbox(md.block, m, state, string)
    )
    insert_before_or_append(md.block.rules, "block_html", "alertbox_start")

    md.block.register_rule("template", re.compile(r"<itemlist\s*/>"), _make_itemlist)
    insert_before_or_append(md.block.rules, "block_html", "template")


def _make_email(inline, m, state):
    return "email", m.group(1)


def _make_glyph(inline, m, state):
    return "glyph", m.group(1)


def _make_itemlist(block, m, state):
    return {
        "type": "template",
        "text": "",
        "params": ("kirppu/vendor_item_list.html",),
    }


def _make_alertbox(block, m, state, string: str):
    end_tag = "</alertbox>"
    block_end = string.find(end_tag, m.end())
    box_type = m.group(1)

    valid_types = {
        "success",
        "info",
        "warning",
        "danger"
    }
    if box_type not in valid_types:
        raise ValueError(
            "Invalid argument to alertbox: \"" + box_type + "\". Must have a single argument, any of: " + ", ".join(
                valid_types)
        )

    text = string[m.end():block_end]
    token = {
        "type": "alertbox",
        "params": (box_type,),
        "text": text,
    }
    return token, block_end + len(end_tag)


class CustomTagRenderer(mistune.HTMLRenderer):
    def __init__(self, context: typing.Optional[typing.Union[RequestContext, Context]]):
        super().__init__()
        self._context = context

    @staticmethod
    def email(address):
        enc = bytes(
            ord(a) ^ ord(k)
            for a, k in zip(address.replace("@", " <em>at</em> "), itertools.cycle(EMAIL_KEY))
        )
        safe = base64.b64encode(enc).decode().rstrip("=")
        html = '<code class="%s">' % EMAIL_CLASS + safe + "</code>"
        return html

    @staticmethod
    def glyph(glyph):
        html = '<span class="glyphicon glyphicon-%s"> </span>' % glyph
        return html

    @staticmethod
    def alertbox(text, box_type):
        html = '<div class="alert alert-%s" role="alert">' % box_type
        html += text + "</div>"
        return html

    def template(self, text, template_name):
        if self._context is None:
            import warnings
            warnings.warn("No context when trying to render a template %s" % template_name)
        context = self._context if self._context is None or isinstance(self._context, dict) else self._context.flatten()
        return loader.render_to_string(template_name, context)


def mark_down(text, context: typing.Optional[typing.Union[RequestContext, Context]] = None):
    m = mistune.create_markdown(
        escape=False,
        renderer=CustomTagRenderer(context),
        plugins=[
            'strikethrough',
            'footnotes',
            'table',
            kirppu_plugin,
        ],
    )
    return m(text)


def main():
    text = """
# Heading

## Subheading

### Sub-subheading

- Un-ordered list item
  - Sub-item

1. Ordered list item

*emphasis*

**strong**

[Link title](https://...)

Email address: <email>email@example.org</email>

A glyph: <glyph volume-off />

<alertbox danger>Alert text content</alertbox>
    """
    print(mark_down(text))


if __name__ == '__main__':
    main()
