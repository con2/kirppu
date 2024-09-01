import decimal
import os.path
import re
import textwrap
import typing
import unittest

from django.test import TestCase as DjangoTestCase
import kirppu.provision_dsl.interpreter as dsl
from kirppu.provision_dsl.interpreter import Error, ErrorType
from kirppu.models import Item
from kirppu.tests.factories import ItemFactory

PAT = re.compile(r"\W")
NUM = re.compile(r"\d+(\.\d*)?")


def make_ex_str(raises_e: BaseException):
    cause = raises_e.__cause__
    self = type(raises_e).__name__ + "(" + str(raises_e) + ")"
    if cause:
        return self + "  caused by  " + make_ex_str(cause)
    return self


class SourceMetaClass(type):
    class TestCase(typing.NamedTuple):
        name: str
        code: typing.List[str]
        expected: typing.List[str]  # actually "Optional".
        source: str

    def __new__(mcs, name, bases, namespace, **kwargs):
        tests = {}

        def maybe_save_test(the_test: typing.Optional[SourceMetaClass.TestCase]):
            if the_test is not None and the_test.code:
                the_test_name = "test_" + PAT.sub("_", the_test.name)
                tests[the_test_name] = the_test

        # Collect tests to tests dictionary.
        with open(os.path.join(os.path.dirname(__file__), "test_dsl.scm"), "rt", encoding="utf-8") as source:
            current_test = None
            for lineno, line in enumerate(source, start=1):
                line = line.rstrip()
                if line.startswith(";TEST"):
                    # ;TEST test-name
                    maybe_save_test(current_test)
                    current_test = mcs.TestCase(line[6:], [], [], source.name + ":" + str(lineno))

                elif not line.isspace() and current_test is not None:
                    if line.lstrip().startswith(";="):
                        # ;= expected_result
                        current_test.expected.append(line[3:])
                    else:
                        # lisp-code
                        current_test.code.append(line)

            maybe_save_test(current_test)

        # Transform the tests dictionary to test cases that run the program and check result.
        funcs = {}
        for test_name, (_, lisp, expect, source) in tests.items():
            program = "\n".join(lisp)
            expect = expect[0] if expect else None
            if expect is not None:
                if expect == "" or expect == "null":
                    expect = None
                elif NUM.match(expect):
                    expect = decimal.Decimal(expect)

            funcs[test_name] = mcs._make_test(test_name, program, expect, source)

        ns = dict(namespace)
        ns.update(funcs)
        result = type.__new__(mcs, name, bases, ns)
        return result

    @staticmethod
    def _make_test(name, program, expect, source):
        doc = "Code:\n" + textwrap.indent(program, "\t") + "\nExpect:\n\t" + repr(expect)

        def the_test(self):
            actual = dsl.run(program)
            self.assertEqual(expect, actual, source + ": Result not expected in test " + repr(name))
        the_test.__name__ = name
        the_test.__doc__ = doc
        return the_test


class ProvisionDslSourceTestCase(unittest.TestCase, metaclass=SourceMetaClass):
    def test_redefine(self):
        with self.assertRaises(Error) as e:
            dsl.run("""(begin (define pi 3.14) (define pi 3.141) pi)""")
        self.assertEqual(ErrorType.DEFINE, e.exception.code, make_ex_str(e.exception))

    def test_redefine_int(self):
        with self.assertRaises(Error) as e:
            dsl.run("""(begin (define 3 5))""")
        self.assertEqual(ErrorType.DEFINE, e.exception.code, make_ex_str(e.exception))

    def test_redefine_decimal(self):
        with self.assertRaises(Error) as e:
            dsl.run("""(begin (define 3.1415 5))""")
        self.assertEqual(ErrorType.DEFINE, e.exception.code, make_ex_str(e.exception))

    def test_redefine_literal_number(self):
        # Literal numbers cannot currently be unquoted, thus using them in too weird ways is currently not possible.

        with self.assertRaises(Error) as e:
            dsl.run("""(begin (define '3 5) (+ '3 2))""")
        self.assertEqual(ErrorType.ARGUMENT_TYPE, e.exception.code, make_ex_str(e.exception))

    def test_short_define(self):
        with self.assertRaises(Error) as e:
            dsl.run("""(define)""")
        self.assertEqual(ErrorType.DEFINE_SHORT, e.exception.code, make_ex_str(e.exception))

    def test_tokenizer_error(self):
        with self.assertRaises(SyntaxError) as e:
            dsl.tokenize("""a&b""")  # not really a good case. Per tokenizer, this might be ok program.

    def test_assoc_dictness(self):
        with self.assertRaises(Error) as e:
            dsl.run("""(assoc '__name__ +)""")
        self.assertEqual(ErrorType.ASSOC_NOT_ASSOCIATION, e.exception.code, make_ex_str(e.exception))

    def test_wrong_addition(self):
        with self.assertRaises(Error) as e:
            dsl.run("""(+ 'a 'b)""")
        self.assertEqual(ErrorType.ARGUMENT_TYPE, e.exception.code, make_ex_str(e.exception))

    def test_wrong_argument_count(self):
        with self.assertRaises(Error) as e:
            dsl.run("""(< 1 2 3)""")
        self.assertEqual(ErrorType.ARGUMENT_COUNT, e.exception.code, make_ex_str(e.exception))

    def test_parens_1(self):
        with self.assertRaises(SyntaxError):
            dsl.run("(1 1")

    def test_parens_2(self):
        with self.assertRaises(SyntaxError):
            dsl.run("1) 1")

    def test_non_single_top(self):
        with self.assertRaises(ValueError):
            dsl.run("1 1")

    def test_wrong_vararg_type(self):
        with self.assertRaises(Error) as e:
            dsl.run("(min 1 2 'a)")
        self.assertEqual(ErrorType.ARGUMENT_TYPE, e.exception.code, make_ex_str(e.exception))



