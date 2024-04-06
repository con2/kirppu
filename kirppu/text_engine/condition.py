import decimal
import operator
import re
import typing

import mistune

from .base import InlinePlugin, MtToken, maybe_call
from kirppu.provision_dsl.interpreter import tokenize, Symbol, Token


class ConditionPlugin(InlinePlugin):
    NAME = "if"
    ELIF = r"<\s*elif\s*(?P<elif_condition>[\w_. ()!=-]+)\s*>(?P<elif_body>[\s\S]*?)"

    class Condition(typing.TypedDict, total=False):
        condition: list[str] | bool
        body: list[dict[str, typing.Any]]

    def __init__(self, variables: dict[str, str | typing.Callable[[], str]]):
        self._variables = variables
        self._env: dict[str, str | callable] = {
            "=": operator.eq,
            "le": operator.le,
            "lt": operator.gt,
            "ge": operator.ge,
            "gt": operator.gt,
            "!": operator.ne,
            "not": operator.not_,
            "and": lambda *a: operator.and_(*(bool(e) for e in a)),
            "or": lambda *a: operator.or_(*(bool(e) for e in a)),
        }

    def __call__(self, md: mistune.Markdown) -> None:
        self.register_inline(
            md,
            self.NAME,
            r"<\s*if\s+(?P<condition>[\w_. ()!=-]+)\s*>"
            r"(?P<body>[\s\S]*?)"
            r"(?P<elif_group>(?:" + self.ELIF + ")*)"
            r"(?:<\s*else\s*>(?P<false_body>[\s\S]*?))?"
            r"</if\s*>",
        )

    @staticmethod
    def _eval_children(inline, state, body) -> list[dict[str, typing.Any]]:
        child_state = state.copy()
        child_state.src = body
        return inline.render(child_state)

    @classmethod
    def parse(
        cls, inline: mistune.InlineParser, m: re.Match, state: mistune.InlineState
    ) -> int:
        body = m.group("body")
        false_body = m.group("false_body")

        primary_condition_str = m.group("condition")
        primary_program = tokenize(primary_condition_str)
        primary_children = cls._eval_children(inline, state, body)
        cases: list[cls.Condition] = [
            cls.Condition(condition=primary_program, body=primary_children),
        ]

        elifs = m.group("elif_group")
        if elifs:
            prev = 0
            # This doesn't match the body properly, so we'll complete a case when processing the next.
            for match in re.finditer(cls.ELIF, elifs):
                if prev != 0:
                    # Add body to the previous case.
                    body = elifs[prev : match.start()]
                    cases[-1]["body"] = cls._eval_children(inline, state, body)

                prev = match.start("elif_body")
                cases.append(
                    cls.Condition(condition=tokenize(match.group("elif_condition")))
                )

            if prev != 0:
                # Add body to last case.
                body = elifs[prev:]
                cases[-1]["body"] = cls._eval_children(inline, state, body)

        if false_body:
            cases.append(
                cls.Condition(
                    condition=False, body=cls._eval_children(inline, state, false_body)
                )
            )

        token = MtToken(
            type=cls.NAME,
            attrs={"cases": cases},
        )

        state.append_token(token)
        return m.end()

    # noinspection PyMethodOverriding
    def render(self, renderer: mistune.BaseRenderer, cases: list[Condition]) -> str:
        env = self._env.copy()
        env.update(self._variables)
        for cond in cases:
            program = cond["condition"]
            if program is not False:
                # <if ...>
                # <elif ...>
                stream = next(self.read_from_tokens(program))
                result = self.evaluate(stream, env)
                if result:
                    return renderer.render_tokens(cond["body"], None)
            else:
                # <else>
                return renderer.render_tokens(cond["body"], None)
        # no matching case
        return ""

    @classmethod
    def read_from_tokens(
        cls, tokens: typing.Iterator[str] | list[str]
    ) -> typing.Iterator[Token]:
        if isinstance(tokens, list):
            tokens = iter(tokens)
        token = next(tokens)
        while token != ")":
            if token == "(":
                yield [token for token in cls.read_from_tokens(tokens)]
            else:
                yield cls.atomize(token)
            token = next(tokens)

    @staticmethod
    def atomize(token: str) -> Symbol | decimal.Decimal:
        if token.isdigit():
            try:
                return decimal.Decimal(token)
            except decimal.InvalidOperation:
                return Symbol(token)
        return Symbol(token)

    @classmethod
    def evaluate(cls, x: list[Token] | Token, env: dict[str, typing.Any]):
        if isinstance(x, Symbol):
            return env.get(x)
        elif isinstance(x, decimal.Decimal):
            return x
        elif len(x) == 0:
            return None
        try:
            proc = cls.evaluate(x[0], env)
            args = [maybe_call(cls.evaluate(arg, env)) for arg in x[1:]]
            return proc(*args)
        except:
            return ""
