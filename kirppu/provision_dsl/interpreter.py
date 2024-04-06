"""
Minimalistic lisp implementation in Python.
Based on https://norvig.com/lispy.html "Language 1: Lispy Calculator".
Notable changes:
- Tokenizer using regular expression.
- AST transformer using iteration instead of recursive list modification.
- Standard environment is reduced/different and has few added functions for accessing Django database models.
- Added literals, both symbols and lists.
- Added support for comments.
"""
import decimal
import enum
import functools
import math
import operator
import re
import typing

__all__ = [
    "run",
    "tokenize",
    "Error",
    "ErrorType",
    "Literal",
    "LiteralList",
    "Symbol",
    "Token",
]

TOKENS = re.compile(r"(\d+(\.\d+)?|[-.<>=!*+/\w][-.<>=!*+/\w\d]*|'?\(|\)|'\w[\w\d]*|\s+|;+[^\n]*)", re.MULTILINE)


class ErrorType(enum.Enum):
    DEFINE = "define"
    DEFINE_SHORT = "define short"
    EVAL = "eval"
    IF_SHORT = "if short"
    ASSOC_NOT_ASSOCIATION = "assoc_not_association"
    ASSOC_NOT_DEFINED = "assoc_not_defined"
    ARGUMENT_TYPE = "argument type"
    ARGUMENT_COUNT = "argument count"

    COUNT_QUERY = "count query"
    FILTER_QUERY = "filter query"
    FILTER_EXPR = "filter expr"
    FILTER_MODEL = "filter model"
    FILTER_FIELD = "filter field"
    FILTER_OP = "filter op"
    SUM_BY_LITERAL = "sumBy literal"
    SUM_BY_QUERY = "sumBy query"
    AGGREGATE_QUERY = "aggregate query"
    AGGREGATE_DEFINITION = "aggregate definition"


class Error(Exception):
    def __init__(self, msg: str, code: typing.Union[str, ErrorType], ast=None):
        super().__init__(msg)
        self.code = code
        self.ast = ast


def tokenize(program: str) -> typing.Optional[typing.List[str]]:
    tokens = []
    start = 0
    length = len(program)
    visual_line = 1
    line_start_pos = 0
    errors = []
    in_code = True
    while start < length:
        match = TOKENS.search(program, start)
        if match.start(0) != start and in_code:
            errors.append(
                "Invalid code line %d col %d: %s" % (
                    visual_line,
                    match.start(0) - line_start_pos,
                    program[start:match.start(0)])
            )
        start = match.end(0)
        token = match.group(0)
        if not token.isspace():
            if token.startswith(";"):
                in_code = False
            elif in_code:
                tokens.append(token)
        else:
            newlines = token.count("\n")
            visual_line += newlines
            if newlines > 0:
                in_code = True
                line_start_pos = start + token.rfind("\n") - 1
    if errors:
        if len(errors) > 5:
            msg = "\n".join(errors[0:5]) + "\n...(and %d more)" % (len(errors) - 5)
        else:
            msg = "\n".join(errors)
        raise SyntaxError(msg)
    else:
        return tokens


class _Repr:
    def __repr__(self):
        return self.__class__.__name__ + "(" + super().__repr__() + ")"


class Symbol(_Repr, str):
    pass


class Literal(_Repr, str):
    pass


class LiteralList(_Repr, list):
    pass


Token = typing.Union[decimal.Decimal, Symbol, Literal, LiteralList]


def read_from_tokens(tokens: typing.Union[typing.Iterator[str], typing.List[str]]) -> typing.Iterator[Token]:
    if isinstance(tokens, list):
        tokens = iter(tokens)
    token = next(tokens)
    while token != ")":
        if token == "(":
            yield [token for token in read_from_tokens(tokens)]
        elif token == "'(":
            yield LiteralList(token for token in read_from_tokens(tokens))
        else:
            yield atomize(token)
        token = next(tokens)


def atomize(token: str) -> typing.Union[decimal.Decimal, Symbol, Literal]:
    try:
        return decimal.Decimal(token)
    except decimal.InvalidOperation:
        # Not a number.
        if token.startswith("'"):
            return Literal(token[1:])
        return Symbol(token)


