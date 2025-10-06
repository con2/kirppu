import io

import pytest

from kirppu.text_engine import mark_down
from kirppu.text_engine.ast_visitor import MdNodeVisitor


def md_ast(text: str, context: dict | None = None) -> str:
    ast = mark_down(text, context=context, renderer="ast")
    out = io.StringIO()
    MdNodeVisitor(out).visit(ast)
    return out.getvalue()


@pytest.fixture
def email_plain() -> None:
    # The address is still going to be b64encoded.
    from unittest.mock import patch

    with (
        patch("kirppu.text_engine.monolithic.EMAIL_CLASS", "a"),
        patch("kirppu.text_engine.monolithic.EMAIL_KEY", "\0"),
    ):
        yield


def test_email(email_plain) -> None:
    out = md_ast("<email>example@example.com</email>")
    assert (
        out
        == """\
paragraph
    email
    - 'example@example.com'
"""
    )


def test_email_html(email_plain) -> None:
    out = mark_down("<email>example@example.com</email>").replace("\n", "")
    assert (
        out
        == '<p><code class="a">ZXhhbXBsZSA8ZW0+YXQ8L2VtPiBleGFtcGxlLmNvbQ</code></p>'
    )


def test_multiple_emails() -> None:
    out = md_ast(
        "<email>example@example.com</email> or <email>other@example.com</email>"
    )
    assert (
        out
        == """\
paragraph
    email
    - 'example@example.com'
    text: ' or '
    email
    - 'other@example.com'
"""
    )


def test_glyph() -> None:
    out = md_ast("<glyph info-sign/>")
    assert (
        out
        == """\
paragraph
    glyph
    - 'info-sign'
"""
    )


def test_glyph_html() -> None:
    out = mark_down("<glyph info-sign/>").replace("\n", "")
    assert out == '<p><span class="glyphicon glyphicon-info-sign"> </span></p>'


def test_alert_box() -> None:
    out = md_ast("<alertbox warning>Text</alertbox>")
    assert (
        out
        == """\
alert_box: alert_box_type=warning
    paragraph
        text: 'Text'
"""
    )


def test_alert_box_invalid_type() -> None:
    with pytest.raises(ValueError) as e:
        md_ast("<alertbox invalidtype>Text</alertbox>")
    assert e.value.args[0].startswith("Invalid argument")


def ctx(**ui_text_vars) -> dict:
    return {
        "uiTextVars": ui_text_vars,
    }


def test_var() -> None:
    out = md_ast("Value: <var name/>", ctx(name="value"))
    assert (
        out
        == """\
paragraph
    text: 'Value: '
    var
    - {'var_name': 'name', 'src': '<var name/>'}
"""
    )


def test_var_html() -> None:
    out = mark_down("Value: <var name/>", ctx(name="value")).replace("\n", "")
    assert out == """<p>Value: value</p>"""


def test_var_undefined() -> None:
    out = mark_down("Value: <var name/>").replace("\n", "")
    assert out == """<p>Value: </p>"""


def test_var_assignment() -> None:
    out = mark_down(
        """\
.. vars::
    :name: The value

Value: <var name/>, other: <var other/>
""",
        ctx(other="other value"),
    ).replace("\n", "")
    assert out == """<p>Value: The value, other: other value</p>"""


def test_condition_only_primary() -> None:
    out = md_ast("<if foo>true</if>")
    assert (
        out
        == """\
paragraph
    if: attrs.cases:
    - ['foo']
        text: 'true'
"""
    )


def test_condition_else() -> None:
    out = md_ast("<if foo>true<else>false</if>")
    assert (
        out
        == """\
paragraph
    if: attrs.cases:
    - ['foo']
        text: 'true'
    - False
        text: 'false'
"""
    )


def test_condition_chain_1() -> None:
    out = md_ast("<if foo>true<elif bar>other<else>false</if>")
    assert (
        out
        == """\
paragraph
    if: attrs.cases:
    - ['foo']
        text: 'true'
    - ['bar']
        text: 'other'
    - False
        text: 'false'
"""
    )


def test_condition_chain_2() -> None:
    out = md_ast("<if foo>true<elif bar>other<elif zot>second<else>false</if>")
    assert (
        out
        == """\
paragraph
    if: attrs.cases:
    - ['foo']
        text: 'true'
    - ['bar']
        text: 'other'
    - ['zot']
        text: 'second'
    - False
        text: 'false'
"""
    )


def test_condition_chain_no_else() -> None:
    out = md_ast("<if foo>true<elif bar>other<elif zot>second</if>")
    assert (
        out
        == """\
paragraph
    if: attrs.cases:
    - ['foo']
        text: 'true'
    - ['bar']
        text: 'other'
    - ['zot']
        text: 'second'
"""
    )


def test_condition_fn() -> None:
    out = md_ast("<if (and foo bar)>true</if>")
    assert (
        out
        == """\
paragraph
    if: attrs.cases:
    - ['(', 'and', 'foo', 'bar', ')']
        text: 'true'
"""
    )


def test_condition_var_override() -> None:
    # Raises "TypeError: 'str' object is not callable" exception in evaluate,
    # which reduces the call to empty string.
    out = mark_down(
        """\
.. vars::
    :and: A value

<if (and foo bar)>true</if>
""",
        ctx(foo=1, bar=1),
    ).replace("\n", "")
    assert out == "<p></p>"


def test_condition_missing_var() -> None:
    out = mark_down("<if (and foo bar)>true</if>", ctx(foo=1)).replace("\n", "")
    assert out == "<p></p>"


def test_condition_constant_1() -> None:
    out = mark_down("<if 1>true</if>").replace("\n", "")
    assert out == "<p>true</p>"


def test_condition_constant_2() -> None:
    out = mark_down("<if ()>true<else>false</if>").replace("\n", "")
    assert out == "<p>false</p>"


def test_non_single_toplevel_1() -> None:
    with pytest.raises(ValueError) as e:
        mark_down("<if (1)1>true</if>")
    assert e.value.args[0] == "Garbage at end of program"


def test_non_single_toplevel_2() -> None:
    with pytest.raises(ValueError) as e:
        mark_down("<if 1 1>true</if>")
    assert e.value.args[0] == "Garbage at end of program"


def test_parens_1() -> None:
    with pytest.raises(SyntaxError) as e:
        mark_down("<if 1) 1>true</if>")
    assert e.value.args[0] == "Unbalanced parentheses"


def test_parens_2() -> None:
    with pytest.raises(SyntaxError) as e:
        mark_down("<if (1 1>true</if>")
    assert e.value.args[0] == "Unbalanced parentheses"
