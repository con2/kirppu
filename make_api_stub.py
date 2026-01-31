# -*- coding: utf-8 -*-

import argparse
import ast
import functools
import os.path

try:
    from typing import List
except ImportError:
    class _AbstractType(object):
        def __getitem__(self, item):
            pass
    List = _AbstractType()


__author__ = 'codez'


class Arg(object):
    def __init__(self, name, node: ast.arguments):
        self.name = name
        self.optional = False
        self.node = node


class Writer(object):
    def __init__(self, output):
        self._output = output
        self.print = functools.partial(print, file=self._output)

    def write_stub_header(self):
        pass

    def write_source_file_header(self, file: str):
        pass

    def write_function(self, module: str, node: ast.FunctionDef, arguments: List[Arg]):
        pass

    def write_source_file_trailer(self):
        pass

    def write_stub_trailer(self):
        pass


class JsWriter(Writer):
    def write_stub_header(self):
        self.print("""throw "Don't use";  // Automatically generated with make_api_stub""")
        self.print("// noinspection UnreachableCodeJS,JSUnusedGlobalSymbols")
        self.print("Api = {")

    def write_source_file_header(self, file: str):
        self.print("    // region", file)
        self.print()

    def write_function(self, module: str, node: ast.FunctionDef, arguments: List[Arg]):
        has_args = False
        first_real_arg = 0
        for index, arg in enumerate(arguments):
            if index == first_real_arg and arg.name == "request":
                first_real_arg += 1
                continue
            if index == first_real_arg and arg.name == "event":
                first_real_arg += 1
                continue

            if index == first_real_arg:
                self.print("    /** @param {Object} obj Parameters")
                has_args = True
            else:
                self.print()

            if arg.optional:
                self.print("     *  @param [obj.{name}]".format(name=arg.name), end="")
            else:
                self.print("     *  @param obj.{name}".format(name=arg.name), end="")

        if has_args:
            self.print("    */")
        self.print("    {name}: function({obj}) {{ /**".format(name=node.name, obj="obj" if has_args else ""))
        self.print("        {module}.{name}".format(module=module, name=node.name))
        self.print("    */},")
        self.print()

    def write_source_file_trailer(self):
        self.print("    // endregion")
        self.print()

    def write_stub_trailer(self):
        self.print("};")


class IsUsedDetector(Writer):
    def __init__(self, output):
        super().__init__(output)
        self.used_files = set()
        self._file = None

    def write_source_file_header(self, file: str):
        self._file = file

    def write_function(self, module: str, node: ast.FunctionDef, arguments: List[Arg]):
        self.used_files.add(self._file)


class PyWriter(Writer):
    def __init__(self, output, modules):
        super().__init__(output)
        self._modules = modules
        self._full_module = None

    def write_stub_header(self):
        self.print("""raise ImportError("Don't use")  # Automatically generated with make_api_stub""")
        self.print("# noinspection PyUnreachableCode")
        self.print("from .django_test import DjangoResponse  # .pyi")
        # TODO: Get rid of circular dependency in checkout_api. Then we don't need to order it to be first.
        for module in sorted(self._modules, key=lambda a: "" if "kirppu.checkout_api" in a else a):
            self.print("import", module)
        self.print()
        self.print()
        self.print("# noinspection PyMethodMayBeStatic")
        self.print("class Api(object):")
        self.print("""    def __init__(self, client, event, debug=False):
        self._event = event
    @staticmethod
    def _response_json(response): pass
    def _check_response(self, response): pass
""")

    def write_source_file_header(self, file: str):
        self.print("    # region", file)
        self.print()
        self._full_module = file_to_module(file)

    def write_function(self, module: str, node: ast.FunctionDef, arguments: List[Arg]):
        decl_args = []
        args = []
        arg_count = len(arguments)
        has_event = False
        for index, arg in enumerate(arguments):
            if index == 0 and arg.name == "request":
                continue
            if index == 1 and arg.name == "event":
                args.append("self._event")
                continue

            if arg.optional:
                d = arg.node.defaults
                default = d[index - (arg_count - len(d))]

                if isinstance(default, ast.Str):
                    default = repr(default.s)
                elif isinstance(default, ast.NameConstant):
                    default = default.value
                else:
                    raise TypeError("Unhandled AST type %s" % type(default))

                decl_args.append("{name}={default}".format(name=arg.name, default=default))
            else:
                decl_args.append(arg.name)
            args.append(arg.name)

        if decl_args:
            decl_args.insert(0, "")  # add leading comma.
            decl_args.insert(1, "*")  # prevent positional arguments.

        self.print("    def {name}(self{args}) -> DjangoResponse:".format(name=node.name, args=", ".join(decl_args)))
        self.print("        return {module}.{name}({args})".format(
            module=self._full_module, name=node.name, args=", ".join(args)))
        self.print()

    def write_source_file_trailer(self):
        self.print("    # endregion")

    def write_stub_trailer(self):
        pass


