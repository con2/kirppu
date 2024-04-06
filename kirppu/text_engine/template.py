import re

import mistune
from django.template import loader
from django.template.context import Context, RequestContext

from .base import BlockPlugin, MtToken


class TemplatePlugin(BlockPlugin):
    NAME = "template"

    TEMPLATES = {
        "itemlist": "kirppu/vendor_item_list.html",
    }

    def __init__(self, context: Context | RequestContext | dict):
        self._context = context

    def __call__(self, md: mistune.Markdown):
        templates = "|".join(self.TEMPLATES.keys())
        self.register_block(md, self.NAME, r"<(?P<template_type>%s)\s*/>" % templates)

    @classmethod
    def parse(
        cls, block: mistune.BlockParser, m: re.Match, state: mistune.BlockState
    ) -> int:
        t_type = m.group("template_type")
        template = cls.TEMPLATES[t_type]

        state.append_token(
            MtToken(
                type=cls.NAME,
                attrs={"template_name": template},
            )
        )
        return m.end() + 1

    # noinspection PyMethodOverriding
    def render(self, renderer: mistune.BaseRenderer, template_name: str) -> str:
        if self._context is None:
            import warnings

            warnings.warn(
                "No context when trying to render a template %s" % template_name
            )
        context = (
            self._context
            if self._context is None or isinstance(self._context, dict)
            else self._context.flatten()
        )
        return loader.render_to_string(template_name, context)
