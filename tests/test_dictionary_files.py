# -*- coding: utf-8 -*-
"""
Dictionary files: the built dictionary in yomi/data and the reader for it.
These catch a broken or outdated build before it reaches a game.
"""

from __future__ import unicode_literals

import io
import os
import time

from helpers import DATA, core, dictionary

TITLE = "Dictionary files: yomi/data and its reader"

FILES = sorted([core.ENTRIES_FILE, core.ENTRIES_INDEX_FILE, core.KEYS_FILE, core.KEYS_INDEX_FILE,
                core.META_FILE])

# Speed limits for hovering, in milliseconds (a lookup takes about 3 ms).
AVERAGE_LOOKUP_LIMIT = 30
SLOWEST_LOOKUP_LIMIT = 100


def entry_ids(word):
    return dictionary().lookup_ids(word)


def run(t):
    data = dictionary()

    t.section("Files")
    t.check("yomi/data holds exactly: " + ", ".join(FILES), sorted(os.listdir(DATA)), FILES)

    t.section("meta.json")
    t.check("format is %d (what the reader expects)" % core.DATA_FORMAT,
            data.meta.get("format"), core.DATA_FORMAT)
    t.check("has a block size", data.meta.get("block", 0) > 0, True)
    t.check("more than 200,000 entries", data.meta.get("entries", 0) > 200000, True)
    t.check("has the JMdict date", bool(data.meta.get("jmdict_date")), True)
    t.check("tag names: comp → computing", data.tags.get("comp"), "computing")

    t.section("Finding words (binary search in keys.dat)")
    first_key = data._key_line(0)[0].decode("utf-8")
    last_key = data._key_line(len(data.key_offsets) - 1)[0].decode("utf-8")
    t.check("the first word in keys.dat is found (%s)" % first_key, len(entry_ids(first_key)) > 0, True)
    t.check("the last word in keys.dat is found (%s)" % last_key, len(entry_ids(last_key)) > 0, True)
    t.check("食べる is found", len(entry_ids("食べる")) > 0, True)
    t.check("an unknown word gives nothing", entry_ids("ほげほげほげ"), [])
    t.check("a word's prefix alone gives nothing (食べ)", entry_ids("食べ"), [])

    t.section("Reading entries (compressed blocks in entries.dat)")
    count = data.meta["entries"]
    for label, i in (("first", 0), ("middle", count // 2), ("last", count - 1)):
        entry = data.entry(i)
        t.check("the %s entry (#%d) has an id, spellings, readings and meanings" % (label, i),
                all(key in entry for key in ("id", core.KANJI, core.READINGS, core.SENSES)), True)
    taberu = [data.entry(i) for i in entry_ids("食べる")]
    t.check("食べる's entry has the spelling 食べる",
            any(kanji[core.KANJI_TEXT] == "食べる" for entry in taberu for kanji in entry[core.KANJI]), True)

    t.section("What the build stored")
    entry = taberu[0]
    t.check("parts of speech are short codes: 食べる → v1, vt",
            entry[core.SENSES][0].get(core.PARTS_OF_SPEECH), ["v1", "vt"])
    t.check("食べる has a frequency marker", entry[core.KANJI][0][core.KANJI_PRIORITY] > 0, True)
    t.check("食べる is marked common", entry[core.KANJI][0][core.KANJI_COMMON], 1)
    noma = [data.entry(i) for i in entry_ids("ノマ")][0]
    t.check("ノマ is stored as \"not a reading of the kanji\" (applies to no kanji)",
            [reading[core.READING_APPLIES_TO] for reading in noma[core.READINGS]
             if reading[core.READING_TEXT] == "ノマ"], [[]])

    t.section("Reading through a file opener (used when a game keeps the mod in an archive)")

    def opener(name):
        with open(os.path.join(DATA, name), "rb") as f:
            return io.BytesIO(f.read())

    archived = core.Dictionary("unused", opener)
    t.check("食べる gives the same entries", archived.lookup_ids("食べる"), entry_ids("食べる"))
    t.check("and the same first result",
            core.headword(core.lookup(archived, "食べた", 0)[0])[0], "食べる")

    t.section("Speed: the card has to appear as soon as the mouse moves")
    fresh = core.Dictionary(DATA)                # nothing cached yet
    sentence = "昨日は友達と一緒に映画を見に行きました"
    times = []
    for i in range(len(sentence)):
        start = time.time()
        core.lookup(fresh, sentence, i, 16, 16)
        times.append(time.time() - start)
    average = sum(times) / len(times) * 1000
    slowest = max(times) * 1000
    t.check("hovering each character of a sentence: under %d ms on average (took %.1f ms)"
            % (AVERAGE_LOOKUP_LIMIT, average), average < AVERAGE_LOOKUP_LIMIT, True)
    t.check("and under %d ms for the slowest one (took %.1f ms)" % (SLOWEST_LOOKUP_LIMIT, slowest),
            slowest < SLOWEST_LOOKUP_LIMIT, True)
