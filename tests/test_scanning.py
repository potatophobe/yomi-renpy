# -*- coding: utf-8 -*-
"""
Scanning: which piece of text is looked up when the mouse is over a
character. The lookup starts at the hovered character and runs to the
first punctuation mark or space, or up to the length limit
(core.MAX_SCAN_LENGTH, the card's setting).
"""

from __future__ import unicode_literals

from helpers import core

TITLE = "Scanning: what text is looked up"

# (text, hovered character index, text that gets looked up)
STOPS = [
    ("食べる。おいしい", 0, "食べる"),           # 。
    ("今日は、晴れ", 0, "今日は"),               # 、
    ("行こう！", 0, "行こう"),                   # ！
    ("本当？", 0, "本当"),                       # ？
    ("待って…", 0, "待って"),                   # …
    ("「はい」と言った", 1, "はい"),             # 」
    ("『本』", 1, "本"),                         # 』
    ("日本語 テスト", 0, "日本語"),              # space
    ("日本語　テスト", 0, "日本語"),             # full-width space
    ("一行目\n二行目", 0, "一行目"),             # line break
]

STARTS = [
    ("食べる", 1, "べる"),                       # from the middle of a word
    ("コーヒーを飲む", 0, "コーヒーを飲む"),     # ー is part of a word, not a stop
    ("人々が来た", 1, "々が来た"),               # 々 counts as Japanese
    ("ﾀﾍﾞﾙ", 0, "ﾀﾍﾞﾙ"),                         # half-width katakana counts as Japanese
    ("Hello 世界", 6, "世界"),                   # Japanese after Latin text
]

NOTHING = [
    ("Hello 世界", 0, ""),                       # hovering Latin text
    ("「はい」", 0, ""),                         # hovering punctuation
    ("123日", 0, ""),                            # hovering a digit
    ("食べる", 3, ""),                           # past the end of the text
    ("食べる", -1, ""),                          # before the start
]


def run(t):
    t.section("The lookup stops at punctuation, spaces and line breaks")
    for text, index, expected in STOPS:
        t.check("%s at %d → %s" % (text.replace("\n", "\\n"), index, expected),
                core.scan_text(text, index), expected)

    t.section("The lookup starts at the hovered character")
    for text, index, expected in STARTS:
        t.check("%s at %d → %s" % (text, index, expected), core.scan_text(text, index), expected)

    t.section("Nothing is looked up when the mouse isn't on Japanese text")
    for text, index, expected in NOTHING:
        t.check("%s at %d → nothing" % (text, index), core.scan_text(text, index), expected)

    t.section("Length limit")
    long_text = "あいうえおかきくけこさしすせそたちつてとなにぬねの"
    limit = core.MAX_SCAN_LENGTH
    t.check("%d characters → the first %d (the default limit)" % (len(long_text), limit),
            core.scan_text(long_text, 0), long_text[:limit])
    t.check("%d characters, limit 5 → the first 5" % len(long_text),
            core.scan_text(long_text, 0, 5), long_text[:5])