# noinspection PyPep8Naming
class DecoratorCallVisitor(ast.NodeVisitor):
    def visit_Call(self, node: ast.Call) -> bool:
        return self.visit(node.func)

    def visit_Attribute(self, node: ast.Attribute):
        return self.match_name(node.attr)

    def visit_Name(self, node: ast.Name):
        return self.match_name(node.id)

    @staticmethod
    def match_name(name):
        return name == "ajax_func"


# noinspection PyPep8Naming
class MainVisitor(ast.NodeVisitor):
    def __init__(self, mod: str, file: str, writer: Writer):
        self._decorator_visitor = DecoratorCallVisitor()
        self._module = mod
        self._file = file
        self._header_written = False
        self._writer = writer

    def visit_FunctionDef(self, node: ast.FunctionDef):
        if node.decorator_list:
            for decorator in node.decorator_list:
                if self._decorator_visitor.visit(decorator):
                    break
            else:
                return
        else:
            return

        if not self._header_written:
            self._header_written = True
            self._writer.write_source_file_header(self._file)

        if node.args:
            arguments = self.parse_arguments(node.args)
        else:
            arguments = []
        self._writer.write_function(self._module, node, arguments)

    @staticmethod
    def parse_arguments(node: ast.arguments) -> List[Arg]:
        args = []  # type: List[Arg]
        for arg in node.args:
            args.append(Arg(arg.arg, node))

        for index, default in enumerate(node.defaults):
            args[-len(node.defaults) + index].optional = True

        return args

    def end(self):
        if self._header_written:
            self._writer.write_source_file_trailer()


def handle_source(f: str, writer: Writer):
    with open(f, "rt") as handle:
        tree = ast.parse(handle.read(), f)
        mod = os.path.splitext(os.path.basename(f))[0]
        visitor = MainVisitor(mod, f, writer)
        visitor.visit(tree)
        visitor.end()


def handle_sources(sources: List[str], writer: Writer):
    writer.write_stub_header()
    for f in sources:
        handle_source(f, writer)
    writer.write_stub_trailer()


def file_to_module(name: str) -> str:
    return os.path.splitext(name)[0].replace(os.path.sep, ".")


def main(args=None):
    parser = argparse.ArgumentParser(description="Create API stub file(s).")
    parser.add_argument("--js", type=str, action="append", help="JavaScript stub file to write into.")
    parser.add_argument("--py", type=str, action="append", help="Python stub file to write into.")
    parser.add_argument("source", type=str, nargs="+", help="Python source file.")

    arguments = parser.parse_args(args)

    for filename in arguments.js:
        with open(filename, "wt") as f:
            writer = JsWriter(f)
            handle_sources(arguments.source, writer)

    if arguments.py:
        detector = IsUsedDetector(None)
        handle_sources(arguments.source, detector)
        py_modules = [file_to_module(py) for py in detector.used_files]

        for filename in arguments.py:
            with open(filename, "wt") as f:
                writer = PyWriter(f, py_modules)
                handle_sources(arguments.source, writer)


if __name__ == "__main__":
    main()
