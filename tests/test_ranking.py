# -*- coding: utf-8 -*-
"""
Matching and ranking: which results the card lists, and in which order.

Rules, in order of importance (yomi_core._score):
1. longer matches first,
2. fewer undone conjugation steps first,
3. the text's own script before its katakana/hiragana counterpart,
4. more common words and readings first (JMdict's frequency markers),
5. ordinary words before counters, suffixes and prefixes.
"""

from __future__ import unicode_literals

from helpers import core, dictionary, explain, reading, results, top

TITLE = "Matching and ranking: which results, in which order"

# (text, title of the first result, characters it covers)
LONGEST = [
    ("日本語を話す", "日本語", 3),
    ("三人で", "三人", 2),
    ("コンピューターが", "コンピューター", 7),
    ("いらっしゃいませ", "いらっしゃいませ", 8),
    ("あの子", "あの子", 3),
    ("勉強しました", "勉強", 2),         # nouns used with する match the noun
]

# (text, reading of the first result)
COMMON_READING = [
    ("頭", "あたま"),
    ("人", "ひと"),
    ("中", "なか"),
    ("今", "いま"),
    ("一人", "ひとり"),
    ("私", "わたし"),
    ("上手", "じょうず"),
    ("大人", "おとな"),
]

# (hovered character, card title): hovering each word of a sentence.
SENTENCE = "昨日、友達と映画を見に行きました。"
SENTENCE_WORDS = [
    (0, "昨日"),
    (2, None),                                  # 、
    (3, "友達"),
    (6, "映画"),
    (9, "見に行く « polite « past"),            # JMdict has 見に行く as one entry
    (11, "行く « polite « past"),
]

# Kana spellings of very common verbs: (text, title of the first result)
KANA_VERBS = [
    ("あった", "ある « past"),                  # not 会う
    ("あって", "ある « te"),
    ("あります", "ある « polite"),
]

# (text, first result expected, why it isn't yet)
KANA_VERBS_KNOWN_ISSUES = [
    ("きます", "来る « polite", "着る and 来る are in the same frequency level; the tie goes to entry order"),
    ("きて", "来る « te", "an exact dictionary entry (the rare 来手) comes before a conjugated verb"),
    ("きた", "来た", "an exact dictionary entry (北) comes before 来た, which is written in kanji in JMdict"),
]

# (text, reading expected first, why it isn't yet)
COMMON_READING_KNOWN_ISSUES = [
    ("下手", "へた", "したて and へた are in the same frequency level; the tie goes to entry order"),
    ("方", "ほう", "かた and ほう are in the same frequency level; the tie goes to entry order"),
]


def run(t):
    t.section("The longest match comes first")
    for text, form, length in LONGEST:
        match = top(text)
        t.check("%s → %s (%d characters)" % (text, form, length),
                (core.headword(match)[0], match.length) if match else None, (form, length))

    t.section("Hovering any word of a sentence")
    for index, expected in SENTENCE_WORDS:
        found = core.lookup(dictionary(), SENTENCE, index)
        t.check("%s at %d (%s) → %s" % (SENTENCE, index, SENTENCE[index], expected or "nothing"),
                explain(found[0]) if found else None, expected)

    t.section("An exact dictionary entry comes before a conjugated reading")
    titles = [explain(match) for match in results("来た")[:2]]
    t.check("来た → 来た (its own entry), then 来る « past", titles, ["来た", "来る « past"])
    titles = [explain(match) for match in results("知らない")[:2]]
    t.check("知らない → 知らない (its own entry), then 知る « negative",
            titles, ["知らない", "知る « negative"])

    t.section("The most common reading comes first")
    for text, expected in COMMON_READING:
        t.check("%s → %s" % (text, expected), reading(top(text)), expected)
    for text, expected, issue in COMMON_READING_KNOWN_ISSUES:
        t.check("%s → %s" % (text, expected), reading(top(text)), expected, known_issue=issue)

    t.section("The most common word comes first among conjugations")
    titles = [explain(match) for match in results("行った")[:2]]
    t.check("行った → 行く « past, then 行う « past", titles, ["行く « past", "行う « past"])
    for text, expected in KANA_VERBS:
        t.check("%s → %s" % (text, expected), explain(top(text)), expected)
    for text, expected, issue in KANA_VERBS_KNOWN_ISSUES:
        t.check("%s → %s" % (text, expected), explain(top(text)), expected, known_issue=issue)

    t.section("Ordinary words come before counters and suffixes")
    readings = [reading(match) for match in results("人")[:3]]
    t.check("人 → ひと (person), then じん and にん (suffix, counter)", readings, ["ひと", "じん", "にん"])

    t.section("Katakana text also finds hiragana words, and the other way round")
    t.check("ユックリ → ゆっくり", explain(top("ユックリ")), "ゆっくり")
    t.check("タベル → 食べる", explain(top("タベル")), "食べる")
    t.check("たべる → 食べる", explain(top("たべる")), "食べる")
    t.check("ママ → ママ (mom) before まま (as it is): the text's own script first",
            [explain(match) for match in results("ママ")[:3]], ["ママ", "ママ", "まま"])
    t.check("ﾀﾍﾞﾙ (half-width) → 食べる", explain(top("ﾀﾍﾞﾙ")), "食べる",
            known_issue="half-width katakana isn't converted to full-width before the lookup")

    t.section("Result limit")
    t.check("中 with a limit of 3 → 3 results", len(results("中", max_results=3)), 3)
    limit = core.MAX_RESULTS
    t.check("いらっしゃいませ (over %d matches) → %d results (the default limit)" % (limit, limit),
            len(results("いらっしゃいませ")), limit)

    t.section("Text that isn't in the dictionary gives no results")
    t.check("… → nothing", results("…"), [])
    t.check("ABC → nothing", results("ABC"), [])
