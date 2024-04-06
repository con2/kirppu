import base64
import itertools
import re

import mistune

from .base import InlinePlugin, MtToken

# Also check customtexts_front.js that does the reverse with these.
EMAIL_CLASS = "yv8k02zi"
EMAIL_KEY = "yJrx6Rvvyn39u4La"


class EmailPlugin(InlinePlugin):
    NAME = "email"

    def __call__(self, md: mistune.Markdown):
        self.register_inline(
            md, self.NAME, r"<email>\s*(?P<email_text>[^<]*)\s*</email>"
        )

    @classmethod
    def parse(
        cls, inline: mistune.InlineParser, m: re.Match, state: mistune.InlineState
    ) -> int:
        state.append_token(MtToken(type=cls.NAME, raw=m.group("email_text")))
        return m.end()

    # noinspection PyMethodOverriding
    @staticmethod
    def render(renderer: mistune.BaseRenderer, address: str) -> str:
        enc = bytes(
            ord(a) ^ ord(k)
            for a, k in zip(
                address.replace("@", " <em>at</em> "), itertools.cycle(EMAIL_KEY)
            )
        )
        safe = base64.b64encode(enc).decode().rstrip("=")
        html = '<code class="%s">' % EMAIL_CLASS + safe + "</code>"
        return html


class GlyphPlugin(InlinePlugin):
    NAME = "glyph"

    def __call__(self, md: mistune.Markdown):
        self.register_inline(md, self.NAME, r"<glyph \s*(?P<glyph_name>[\w-]+)\s*/>")

    @classmethod
    def parse(
        cls, inline: mistune.InlineParser, m: re.Match, state: mistune.InlineState
    ) -> int:
        state.append_token(MtToken(type=cls.NAME, raw=m.group("glyph_name")))
        return m.end()

    # noinspection PyMethodOverriding
    @staticmethod
    def render(renderer: mistune.BaseRenderer, glyph: str) -> str:
        html = '<span class="glyphicon glyphicon-%s"> </span>' % glyph
        return html
