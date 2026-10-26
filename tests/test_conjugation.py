# -*- coding: utf-8 -*-
"""
Conjugation: the card shows the dictionary form of a conjugated word and the
steps that were undone, e.g. 書きました → 書く « polite « past.

Each case is (text in the game, card title of the first result). The title
is the dictionary form followed by the undone steps, innermost first.
"""

from __future__ import unicode_literals

from helpers import core, explain, results, top

TITLE = "Conjugation: conjugated words lead to their dictionary form"

GODAN = [
    ("買います", "買う « polite"),                        # う
    ("言った", "言う « past"),
    ("書きました", "書く « polite « past"),               # く
    ("泳いだ", "泳ぐ « past"),                            # ぐ
    ("話した", "話す « past"),                            # す
    ("待って", "待つ « te"),                              # つ
    ("死んだ", "死ぬ « past"),                            # ぬ
    ("遊ばない", "遊ぶ « negative"),                      # ぶ
    ("読もう", "読む « volitional"),                      # む
    ("帰れば", "帰る « provisional"),                     # る
    ("書け", "書く « imperative"),
    ("書き", "書く « masu stem"),
    ("書かず", "書く « negative (zu)"),
    ("書かずに", "書く « without"),
    ("書ける", "書く « potential"),
    ("書けない", "書く « potential « negative"),
]

ICHIDAN = [
    ("食べなかった", "食べる « negative « past"),
    ("食べろ", "食べる « imperative"),
    ("食べよう", "食べる « volitional"),
    ("食べたら", "食べる « conditional"),
    ("食べたり", "食べる « tari"),
    ("食べれば", "食べる « provisional"),
    ("食べず", "食べる « negative (zu)"),
    ("食べたい", "食べる « want"),
    ("食べたくない", "食べる « want « negative"),
    ("食べながら", "食べる « while"),
    ("食べやすい", "食べる « easy to"),
    ("見せられない", "見せる « passive « negative"),
]

SURU_KURU = [
    ("しなかった", "する « negative « past"),
    ("しません", "する « polite « negative"),
    ("してる", "する « te « progressive"),
    ("来なかった", "来る « negative « past"),
    ("こなかった", "来る « negative « past"),             # 来る written in kana
    ("来ます", "来る « polite"),
    ("来て", "来る « te"),
    ("来られる", "来る « passive"),
]

IRREGULAR = [
    ("行った", "行く « past"),                            # not 行いた
    ("行って", "行く « te"),
    ("行ったら", "行く « conditional"),
    ("いらっしゃいます", "いらっしゃる « polite"),         # not いらっしゃります
    ("おっしゃいます", "おっしゃる « polite"),
]

ADJECTIVES = [
    ("高かった", "高い « past"),
    ("高くない", "高い « negative"),
    ("高くて", "高い « te"),
    ("高く", "高い « adverbial"),
    ("高そう", "高い « seemingly"),
    ("高ければ", "高い « provisional"),
    ("寒くありません", "寒い « polite negative"),
    ("良かった", "良い « past"),
    ("よくない", "良い « negative"),
]

POLITE = [
    ("食べません", "食べる « polite « negative"),
    ("食べませんでした", "食べる « polite « past negative"),
    ("食べましょう", "食べる « polite « volitional"),
    ("話せますか", "話せる « polite"),                    # stops before か
]

HELPERS = [
    ("寝ている", "寝る « te « progressive"),
    ("起きてる", "起きる « te « progressive"),             # ている without い
    ("食べてた", "食べる « te « progressive « past"),
    ("食べていない", "食べる « te « progressive « negative"),
    ("書いてしまった", "書く « te « completion « past"),
    ("書いちゃった", "書く « te « completion « past"),     # てしまう contracted
    ("読んじゃう", "読む « te « completion"),
    ("飲んじゃった", "飲む « te « completion « past"),
    ("書いておく", "書く « te « preparation"),
    ("書いては", "書く « te « topic"),
    ("待ってください", "待つ « te"),                       # stops before ください
    ("食べなきゃ", "食べる « negative « must"),
    ("食べないで", "食べる « negative « negative te"),
    ("食べなくて", "食べる « negative « te"),
    ("書いちゃだめ", "書く « te « contraction"),           # ちゃ = ては; stops before だめ
]

CAUSATIVE_PASSIVE = [
    ("読まれる", "読む « passive"),
    ("書かせる", "書く « causative"),
    ("書かされる", "書く « causative « passive"),         # short causative 書かす
    ("買わされた", "買う « causative « passive « past"),
    ("書かせられなかった", "書く « causative « passive « negative « past"),
    ("食べさせられなかった", "食べる « causative « passive « negative « past"),
    ("来させられる", "来る « causative « passive"),
]


def check_table(t, cases):
    for text, expected in cases:
        t.check("%s → %s" % (text, expected), explain(top(text)), expected)


def run(t):
    t.section("Godan verbs: one case per dictionary ending, plus forms with no ending")
    check_table(t, GODAN)

    t.section("Ichidan verbs")
    check_table(t, ICHIDAN)

    t.section("する and 来る")
    check_table(t, SURU_KURU)

    t.section("Irregular verbs: 行く and the honorific verbs")
    check_table(t, IRREGULAR)

    t.section("い-adjectives")
    check_table(t, ADJECTIVES)

    t.section("Polite forms")
    check_table(t, POLITE)

    t.section("て-form helpers and contractions")
    check_table(t, HELPERS)

    t.section("Causative and passive")
    check_table(t, CAUSATIVE_PASSIVE)

    t.section("A step is only undone if the word's part of speech allows it")
    titles = [explain(match) for match in results("きた")]
    t.check("きた → 着る « past (ichidan) is among the results", "着る « past" in titles, True)
    t.check("きた → 来る « past is among the results", "来る « past" in titles, True)
    t.check("きた → not 切る (godan: its past is きった)",
            any(x.startswith("切る") for x in titles), False)

    t.section("Undoing steps alone never produces a word")
    for text in ("た", "て", "ない", "ます", "る"):
        t.check("deinflect(\"%s\") never produces an empty word" % text,
                [term for term, _, _ in core.deinflect(text) if not term], [])
