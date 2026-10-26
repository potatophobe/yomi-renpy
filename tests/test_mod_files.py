# -*- coding: utf-8 -*-
"""
Mod files: every Python file of the mod compiles on this Python (the other
tests only import yomi_core; this also catches a syntax error in
yomi_renpy.py, which can only be imported inside Ren'Py), and the license
shipped with the mod matches the repository's.
"""

from __future__ import unicode_literals

import io
import os

from helpers import MOD, ROOT

TITLE = "Mod files: the mod's code compiles, its license is up to date"


def read(path):
    with io.open(path, encoding="utf-8") as f:
        return f.read()


def run(t):
    t.section("Every .py file in yomi/ compiles")
    for name in sorted(os.listdir(MOD)):
        if not name.endswith(".py"):
            continue
        source = read(os.path.join(MOD, name))
        try:
            compile(source.encode("utf-8"), name, "exec")
            error = None
        except SyntaxError as e:
            error = "line %s: %s" % (e.lineno, e.msg)
        t.check(name, error, None)

    t.section("License")
    t.check("yomi/LICENSES.txt contains the repository's LICENSE word for word",
            read(os.path.join(ROOT, "LICENSE")) in read(os.path.join(MOD, "LICENSES.txt")), True)
