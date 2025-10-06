from __future__ import annotations
import html
import typing

if typing.TYPE_CHECKING:
    from .base import BasePlugin


class Colorizer:
    COLORS = (
        "#ffff7f",
        "#bbff7f",
        "#7fffbb",
        "#7fffff",
        "#aaaaff",
        "#ff7fff",
        "#ffaaaa",
    )

    def __init__(self):
        self._pos = 0

    def __call__(self, text: str, kwargs) -> str:
        color = self.COLORS[self._pos]
        self._pos = (self._pos + 1) % len(self.COLORS)
        src = html.escape(kwargs.get("src", ""))
        return f'<span class="placeholder-hl" style="background-color:{color};" title="{src}">{text}</span>'

    def wraps(self, plugin: BasePlugin):
        original = plugin.render

        def wrapper(*args, **kwargs):
            text = original(*args, **kwargs)
            if not text:
                return ""
            return self(text, kwargs)

        plugin.render = wrapper
        return plugin
