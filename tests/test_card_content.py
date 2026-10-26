# -*- coding: utf-8 -*-
"""
Card content: what one result looks like on the card. The headword with its
furigana, the "also:" line, the meanings shown, the "common" marker, the
part-of-speech line and the notes, and escaping for Ren'Py's text tags.
"""

from __future__ import unicode_literals

from helpers import core, dictionary, top

TITLE = "Card content: headword, furigana, meanings, labels"

# (text, headword, reading, furigana segments: [text, reading above it] or [text])
FURIGANA = [
    ("食べる", "食べる", "たべる", [["食", "た"], ["べる"]]),
    ("割り勘", "割り勘", "わりかん", [["割", "わ"], ["り"], ["勘", "かん"]]),
    ("万能", "万能", "ばんのう", [["万", "ばん"], ["能", "のう"]]),
]

# Words JmdictFurigana can't split: the whole reading goes over the whole word.
FURIGANA_FALLBACK = [
    ("可愛い", "可愛い", "かわいい", [["可愛い", "かわいい"]]),
    ("眼差し", "眼差し", "まなざし", [["眼差し", "まなざし"]]),
    ("刀削麺", "刀削麺", "とうしょうめん", [["刀削麺", "とうしょうめん"]]),
]

KANA_MATCHES = [
    # A word normally written in kanji shows its kanji spelling.
    ("たべる", "食べる", "たべる", [["食", "た"], ["べる"]]),
    ("まんのう", "万能", "まんのう", [["万", "まん"], ["能", "のう"]]),
    # A word usually written in kana stays in kana, without a reading.
    ("わかる", "わかる", None, [["わかる"]]),
    ("ゆっくり", "ゆっくり", None, [["ゆっくり"]]),
    # A katakana form marked as "not a reading of the kanji" stays as is.
    ("ノマ", "ノマ", None, [["ノマ"]]),
]


def headword_table(t, cases):
    for text, form, reading, segments in cases:
        t.check("%s → %s" % (text, form), list(core.headword(top(text))), [form, reading, segments])


def glosses(match):
    return [sense[core.GLOSSES][0] for sense in core.senses(match)]


def run(t):
    t.section("Headword with furigana over each kanji")
    headword_table(t, FURIGANA)

    t.section("Headword when the reading can't be split per kanji")
    headword_table(t, FURIGANA_FALLBACK)

    t.section("Headword for a word found by its kana spelling")
    headword_table(t, KANA_MATCHES)

    t.section("The \"also:\" line lists the other spellings")
    t.check("万能 → also まんのう", core.other_forms(top("万能")), ["まんのう"])
    t.check("割り勘 → also ワリカン, not the search-only spelling 割勘",
            core.other_forms(top("割り勘")), ["ワリカン"])
    t.check("ノマ → also 々 and のま", core.other_forms(top("ノマ")), ["々", "のま"])

    t.section("Only meanings that apply to the matched reading are shown")
    t.check("ばんのう → 2 meanings (not \"fork hoe\", which is only まんのう)",
            glosses(top("ばんのう")), ["all-purpose", "all-powerful"])
    t.check("まんのう → 3 meanings, including \"fork hoe\"",
            glosses(top("まんのう")), ["all-purpose", "all-powerful", "fork hoe"])

    t.section("\"common\" marker")
    t.check("食べる is common", core.is_common(top("食べる")), True)
    t.check("刀削麺 is not common", core.is_common(top("刀削麺")), False)

    tags = dictionary().tags

    t.section("Part-of-speech line: the card's short labels")
    t.check("n, vs, vt → noun, suru verb, transitive",
            core.part_of_speech_text(["n", "vs", "vt"], tags), "noun, suru verb, transitive")
    t.check("v5k, v5k-s → godan verb (shown once)",
            core.part_of_speech_text(["v5k", "v5k-s"], tags), "godan verb")
    t.check("食べる → ichidan verb, transitive",
            core.part_of_speech_text(core.senses(top("食べる"))[0][core.PARTS_OF_SPEECH], tags), "ichidan verb, transitive")

    t.section("Part-of-speech line: JMdict's own name when the card has no label")
    t.check("v2a-s → Nidan verb with 'u' ending (archaic)",
            core.part_of_speech_text(["v2a-s"], tags), "Nidan verb with 'u' ending (archaic)")
    t.check("an unknown code is shown as is: zzz → zzz",
            core.part_of_speech_text(["zzz"], tags), "zzz")

    t.section("Notes under a meaning: usage, subject, dialect, then JMdict's note")
    sense = {core.GLOSSES: ["x"], core.USAGE: ["uk", "rare"], core.FIELDS: ["comp"],
             core.DIALECTS: ["ksb"], core.INFORMATION: ["a free-text note"]}
    t.check("uk, rare, comp, ksb, note → usually kana, rare, computing, Kansai-ben, note",
            core.sense_notes(sense, tags),
            ["usually kana", "rare", "computing", "Kansai-ben", "a free-text note"])
    t.check("MA (no short label) → martial arts", core.sense_notes({core.FIELDS: ["MA"]}, tags), ["martial arts"])
    t.check("刀削麺 → food, cooking", core.sense_notes(core.senses(top("刀削麺"))[0], tags), ["food, cooking"])
    t.check("a meaning without notes → no notes", core.sense_notes({core.GLOSSES: ["x"]}, tags), [])

    t.section("Text is escaped for Ren'Py")
    t.check("{ is doubled, so Ren'Py doesn't read it as a text tag",
            core.escape_text_tags("to {be} done"), "to {{be} done")
    t.check("[ is left alone (the card turns off [variable] substitution)",
            core.escape_text_tags("[see] here"), "[see] here")
