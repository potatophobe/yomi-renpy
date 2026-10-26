# -*- coding: utf-8 -*-
"""
Runs the Yomi tests and prints the results grouped by topic.

    python tests/run_tests.py               all test files
    python tests/run_tests.py ranking       only files whose name contains "ranking"

The mod runs on Python 2.7 (Ren'Py 6 and 7) and Python 3 (Ren'Py 8), so run
the tests with both; README.md shows how to use a game's own Python 2.7.
The exit code is 0 when nothing failed.

Each test file defines TITLE and run(tester); see helpers.Tester.
"""

from __future__ import unicode_literals, print_function

import os
import sys
import time
import traceback

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import helpers  # noqa: E402

# Test files in reading order: from the input text to the card.
FILES = [
    "test_scanning",
    "test_conjugation",
    "test_ranking",
    "test_card_content",
    "test_dictionary_files",
    "test_build",
    "test_mod_files",
]


def main():
    selected = [f for f in FILES if not sys.argv[1:] or any(a in f for a in sys.argv[1:])]
    tester = helpers.Tester()

    helpers.write("Python %s" % sys.version.split()[0])
    start = time.time()

    for name in selected:
        module = __import__(name)
        tester.file(module.TITLE, name + ".py")
        try:
            module.run(tester)
        except Exception:
            tester.failed += 1
            tester.failures.append("%s: crashed" % module.TITLE)
            helpers.write("  CRASH")
            helpers.write(traceback.format_exc())

    ok = tester.summary()
    helpers.write("Time: %.1fs" % (time.time() - start))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
