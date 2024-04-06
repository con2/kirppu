from __future__ import annotations

import typing
import re

import mistune


class MtToken(typing.TypedDict, total=False):
    type: typing.Required[str]
    raw: str
    attrs: dict[str, typing.Any]
    children: list[MtToken]


T = typing.TypeVar("T")


def remove_if_present(a_list: list[T], element: T):
    if element in a_list:
        a_list.remove(element)


def maybe_call(value):
    if callable(value):
        return value()
    return value


class BasePlugin:
    NAME: str

    def __call__(self, md: mistune.Markdown) -> None:
        raise NotImplementedError

    @staticmethod
    def render(renderer: mistune.BaseRenderer, *args, **kwargs) -> str:
        # Function signature varies, see mistune.renderers.html.HTMLRenderer.render_token
        raise NotImplementedError


class InlinePlugin(BasePlugin):
    def register_inline(
        self, md: mistune.Markdown, name: str, pattern: str, before: str = "inline_html"
    ) -> None:
        md.inline.register(name, pattern, self.parse, before=before)
        if md.renderer:
            md.renderer.register(name, self.render)

    @classmethod
    def parse(
        cls, inline: mistune.InlineParser, m: re.Match, state: mistune.InlineState
    ) -> int:
        raise NotImplementedError


class BlockPlugin(BasePlugin):
    def register_block(
        self, md: mistune.Markdown, name: str, pattern: str, before: str = "raw_html"
    ) -> None:
        md.block.register(name, pattern, self.parse, before=before)
        if md.renderer:
            md.renderer.register(name, self.render)

    @classmethod
    def parse(
        cls, block: mistune.BlockParser, m: re.Match, state: mistune.BlockState
    ) -> int:
        raise NotImplementedError