class ProvisionDslDjangoTestCase(DjangoTestCase):
    def setUp(self):
        base_item = ItemFactory()
        for i in range(1, 5):
            ItemFactory(
                itemtype=base_item.itemtype,
                price=base_item.price + i,
                vendor=base_item.vendor,
            )

    @staticmethod
    def _evaluate(program: str):
        return dsl.run(program, items=Item.objects.all())

    def test_filter_count(self):
        self.assertEqual(2, self._evaluate("""(.count (.filter items '(< price 3)))"""))

    def test_sum_by(self):
        self.assertEqual(decimal.Decimal("16.25"), self._evaluate("""(.sumBy 'price items)"""))

    def test_filter_sum_by(self):
        self.assertEqual(decimal.Decimal("3.5"), self._evaluate("""(.sumBy 'price (.filter items '(< price 3)))"""))

    def test_empty_sum_by(self):
        self.assertEqual(decimal.Decimal(0), self._evaluate("""(.sumBy 'price (.filter items '(= price 99)))"""))

    def test_sum_by_calc(self):
        self.assertEqual(decimal.Decimal("1.925"), self._evaluate(
            """(* 0.55 (.sumBy 'price (.filter items '(< price 3))))"""))

    def test_filter_order(self):
        with self.assertRaises(Error) as e:
            self._evaluate("""(.filter items '(< 3 price))""")
        self.assertEqual(ErrorType.FILTER_FIELD, e.exception.code, make_ex_str(e.exception))

    def test_filter_field_reference(self):
        with self.assertRaises(Error) as e:
            self._evaluate("""(.filter items '(< price price))""")
        self.assertEqual(ErrorType.FILTER_OP, e.exception.code, make_ex_str(e.exception))

    def test_count_aggregate(self):
        with self.assertRaises(Error) as e:
            self._evaluate("""(.count (.sumBy 'price items))""")
        self.assertEqual(ErrorType.COUNT_QUERY, e.exception.code, make_ex_str(e.exception))

    def test_define_count_and_filter(self):
        self.assertEqual(decimal.Decimal(7), self._evaluate(
            """(begin
                (define under (.count (.filter items '(< price 3))))
                (define eqAndOver (.count (.filter items '(>= price 3))))
                (+ (* 0.5 under) (* 2 eqAndOver))
            )"""))

    def test_define_sums(self):
        self.assertEqual(decimal.Decimal(7), self._evaluate(
            """(begin
  (define sums (.aggregate items '(
    (under count (< price 3))
    (over count (>= price 3))
  )))
  (+ (* 0.5 (assoc 'under sums)) (* 2 (assoc 'over sums)))
)"""))

    def test_define_aggregate_count(self):
        self.assertEqual(decimal.Decimal("2.5"), self._evaluate(
            """(begin
  (define sums (.aggregate items '(
    (item_count count ())
  )))
  (* 0.5 (assoc 'item_count sums))
)"""))

    def test_aggregate_filter(self):
        with self.assertRaises(Error) as e:
            self._evaluate("""(.aggregate items '( (under count (< price 3 1)) ))""")
        self.assertEqual(ErrorType.AGGREGATE_DEFINITION, e.exception.code, make_ex_str(e.exception))

    def test_cmp_on_query(self):
        with self.assertRaises(Error) as e:
            self._evaluate("""(> 5 (.filter items '(< price 3)))""")
        # Note: no specialized check is done here, so the error comes from evaluating.
        self.assertEqual(ErrorType.EVAL, e.exception.code, make_ex_str(e.exception))

    def test_op_on_query(self):
        with self.assertRaises(Error) as e:
            self._evaluate("""(+ 5 (.filter items '(< price 3)))""")
        self.assertEqual(ErrorType.ARGUMENT_TYPE, e.exception.code, make_ex_str(e.exception))

    def test_filter_arg_count_too_few(self):
        with self.assertRaises(Error):
            self._evaluate("""(.filter items '(< 3))""")

    def test_filter_arg_count_too_many(self):
        with self.assertRaises(Error):
            self._evaluate("""(.filter items '(< 3 4 5))""")

    def test_non_literal_list(self):
        with self.assertRaises(Error) as e:
            self._evaluate("""(length (a b))""")
        self.assertEqual(ErrorType.EVAL, e.exception.code, make_ex_str(e.exception))