def ensure_args(fn, *types):
    @functools.wraps(fn)
    def inner(*args):
        arg_count = len(args)
        type_count = len(types)
        if arg_count > type_count:
            raise Error("Too many arguments, %d, expected %d" % (arg_count, type_count), ErrorType.ARGUMENT_COUNT)
        if arg_count < type_count:
            raise Error("Too few arguments, %d, expected %d" % (arg_count, type_count), ErrorType.ARGUMENT_COUNT)
        for index, (arg, arg_type) in enumerate(zip(args, types), start=1):
            if arg_type == decimal.Decimal:
                arg_type = (int, decimal.Decimal)
            if not isinstance(arg, arg_type):
                raise Error("Wrong type of argument given in index %d, got %s" % (index, type(arg)),
                            ErrorType.ARGUMENT_TYPE)
        return fn(*args)
    return inner


def make_std_env():
    return {
        "+": ensure_args(operator.add, decimal.Decimal, decimal.Decimal),
        "-": ensure_args(operator.sub, decimal.Decimal, decimal.Decimal),
        "*": ensure_args(operator.mul, decimal.Decimal, decimal.Decimal),
        "/": ensure_args(operator.truediv, decimal.Decimal, decimal.Decimal),
        "//": ensure_args(operator.floordiv, decimal.Decimal, decimal.Decimal),
        "<": operator.lt,
        ">": operator.gt,
        "=": operator.eq,
        "<=": operator.le,
        ">=": operator.ge,
        "!": operator.ne,
        "not": operator.not_,
        "null": None,

        "abs": ensure_args(abs, decimal.Decimal),
        "begin": lambda *x: x[-1],  # arguments are evaluated in evaluate.
        "length": len,
        "max": ensure_args(max, decimal.Decimal, decimal.Decimal),
        "min": ensure_args(min, decimal.Decimal, decimal.Decimal),
        "round": ensure_args(round, decimal.Decimal),

        "ceil": ensure_args(math.ceil, decimal.Decimal),
        "floor": ensure_args(math.floor, decimal.Decimal),
    }


def evaluate(x: typing.Union[typing.List[Token], Token], env: typing.Dict[str, typing.Any]):
    """Evaluate an expression in an environment."""
    if isinstance(x, Symbol):
        return env[x]
    elif isinstance(x, (decimal.Decimal, Literal, LiteralList)):
        return x
    elif len(x) == 0:
        return None

    try:
        if x[0] == "if":
            (_, test, suite, alt) = _require_list(x, 4, ErrorType.IF_SHORT)
            exp = (suite if evaluate(test, env) else alt)
            return evaluate(exp, env)
        elif x[0] == "define":
            (_, symbol, exp) = _require_list(x, 3, ErrorType.DEFINE_SHORT)
            if symbol in env:
                raise Error("Cannot redefine %s" % symbol, ErrorType.DEFINE)
            if not isinstance(symbol, (Symbol, Literal)):
                raise Error("Cannot define %s" % symbol, ErrorType.DEFINE)
            env[symbol] = evaluate(exp, env)
        else:
            proc = evaluate(x[0], env)
            args = [evaluate(arg, env) for arg in x[1:]]
            return proc(*args)
    except Error as e:
        if e.ast is None:
            e.ast = x
        raise
    except Exception as e:
        raise Error("Error while evaluating %s" % repr(x), ErrorType.EVAL, x) from e


def _require_list(src: typing.List, length: int, error: typing.Union[ErrorType, str]):
    src_len = len(src)
    if src_len != length:
        if src_len > 0:
            raise Error("%s needs %d arguments. %d was given." % (src[0], length, src_len), error)
        raise ValueError("Invalid call for require")
    return src


def run(program: str, **kwargs):
    """Run given program, giving additional kwargs as global variables to it."""
    from . import django_interop, extra_runtime
    tokens = tokenize(program)
    ast = next(read_from_tokens(tokens))
    env = make_std_env()
    env.update(extra_runtime.make_env())
    env.update(django_interop.make_env())
    env.update(kwargs)
    return evaluate(ast, env)
