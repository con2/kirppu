#!/usr/bin/env python
# -*- coding: utf-8 -*-

import argparse
import re
import subprocess
import os
import sys


def main():
    parser = argparse.ArgumentParser(
        description="Compile requirements file from subset of dependencies defined in"
                    " pyproject.toml and constrain the dependencies with common set"
                    " of versions stored in requirements.txt."
                    " Any arguments will be passed directly to pip-compile.",
        usage="%(prog)s [-h] [pip-compile-options]",
    )
    parser.add_argument("--output-file", "-o", type=str, metavar="FILENAME",
                        help="Output filename. - for stdout, which is also default.")

    args, pass_through = parser.parse_known_args()

    of = args.output_file
    if of == "-":
        of = None

    cmd = [
        "scripts/" + parser.prog,
        *pass_through,
    ]
    if of:
        cmd.append("-o")
        cmd.append(repr(of))
    env = dict(os.environ)
    env.update(CUSTOM_COMPILE_COMMAND=" ".join(cmd))

    compiled = subprocess.check_output([
        "pip-compile",
        "-o",
        "-",
        *pass_through,
    ],
        stderr=subprocess.DEVNULL,
        env=env,
    ).decode()

    pkg = re.compile(r"([^=]+)==.+")
    in_header = True

    with open(of, "wt") if of else sys.stdout as out:
        for line in compiled.split("\n"):
            ls = line.lstrip()
            if ls and not ls.startswith("#"):
                if in_header:
                    print("-c constraints.txt", file=out)
                    print("    # by", parser.prog, file=out)
                    in_header = False
                match = pkg.match(line)
                print(match.group(1), file=out)
            else:
                print(line, file=out)


if __name__ == '__main__':
    main()
