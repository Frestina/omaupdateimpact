"""The drift watch: fail when Omarchy's newest release, RCs included, stops fitting the parser.

Run it from the repo with python3 -m tests.drift_watch. --target reads an unpacked
release instead of downloading. Nothing from a release runs: its files are only
read as text.
"""

import argparse
import contextlib
import sys
import tempfile
from pathlib import Path

from tests.test_omaupdateimpact import impact


def problems(root):
    try:
        impact.check_tree(root, "release")
        parsed = impact.parse_defaults(root, "release")
    except impact.UnusableTree as error:
        return [str(error)]
    return [f"{source} defines {name}, and the parser has no rule for it." for name, source in parsed.helpers.items()]


def report(name, found):
    for problem in found:
        print(f"{name}: {problem}")
    if not found:
        print(f"{name} fits the parser.")
    return 1 if found else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Check the newest Omarchy release still fits the parser.")
    parser.add_argument("--target", type=Path, help="read an unpacked release instead of downloading")
    options = parser.parse_args(argv)
    if options.target:
        return report(options.target.name, problems(options.target))
    tags = impact.release_tags()
    if not tags:
        return report("The releases list", ["it holds no usable release."])
    with tempfile.TemporaryDirectory() as cache, contextlib.ExitStack() as held:
        return report(tags[0], problems(impact.fetch_release(tags[0], Path(cache), held)))


if __name__ == "__main__":
    sys.exit(main())
