# -*- coding: utf-8 -*-
"""
Shared helpers for the tests: loads the mod's code and dictionary, and the
Tester that records and prints results.
"""

from __future__ import unicode_literals, print_function

import io
import os
import sys

TESTS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TESTS)
MOD = os.path.join(ROOT, "yomi")
DATA = os.path.join(MOD, "data")

# Keep yomi/ free of compiled-file caches (__pycache__, .pyc/.pyo).
sys.dont_write_bytecode = True

if MOD not in sys.path:
    sys.path.insert(0, MOD)

import yomi_core as core  # noqa: E402

PY2 = sys.version_info[0] == 2

out = io.open(sys.stdout.fileno(), "w", encoding="utf-8", closefd=False)


def write(s=""):
    out.write(s + "\n")
    out.flush()


################################################################################
# Dictionary access.

_dictionary = None


def dictionary():
    """The mod's built dictionary (yomi/data), loaded once."""
    global _dictionary
    if _dictionary is None:
        _dictionary = core.Dictionary(DATA)
    return _dictionary


def results(text, max_results=core.MAX_RESULTS):
    """All lookup results for `text`, hovered at its first character."""
    return core.lookup(dictionary(), text, 0, max_results=max_results)


def top(text):
    """The first lookup result for `text`, or None."""
    found = results(text)
    return found[0] if found else None


def explain(match):
    """A match as the card shows its title, e.g. "書く « polite « past"."""
    if match is None:
        return None
    form = core.headword(match)[0]
    return " « ".join((form,) + tuple(match.reasons))


def reading(match):
    """The reading shown above the headword (None for kana words)."""
    return core.headword(match)[1] if match is not None else None


################################################################################
# Results.

def show(value):
    """Formats a value for the report (avoids Python 2's u'' reprs)."""
    if value is None:
        return "(none)"
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(show(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{" + ", ".join("%s: %s" % (show(k), show(v)) for k, v in sorted(value.items())) + "}"
    if isinstance(value, bytes) and not PY2:
        value = value.decode("utf-8", "replace")
    return "%s" % (value,)


class Tester(object):
    """
    Collects check results and prints them as

        ok     書きました → 書く « polite « past
        FAIL   泳いだ → 泳ぐ « past
               expected: 泳ぐ « past
               got:      泳ぐ « te

    A check marked with `known_issue` is a recorded limitation: it prints
    "known" while it fails and doesn't fail the run; if it starts passing,
    it prints "FIXED" as a reminder to remove the mark.
    """

    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.known = 0
        self.fixed = 0
        self.failures = []
        self.file_title = ""
        self.section_title = ""

    def file(self, title, name):
        self.file_title = title
        write()
        write("=" * 78)
        write("%s  (%s)" % (title, name))
        write("=" * 78)

    def section(self, title):
        self.section_title = title
        write()
        write(title)

    def check(self, name, got, expected, known_issue=None):
        good = got == expected

        if known_issue:
            if good:
                self.fixed += 1
                write("  FIXED  %s  (marked as a known issue: %s; remove the mark)" % (name, known_issue))
            else:
                self.known += 1
                write("  known  %s  (%s; got %s)" % (name, known_issue, show(got)))
            return

        if good:
            self.passed += 1
            write("  ok     %s" % name)
        else:
            self.failed += 1
            self.failures.append("%s / %s: %s" % (self.file_title, self.section_title, name))
            write("  FAIL   %s" % name)
            write("         expected: %s" % show(expected))
            write("         got:      %s" % show(got))

    def note(self, text):
        write("  -      %s" % text)

    def summary(self):
        write()
        write("=" * 78)
        parts = ["%d ok" % self.passed, "%d failed" % self.failed]
        if self.known:
            parts.append("%d known issues" % self.known)
        if self.fixed:
            parts.append("%d known issues now pass" % self.fixed)
        write("Summary: " + ", ".join(parts))
        for f in self.failures:
            write("  FAIL   " + f)
        return self.failed == 0
