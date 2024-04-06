import sys
import typing

from .base import MtToken


class MdNodeVisitor:
    def __init__(self, out=sys.stdout) -> None:
        self.out = out

    def element(self, node: MtToken, depth: int, suffix: str = "") -> str:
        indent = "    " * depth
        if suffix:
            suffix = ": " + suffix
        print(f'{indent}{node["type"]}{suffix}', file=self.out)
        return indent

    def visit(self, node: MtToken | list[MtToken], depth: int = 0) -> None:
        if isinstance(node, list):
            for child in node:
                self.visit(child, depth)
        else:
            e_type_fn = "visit_" + node["type"]
            visitor: typing.Callable[[MtToken, int], None] = getattr(
                self, e_type_fn, self.generic_visit
            )
            visitor(node, depth)

    def generic_visit(self, node: MtToken, depth: int) -> None:
        indent = self.element(node, depth)
        if "raw" in node:
            print(f'{indent}- {node["raw"]!r}', file=self.out)
        if "attrs" in node:
            print(f'{indent}- {node["attrs"]}', file=self.out)
        if "children" in node:
            self.visit(node["children"], depth + 1)

    def visit_alert_box(self, node: MtToken, depth: int) -> None:
        self.element(node, depth, "alert_box_type=" + node["attrs"]["alert_box_type"])
        self.visit(node["children"], depth + 1)

    def visit_if(self, node: MtToken, depth: int) -> None:
        indent = self.element(node, depth, "attrs.cases:")
        for cond in node["attrs"]["cases"]:
            print(f'{indent}- {cond["condition"]}', file=self.out)
            self.visit(cond["body"], depth + 1)

    def visit_text(self, node: MtToken, depth: int) -> None:
        if len(node) != 2:
            # text
            # - 'foobar'
            # - ...
            self.generic_visit(node, depth)
        else:
            # text: 'foobar'
            self.element(node, depth, repr(node["raw"]))
