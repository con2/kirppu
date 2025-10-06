import re
import typing

import mistune
from mistune import directives

from .base import InlinePlugin, MtToken, maybe_call


class VarPlugin(InlinePlugin):
    NAME = "var"

    def __init__(self, variables: dict[str, str | typing.Callable[[], str]]):
        self._variables = variables

    def __call__(self, md: mistune.Markdown) -> None:
        self.register_inline(md, self.NAME, r"<var\s+(?P<var_name>[\w._-]+)\s*/>")

    @classmethod
    def parse(
        cls, inline: mistune.InlineParser, m: re.Match, state: mistune.InlineState
    ) -> int:
        var_name = m.group("var_name")
        state.append_token(
            MtToken(
                type=cls.NAME,
                attrs={"var_name": var_name, "src": f"<var {var_name}/>"},
            )
        )
        return m.end()

    # noinspection PyMethodOverriding
    def render(self, renderer: mistune.BaseRenderer, var_name: str, **kwargs) -> str:
        result = ""
        if var_name in self._variables:
            value = self._variables[var_name]
            result = maybe_call(value)

        return result


class VarSetterPlugin(directives.DirectivePlugin):
    NAME = "vars"

    def __init__(self, variables: dict[str, str | typing.Callable[[], str]]):
        super().__init__()
        self._variables = variables

    # noinspection PyMethodOverriding
    def __call__(self, directive, md: mistune.Markdown) -> None:
        directive.register(self.NAME, self.parse)
        if md.renderer:
            md.renderer.register(self.NAME, self.render)

    # Overrides, but is called via registered _methods instead of base class.
    def parse(self, block: mistune.BlockParser, m, state: mistune.BlockState) -> MtToken:
        options = self.parse_options(m)
        for key, value in options:
            self._variables[key] = value
        return MtToken(type=self.NAME)

    @staticmethod
    def render(renderer: mistune.BaseRenderer) -> str:
        return ""
