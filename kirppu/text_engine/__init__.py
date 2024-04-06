import mistune
from mistune import directives
from django.template.context import Context, RequestContext

from .alert_box import AlertBoxPlugin
from .condition import ConditionPlugin
from .monolithic import EmailPlugin, GlyphPlugin
from .template import TemplatePlugin
from .variables import VarPlugin, VarSetterPlugin

__all__ = [
    "mark_down",
]


def mark_down(text, context: RequestContext | Context | dict | None = None, renderer="html") -> str | list[dict]:
    if context:
        text_vars = context.get("uiTextVars", {})
    else:
        text_vars = {}

    m = mistune.create_markdown(
        escape=False,
        renderer=renderer,
        plugins=[
            "strikethrough",
            "footnotes",
            "table",
            EmailPlugin(),
            GlyphPlugin(),
            AlertBoxPlugin(),
            TemplatePlugin(context),
            ConditionPlugin(text_vars),
            VarPlugin(text_vars),
            directives.RSTDirective(
                [
                    VarSetterPlugin(text_vars),
                ]
            ),
        ],
    )
    return m(text)
