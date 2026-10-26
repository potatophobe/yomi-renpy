# -*- coding: utf-8 -*-
"""
Mod files: every Python file of the mod compiles on this Python. The other
tests only import yomi_core; this also catches a syntax error in
yomi_renpy.py, which can only be imported inside Ren'Py.
"""

from __future__ import unicode_literals

import io
import os

from helpers import MOD

TITLE = "Mod files: the mod's code compiles"


def run(t):
    t.section("Every .py file in yomi/ compiles")
    for name in sorted(os.listdir(MOD)):
        if not name.endswith(".py"):
            continue
        with io.open(os.path.join(MOD, name), encoding="utf-8") as f:
            source = f.read()
        try:
            compile(source.encode("utf-8"), name, "exec")
            error = None
        except SyntaxError as e:
            error = "line %s: %s" % (e.lineno, e.msg)
        t.check(name, error, None)
