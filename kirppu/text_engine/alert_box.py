import re

import mistune

from .base import BlockPlugin, MtToken, remove_if_present
from .template import TemplatePlugin


class AlertBoxPlugin(BlockPlugin):
    NAME = "alert_box"

    ALERT_TYPES = {
        "success",
        "info",
        "warning",
        "danger",
    }

    def __call__(self, md: mistune.Markdown):
        self.register_block(
            md,
            self.NAME,
            r"<alertbox\s+(?P<alert_type>\w+)\s*>"
            r"(?P<alert_text>[\s\S]*?)"
            r"</alertbox>",
            before="raw_html",
        )

    @classmethod
    def parse(
        cls, block: mistune.BlockParser, m: re.Match, state: mistune.BlockState
    ) -> int:
        alert_box_type = m.group("alert_type")

        if alert_box_type not in cls.ALERT_TYPES:
            box_type_error = (
                f'Invalid argument to alertbox: "{alert_box_type}".'
                " Must have a single argument, any of: " + ", ".join(cls.ALERT_TYPES)
            )
            raise ValueError(box_type_error)

        text = m.group("alert_text")

        child_state = state.child_state(text)
        rules: list[str] = list(block.rules)
        rules.remove(cls.NAME)
        remove_if_present(rules, TemplatePlugin.NAME)
        block.parse(child_state, rules)

        token = MtToken(
            type=cls.NAME,
            attrs={"alert_box_type": alert_box_type},
            children=child_state.tokens,
        )

        state.append_token(token)
        return m.end() + 1

    # noinspection PyMethodOverriding
    @staticmethod
    def render(renderer: mistune.BaseRenderer, text: str, alert_box_type: str) -> str:
        html = '<div class="alert alert-%s" role="alert">' % alert_box_type
        html += text + "</div>"
        return html
