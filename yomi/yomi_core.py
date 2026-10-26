# -*- coding: utf-8 -*-
"""
Yomi core: dictionary reader, deinflector and Yomitan-style scanner.

Pure Python, no Ren'Py dependency, runs on Python 2.7 and Python 3, so it
works inside every Ren'Py version from 6.x to 8.x and can be tested on its
own.
"""

from __future__ import unicode_literals, division, absolute_import

import collections
import json
import os
import struct
import sys
import zlib

PY2 = sys.version_info[0] == 2


def character_from_code(code):
    """chr() for both Pythons. Python 2 builds that can't hold the character get U+FFFD."""
    if not PY2:
        return chr(code)
    try:
        return unichr(code)  # noqa: F821
    except ValueError:
        return "�"


################################################################################
# Lookup limits, also the card's defaults.

# Characters looked up from the hovered one.
MAX_SCAN_LENGTH = 16

# Results listed on a card.
MAX_RESULTS = 16


################################################################################
# Character classes.

KANA_RANGES = (
    (0x3040, 0x30FF),     # hiragana and katakana
    (0x31F0, 0x31FF),     # katakana phonetic extensions
    (0xFF66, 0xFF9F),     # half-width katakana
)

KANJI_RANGES = (
    (0x4E00, 0x9FFF),     # CJK unified ideographs
    (0x3400, 0x4DBF),     # extension A
    (0xF900, 0xFAFF),     # compatibility ideographs
    (0x20000, 0x2FA1F),   # extensions B and later
)

# Characters that aren't kanji but are written and read like them.
KANJI_LIKE = "々〆ヶ〇"

# Katakana ァ (U+30A1) to ヶ (U+30F6) map onto hiragana ぁ (U+3041) to ゖ.
KATAKANA_FIRST = 0x30A1
KATAKANA_LAST = 0x30F6
KATAKANA_TO_HIRAGANA = 0x30A1 - 0x3041

# Characters that end a scan (punctuation, spaces, brackets).
STOP_CHARS = set("。、，．・：；？！?!「」『』（）()［］[]〈〉《》【】〔〕…‥〜～—―-\"'“”‘’　 \t\n\r.,:;")


def _in_ranges(character, ranges):
    code = ord(character)
    return any(first <= code <= last for first, last in ranges)


def is_kana(character):
    return _in_ranges(character, KANA_RANGES)


def is_kanji(character):
    return _in_ranges(character, KANJI_RANGES) or character in KANJI_LIKE


def is_japanese(character):
    return is_kana(character) or is_kanji(character)


def kata_to_hira(text):
    """Converts katakana to hiragana; other characters are kept."""
    rv = []
    for character in text:
        code = ord(character)
        if KATAKANA_FIRST <= code <= KATAKANA_LAST:
            character = character_from_code(code - KATAKANA_TO_HIRAGANA)
        rv.append(character)
    return "".join(rv)


################################################################################
# Deinflection.
#
# A rule turns a word ending in `inflected` whose conditions intersect
# `conditions_in` into a word ending in `base` with conditions
# `conditions_out`. The initial (not yet deinflected) text matches any
# conditions. A final candidate is accepted for an entry if the entry's part
# of speech is among the candidate's conditions.
#
# Condition names: the JMdict godan classes (v5u, v5k, ...), v1, vk, vs,
# adj-i, plus intermediate forms: "masu" (polite stem + masu), "te"
# (te-form), and "end" (forms that cannot inflect further).

Rule = collections.namedtuple("Rule", "inflected base conditions_in conditions_out reason")

END = ("end",)
TE = ("te",)
V1 = ("v1",)
ADJECTIVE = ("adj-i",)
MASU = ("masu",)

# The most rules applied to one word (e.g. causative « passive « negative « past).
MAX_DEINFLECTION_STEPS = 6

# How one class of verbs conjugates: the endings and stems that replace its
# dictionary ending.
VerbClass = collections.namedtuple("VerbClass", [
    "dictionary_ending",  # 書く: く
    "conditions",         # its part of speech: ("v5k",)
    "negative_stem",      # 書か(ない)
    "masu_stem",          # 書き(ます), also used alone
    "zu_stem",            # 書か(ず)
    "past",               # 書いた
    "te",                 # 書いて
    "provisional",        # 書けば
    "volitional",         # 書こう
    "imperatives",        # 書け
    "passives",           # 書かれる
    "causatives",         # 書かせる
    "potentials",         # 書ける
])

# dictionary ending, a-stem, i-stem, e-stem, o-stem, te-form, past
GODAN = [
    ("v5u", "う", "わ", "い", "え", "お", "って", "った"),
    ("v5k", "く", "か", "き", "け", "こ", "いて", "いた"),
    ("v5g", "ぐ", "が", "ぎ", "げ", "ご", "いで", "いだ"),
    ("v5s", "す", "さ", "し", "せ", "そ", "して", "した"),
    ("v5t", "つ", "た", "ち", "て", "と", "って", "った"),
    ("v5n", "ぬ", "な", "に", "ね", "の", "んで", "んだ"),
    ("v5b", "ぶ", "ば", "び", "べ", "ぼ", "んで", "んだ"),
    ("v5m", "む", "ま", "み", "め", "も", "んで", "んだ"),
    ("v5r", "る", "ら", "り", "れ", "ろ", "って", "った"),
]


def _godan_class(part_of_speech, u, a, i, e, o, te, past):
    return VerbClass(
        dictionary_ending=u, conditions=(part_of_speech,),
        negative_stem=a, masu_stem=i, zu_stem=a, past=past, te=te,
        provisional=e + "ば", volitional=o + "う", imperatives=[e],
        passives=[a + "れる"], causatives=[a + "せる"], potentials=[e + "る"])


ICHIDAN = VerbClass(
    dictionary_ending="る", conditions=V1,
    negative_stem="", masu_stem="", zu_stem="", past="た", te="て",
    provisional="れば", volitional="よう", imperatives=["ろ", "よ"],
    passives=["られる"], causatives=["させる"], potentials=["れる"])

SURU = VerbClass(
    dictionary_ending="する", conditions=("vs",),
    negative_stem="し", masu_stem="し", zu_stem="せ", past="した", te="して",
    provisional="すれば", volitional="しよう", imperatives=["しろ", "せよ"],
    passives=["される"], causatives=["させる"], potentials=[])


def _kuru_class(dictionary_form, ko, ki, ku):
    """来る, written in kana (こ/き/く) or with the kanji 来 for every stem."""
    return VerbClass(
        dictionary_ending=dictionary_form, conditions=("vk",),
        negative_stem=ko, masu_stem=ki, zu_stem=ko, past=ki + "た", te=ki + "て",
        provisional=ku + "れば", volitional=ko + "よう", imperatives=[ko + "い"],
        passives=[ko + "られる"], causatives=[ko + "させる"],
        potentials=[ko + "られる", ko + "れる"])


KURU = [_kuru_class("くる", "こ", "き", "く"), _kuru_class("来る", "来", "来", "来")]


def _build_rules():
    rules = []

    def add(inflected, base, conditions_in, conditions_out, reason):
        rules.append(Rule(inflected, base, frozenset(conditions_in), frozenset(conditions_out), reason))

    def add_verb_class(verb):
        """Adds the common conjugations of one verb class."""

        def add_form(ending, conditions_in, reason):
            add(ending, verb.dictionary_ending, conditions_in, verb.conditions, reason)

        add_form(verb.negative_stem + "ない", ADJECTIVE, "negative")
        add_form(verb.zu_stem + "ん", END, "negative")
        add_form(verb.zu_stem + "ず", END, "negative (zu)")
        add_form(verb.zu_stem + "ずに", END, "without")
        add_form(verb.masu_stem + "ます", MASU, "polite")
        add_form(verb.past, END, "past")
        add_form(verb.past + "ら", END, "conditional")
        add_form(verb.past + "り", END, "tari")
        add_form(verb.te, TE, "te")
        add_form(verb.provisional, END, "provisional")
        add_form(verb.volitional, END, "volitional")
        for ending in verb.imperatives:
            add_form(ending, END, "imperative")
        for ending in verb.passives:
            add_form(ending, V1, "passive")
        for ending in verb.causatives:
            add_form(ending, V1, "causative")
        for ending in verb.potentials:
            add_form(ending, V1, "potential")
        add_form(verb.masu_stem + "たい", ADJECTIVE, "want")
        add_form(verb.masu_stem + "そう", END, "seemingly")
        add_form(verb.masu_stem + "なさい", END, "polite imperative")
        add_form(verb.masu_stem + "ながら", END, "while")
        add_form(verb.masu_stem + "すぎる", V1, "too much")
        add_form(verb.masu_stem + "やすい", ADJECTIVE, "easy to")
        add_form(verb.masu_stem + "にくい", ADJECTIVE, "hard to")
        add_form(verb.masu_stem, END, "masu stem")

    # Godan verbs.
    for godan in GODAN:
        add_verb_class(_godan_class(*godan))

    # Short causative (書かす), a godan verb itself: 書かされる is its passive.
    for part_of_speech, u, a, i, e, o, te, past in GODAN:
        add(a + "す", u, ("v5s",), (part_of_speech,), "causative")

    # Irregular te/past of 行く (v5k-s) and the masu-stem forms of the
    # honorific v5aru verbs (いらっしゃい, なさい, ください, ...).
    for iku_stem in ("行", "い"):
        add(iku_stem + "って", iku_stem + "く", TE, ("v5k",), "te")
        add(iku_stem + "った", iku_stem + "く", END, ("v5k",), "past")
        add(iku_stem + "ったら", iku_stem + "く", END, ("v5k",), "conditional")
        add(iku_stem + "ったり", iku_stem + "く", END, ("v5k",), "tari")
    add("います", "る", MASU, ("v5aru",), "polite")
    add("い", "る", END, ("v5aru",), "imperative")

    add_verb_class(ICHIDAN)
    add_verb_class(SURU)
    for kuru in KURU:
        add_verb_class(kuru)

    # I-adjectives.
    add("かった", "い", END, ADJECTIVE, "past")
    add("かったら", "い", END, ADJECTIVE, "conditional")
    add("かったり", "い", END, ADJECTIVE, "tari")
    add("くない", "い", ADJECTIVE, ADJECTIVE, "negative")
    add("くて", "い", TE + END, ADJECTIVE, "te")
    add("く", "い", END, ADJECTIVE, "adverbial")
    add("ければ", "い", END, ADJECTIVE, "provisional")
    add("かろう", "い", END, ADJECTIVE, "volitional")
    add("さ", "い", END, ADJECTIVE, "noun")
    add("そう", "い", END, ADJECTIVE, "seemingly")
    add("すぎる", "い", V1, ADJECTIVE, "too much")
    add("くありません", "い", END, ADJECTIVE, "polite negative")
    add("ないで", "ない", END, ADJECTIVE, "negative te")
    add("なきゃ", "ない", END, ADJECTIVE, "must")
    add("なくちゃ", "ない", END, ADJECTIVE, "must")

    # Polite (masu) forms.
    add("ました", "ます", END, MASU, "past")
    add("ましたら", "ます", END, MASU, "conditional")
    add("ません", "ます", END, MASU, "negative")
    add("ませんでした", "ます", END, MASU, "past negative")
    add("ましょう", "ます", END, MASU, "volitional")
    add("まして", "ます", TE + END, MASU, "te")
    add("ませ", "ます", END, MASU, "imperative")

    # Te-form auxiliaries.
    for te in ("て", "で"):
        add(te + "いる", te, V1, TE, "progressive")
        add(te + "る", te, V1, TE, "progressive")
        add(te + "しまう", te, ("v5u",), TE, "completion")
        add(te + "おく", te, ("v5k",), TE, "preparation")
        add(te + "ある", te, ("v5r",), TE, "resultative")
        add(te + "は", te, END, TE, "topic")
        add(te + "も", te, END, TE, "even if")
    add("ちゃう", "て", ("v5u",), TE, "completion")
    add("じゃう", "で", ("v5u",), TE, "completion")
    add("ちまう", "て", ("v5u",), TE, "completion")
    add("じまう", "で", ("v5u",), TE, "completion")
    add("とく", "て", ("v5k",), TE, "preparation")
    add("どく", "で", ("v5k",), TE, "preparation")
    add("ちゃ", "て", END, TE, "contraction")
    add("じゃ", "で", END, TE, "contraction")

    # Drop rules that change nothing, and duplicates (verb classes share
    # some endings).
    seen = set()
    rv = []
    for rule in rules:
        if rule.inflected == rule.base and rule.conditions_in == rule.conditions_out:
            continue
        if rule not in seen:
            seen.add(rule)
            rv.append(rule)

    return rv


RULES = _build_rules()


def _index_rules_by_last_character(rules):
    """
    Rules grouped by the last character of their inflected ending, so a word
    is only checked against rules that can match it. Rules with an empty
    ending (the masu stem of ichidan verbs) are under "".
    """
    rv = {}
    for rule in rules:
        rv.setdefault(rule.inflected[-1:], []).append(rule)
    return rv


_RULES_BY_LAST_CHARACTER = _index_rules_by_last_character(RULES)


def deinflect(source, max_steps=MAX_DEINFLECTION_STEPS):
    """
    Returns a list of (term, conditions, reasons) candidates for `source`,
    starting with the source itself (conditions None = anything).
    """

    results = [(source, None, ())]
    seen = set([(source, None)])
    i = 0

    while i < len(results):
        term, conditions, reasons = results[i]
        i += 1

        if len(reasons) >= max_steps:
            continue

        candidates = (_RULES_BY_LAST_CHARACTER.get(term[-1:], ()),
                      _RULES_BY_LAST_CHARACTER.get("", ()))

        for rules in candidates:
            for rule in rules:
                if not term.endswith(rule.inflected):
                    continue
                if conditions is not None and not (conditions & rule.conditions_in):
                    continue
                if rule.inflected == "" and conditions is not None:
                    # The masu-stem rule only applies to the original text.
                    continue

                new = term[:len(term) - len(rule.inflected)] + rule.base
                if not new or (new == term and rule.conditions_out == conditions):
                    continue

                key = (new, rule.conditions_out)
                if key in seen:
                    continue
                seen.add(key)
                results.append((new, rule.conditions_out, (rule.reason,) + reasons))

    return results


def part_of_speech_conditions(parts_of_speech):
    """Maps JMdict part-of-speech codes to deinflection conditions."""
    rv = set()
    for code in parts_of_speech:
        if code.startswith("v5"):
            rv.add(code)
            if code == "v5k-s":
                rv.add("v5k")
            elif code in ("v5r-i", "v5aru"):
                rv.add("v5r")
            elif code == "v5u-s":
                rv.add("v5u")
        elif code in ("v1", "v1-s"):
            rv.add("v1")
        elif code == "vk":
            rv.add("vk")
        elif code in ("vs-i", "vs-s"):
            rv.add("vs")
        elif code in ("adj-i", "adj-ix"):
            rv.add("adj-i")
    return rv


################################################################################
# Dictionary format, written by utils/build_dict.py (see its docstring).

DATA_FORMAT = 2

KEYS_FILE = "keys.dat"
KEYS_INDEX_FILE = "keys.idx"
ENTRIES_FILE = "entries.dat"
ENTRIES_INDEX_FILE = "entries.idx"
META_FILE = "meta.json"

# Fields of an entry (kept short in the data to save space).
KANJI = "k"                 # spellings with kanji: lists, see KANJI_TEXT...
READINGS = "r"              # kana spellings: lists, see READING_TEXT...
SENSES = "s"                # meanings: dicts, see GLOSSES...
FURIGANA = "fu"             # {"kanji|reading": [[text, reading above it] or [text], ...]}

# Positions in a kanji spelling.
KANJI_TEXT = 0
KANJI_COMMON = 1            # 1 if marked common
KANJI_TAGS = 2              # e.g. ["sK"]
KANJI_PRIORITY = 3          # frequency score, see utils/build_dict.py

# Positions in a reading.
READING_TEXT = 0
READING_COMMON = 1
READING_TAGS = 2
READING_APPLIES_TO = 3      # kanji spellings it reads; None = all, [] = none
READING_PRIORITY = 4

# Fields of a sense.
GLOSSES = "g"               # English meanings
PARTS_OF_SPEECH = "p"
USAGE = "m"                 # e.g. "uk" (usually kana)
INFORMATION = "i"           # JMdict's free-text note
FIELDS = "f"                # subject field, e.g. "comp"
DIALECTS = "d"
ONLY_FOR_KANJI = "ak"       # spellings the sense is restricted to
ONLY_FOR_READINGS = "ar"

# JMdict tags used by the lookup.
USUALLY_KANA = "uk"
SEARCH_ONLY_KANA = "sk"
SEARCH_ONLY_KANJI = "sK"
UNUSUAL_KANJI = ("sK", "rK", "iK", "oK")    # search-only, rare, irregular, outdated

# The index files are arrays of uint32 little-endian offsets.
_OFFSET = struct.Struct(str("<I"))

# Cache sizes: looked-up words, and decompressed blocks of entries.
LOOKUP_CACHE_SIZE = 20000
BLOCK_CACHE_SIZE = 256


class _Offsets(object):
    """A read-only array of little-endian uint32 offsets."""

    def __init__(self, data):
        self.data = data
        self.count = len(data) // _OFFSET.size

    def __len__(self):
        return self.count

    def __getitem__(self, i):
        return _OFFSET.unpack_from(self.data, i * _OFFSET.size)[0]


class Dictionary(object):

    def __init__(self, directory, opener=None):
        """
        `directory` holds the data files. `opener`, if given, is a function
        that takes a file name and returns a binary file object (used to
        read from Ren'Py archives); otherwise files are opened directly.
        """

        self.opener = opener or (lambda name: open(os.path.join(directory, name), "rb"))

        self.meta = json.loads(self._read_all(META_FILE).decode("utf-8"))
        if self.meta.get("format") != DATA_FORMAT:
            raise ValueError("The dictionary in %s has format %r, but this version of Yomi reads "
                             "format %d. Rebuild it with utils/build_dict.py."
                             % (directory, self.meta.get("format"), DATA_FORMAT))

        self.block_size = self.meta["block"]
        self.tags = self.meta.get("tags", {})

        self.key_offsets = _Offsets(self._read_all(KEYS_INDEX_FILE))
        self.block_offsets = _Offsets(self._read_all(ENTRIES_INDEX_FILE))

        self.keys_file = self.opener(KEYS_FILE)
        self.entries_file = self.opener(ENTRIES_FILE)

        self.block_cache = {}
        self.lookup_cache = {}

    def _read_all(self, name):
        f = self.opener(name)
        try:
            return f.read()
        finally:
            f.close()

    def _key_line(self, i):
        """The i-th line of the keys file, as (key, comma-separated ids) bytes."""
        f = self.keys_file
        start = self.key_offsets[i]
        f.seek(start)
        if i + 1 < len(self.key_offsets):
            data = f.read(self.key_offsets[i + 1] - start)
        else:
            data = f.read()
        key, _, ids = data.rstrip(b"\n").partition(b"\t")
        return key, ids

    def lookup_ids(self, term):
        """Returns the list of entry ids whose forms exactly match `term`."""

        rv = self.lookup_cache.get(term)
        if rv is not None:
            return rv

        # Binary search: the keys file is sorted by UTF-8 bytes.
        target = term.encode("utf-8")
        low = 0
        high = len(self.key_offsets)
        rv = []

        while low < high:
            middle = (low + high) // 2
            key, ids = self._key_line(middle)
            if key < target:
                low = middle + 1
            elif key > target:
                high = middle
            else:
                rv = [int(i) for i in ids.split(b",")]
                break

        if len(self.lookup_cache) > LOOKUP_CACHE_SIZE:
            self.lookup_cache.clear()
        self.lookup_cache[term] = rv
        return rv

    def entry(self, i):
        """The entry with id `i`, decoded on first use."""

        block = i // self.block_size
        lines = self.block_cache.get(block)

        if lines is None:
            start = self.block_offsets[block]
            end = self.block_offsets[block + 1]
            self.entries_file.seek(start)
            lines = zlib.decompress(self.entries_file.read(end - start)).split(b"\n")

            if len(self.block_cache) > BLOCK_CACHE_SIZE:
                self.block_cache.clear()
            self.block_cache[block] = lines

        position = i % self.block_size
        line = lines[position]
        if not isinstance(line, dict):
            line = json.loads(line.decode("utf-8"))
            lines[position] = line

        return line


################################################################################
# Entry helpers.

def usually_kana(entry):
    """
    Whether the word is usually written in kana. Decided by its first (main)
    meaning: a minor meaning marked "usually kana" (like one of 会う's)
    doesn't make the whole word a kana word.
    """
    return any(USUALLY_KANA in sense.get(USAGE, ()) for sense in entry[SENSES][:1])


def _reading_index(entry, term):
    """
    The index of the reading that `term` matches: the exact spelling if the
    entry has it, else the same word in the other kana script (ユックリ for
    ゆっくり). None if no reading matches.
    """
    readings = entry[READINGS]
    for i, reading in enumerate(readings):
        if reading[READING_TEXT] == term:
            return i
    hiragana = kata_to_hira(term)
    for i, reading in enumerate(readings):
        if kata_to_hira(reading[READING_TEXT]) == hiragana:
            return i
    return None


################################################################################
# Scanning (Yomitan-style longest match).

class Match(object):
    """
    One dictionary result.

    `entry` the entry dict. `source` the text matched in the game. `term`
    the dictionary form looked up. `reasons` the deinflection steps,
    innermost first (e.g. ("negative", "past")).
    """

    def __init__(self, entry, source, term, reasons):
        self.entry = entry
        self.source = source
        self.term = term
        self.reasons = reasons

    @property
    def length(self):
        return len(self.source)

    def matched_form(self):
        """Returns (form, is_kanji) for the form of the entry that matched."""
        for kanji in self.entry[KANJI]:
            if kanji[KANJI_TEXT] == self.term:
                return kanji[KANJI_TEXT], True
        i = _reading_index(self.entry, self.term)
        if i is not None:
            return self.entry[READINGS][i][READING_TEXT], False
        return self.term, False

    def __repr__(self):
        return "<Match %s %s %r>" % (self.source, self.term, self.reasons)


def scan_text(text, start, max_length=MAX_SCAN_LENGTH):
    """
    Returns the text to look up at `start`: up to `max_length` characters,
    stopping at punctuation. Returns "" if `start` isn't on Japanese text.
    """

    if start < 0 or start >= len(text) or not is_japanese(text[start]):
        return ""

    end = start
    while end < len(text) and end - start < max_length and text[end] not in STOP_CHARS:
        end += 1

    return text[start:end]


def find_terms(dictionary, text, max_results=MAX_RESULTS):
    """
    Finds dictionary entries matching prefixes of `text`, longest first.
    Returns a list of Match objects.
    """

    found = {}

    for length in range(len(text), 0, -1):
        source = text[:length]

        # Try the text as written, then in hiragana (katakana words are
        # often listed in hiragana, and the other way round).
        variants = [source]
        hiragana = kata_to_hira(source)
        if hiragana != source:
            variants.append(hiragana)

        for variant_index, variant in enumerate(variants):
            for term, conditions, reasons in deinflect(variant):
                for i in dictionary.lookup_ids(term):
                    entry = dictionary.entry(i)

                    if conditions is not None:
                        parts_of_speech = set()
                        for sense in entry[SENSES]:
                            parts_of_speech.update(sense.get(PARTS_OF_SPEECH, ()))
                        if not (part_of_speech_conditions(parts_of_speech) & conditions):
                            continue

                    score = _score(entry, term, length, reasons, variant_index)
                    old = found.get(i)
                    if old is None or score > old[0]:
                        found[i] = (score, Match(entry, source, term, reasons))

    ranked = sorted(found.values(), key=lambda scored: scored[0], reverse=True)
    return [match for _, match in ranked[:max_results]]


# Parts of speech of entries that are rarely meant when a word stands alone.
AFFIX_PARTS_OF_SPEECH = set(["ctr", "suf", "pref", "n-suf", "n-pref", "aux", "aux-v", "aux-adj"])

# Frequency tiers: a score of at least COMMON_PRIORITY means the word is on
# one of JMdict's main frequency lists (news1, ichi1, spec1, gai1); see
# TOP_LIST_SCORE in utils/build_dict.py.
COMMON_PRIORITY = 20
TIER_COMMON = 2
TIER_LISTED = 1
TIER_UNLISTED = 0

# A kana spelling of a word normally written in kanji counts as less common
# (its priority is divided by this) and as a later spelling (this is added
# to its position).
KANA_SPELLING_PRIORITY_DIVISOR = 2
KANA_SPELLING_RANK_PENALTY = 3

# Spelling position of a term that matched none of the entry's spellings.
UNKNOWN_FORM_RANK = 9


def _score(entry, term, length, reasons, variant_index):
    """
    Sort key, higher first: longer source, fewer deinflections, the text's
    own script, how common the matched form is, ordinary words before
    affixes and counters, earlier spelling, then lower entry id.

    JMdict's priority markers are coarse (and the newspaper-based nfXX
    ranks favour words like 行う over 行く), so only three tiers are used.
    """

    priority = 0
    common = 0
    form_rank = UNKNOWN_FORM_RANK

    for i, kanji in enumerate(entry[KANJI]):
        if kanji[KANJI_TEXT] == term:
            common = kanji[KANJI_COMMON]
            priority = kanji[KANJI_PRIORITY]
            form_rank = i
            break
    else:
        i = _reading_index(entry, term)
        if i is not None:
            reading = entry[READINGS][i]
            common = reading[READING_COMMON]
            priority = reading[READING_PRIORITY]
            form_rank = i
            if entry[KANJI] and not usually_kana(entry):
                priority //= KANA_SPELLING_PRIORITY_DIVISOR
                form_rank += KANA_SPELLING_RANK_PENALTY

    if priority >= COMMON_PRIORITY:
        tier = TIER_COMMON
    elif priority > 0:
        tier = TIER_LISTED
    else:
        tier = TIER_UNLISTED

    senses = entry[SENSES]
    first_parts_of_speech = senses[0].get(PARTS_OF_SPEECH, ()) if senses else ()
    affix = bool(first_parts_of_speech) and all(
        code in AFFIX_PARTS_OF_SPEECH for code in first_parts_of_speech)

    return (length, -len(reasons), -variant_index, tier, common, -affix, -form_rank, -entry["id"])


def lookup(dictionary, text, start, max_length=MAX_SCAN_LENGTH, max_results=MAX_RESULTS):
    """Scans `text` at `start` and finds the matching entries."""
    scanned = scan_text(text, start, max_length)
    if not scanned:
        return []
    return find_terms(dictionary, scanned, max_results)


################################################################################
# Presentation helpers (shared by the UI and tests).

def headword(match):
    """
    Returns (form, reading, furigana_segments) for display.

    furigana_segments is a list of [text] or [text, reading above it] lists.
    """

    entry = match.entry
    form, is_kanji = match.matched_form()
    furigana = entry.get(FURIGANA, {})

    if is_kanji:
        reading = None
        for candidate in entry[READINGS]:
            if SEARCH_ONLY_KANA in candidate[READING_TAGS]:
                continue
            applies_to = candidate[READING_APPLIES_TO]
            if applies_to is None or form in applies_to:
                reading = candidate[READING_TEXT]
                break
        if reading is None and entry[READINGS]:
            reading = entry[READINGS][0][READING_TEXT]

        segments = furigana.get(form + "|" + (reading or ""))
        if not segments:
            segments = [[form, reading]] if reading else [[form]]
        return form, reading, segments

    # Matched a kana form. Show the kanji spelling it applies to (with
    # furigana), unless the word is usually written in kana.
    kanji = None
    if not usually_kana(entry):
        applies_to = None
        for candidate in entry[READINGS]:
            if candidate[READING_TEXT] == form:
                applies_to = candidate[READING_APPLIES_TO]
                break
        for candidate in entry[KANJI]:
            if any(tag in candidate[KANJI_TAGS] for tag in UNUSUAL_KANJI):
                continue
            if applies_to is None or candidate[KANJI_TEXT] in applies_to:
                kanji = candidate[KANJI_TEXT]
                break

    if kanji:
        segments = furigana.get(kanji + "|" + form) or [[kanji, form]]
        return kanji, form, segments

    return form, None, [[form]]


def other_forms(match):
    """Other written forms of the entry (excluding search-only ones)."""
    form, reading, _ = headword(match)
    rv = []
    for kanji in match.entry[KANJI]:
        if kanji[KANJI_TEXT] != form and SEARCH_ONLY_KANJI not in kanji[KANJI_TAGS]:
            rv.append(kanji[KANJI_TEXT])
    for candidate in match.entry[READINGS]:
        text = candidate[READING_TEXT]
        if text != form and text != reading and SEARCH_ONLY_KANA not in candidate[READING_TAGS]:
            rv.append(text)
    return rv


def senses(match):
    """Returns the senses that apply to the displayed form."""
    form, reading, _ = headword(match)
    rv = []
    for sense in match.entry[SENSES]:
        only_for_kanji = sense.get(ONLY_FOR_KANJI)
        only_for_readings = sense.get(ONLY_FOR_READINGS)
        if only_for_kanji is not None and form not in only_for_kanji and reading is not None:
            continue
        if (only_for_readings is not None and reading is not None
                and reading not in only_for_readings and form not in only_for_readings):
            continue
        rv.append(sense)
    return rv or match.entry[SENSES]


def is_common(match):
    entry = match.entry
    return (any(kanji[KANJI_COMMON] for kanji in entry[KANJI])
            or any(reading[READING_COMMON] for reading in entry[READINGS]))


################################################################################
# Card text.

def escape_text_tags(text):
    """
    Escapes Ren'Py text tags, so that a "{" in a meaning is shown as is.
    (The card's Text objects use substitute=False, so "[" needs no escaping.)
    """
    return text.replace("{", "{{")


PART_OF_SPEECH_LABELS = {
    "n": "noun", "v1": "ichidan verb", "v5u": "godan verb", "v5k": "godan verb",
    "v5k-s": "godan verb", "v5g": "godan verb", "v5s": "godan verb",
    "v5t": "godan verb", "v5n": "godan verb", "v5b": "godan verb",
    "v5m": "godan verb", "v5r": "godan verb", "v5r-i": "godan verb",
    "v5aru": "godan verb", "vk": "kuru verb", "vs": "suru verb",
    "vs-i": "suru verb", "vs-s": "suru verb", "vs-c": "su verb",
    "vt": "transitive",
    "vi": "intransitive", "adj-i": "i-adjective", "adj-na": "na-adjective",
    "adj-no": "no-adjective", "adj-pn": "pre-noun adjectival", "adv": "adverb",
    "adv-to": "adverb (to)", "exp": "expression", "int": "interjection",
    "prt": "particle", "conj": "conjunction", "pn": "pronoun", "pref": "prefix",
    "suf": "suffix", "ctr": "counter", "aux-v": "auxiliary verb",
    "aux-adj": "auxiliary adjective", "cop": "copula", "num": "numeric",
    "n-suf": "noun suffix", "n-pref": "noun prefix", "adj-ix": "i-adjective",
    "adj-t": "taru-adjective", "adj-f": "prenominal", "unc": "unclassified",
}

USAGE_LABELS = {
    "uk": "usually kana", "col": "colloquial", "sl": "slang", "hon": "honorific",
    "hum": "humble", "pol": "polite", "fam": "familiar", "vulg": "vulgar",
    "arch": "archaic", "obs": "obsolete", "abbr": "abbreviation",
    "male": "male", "fem": "female", "derog": "derogatory", "joc": "jocular",
    "on-mim": "onomatopoeia", "id": "idiom", "poet": "poetic", "rare": "rare",
    "dated": "dated", "form": "formal", "chn": "children's",
}


def tag_label(code, labels, descriptions):
    """
    The card's label for a JMdict tag: our own short label from `labels` if
    there is one, else JMdict's description (`descriptions`, the tags from
    meta.json), else the code itself.
    """
    return labels.get(code) or descriptions.get(code) or code


def part_of_speech_text(codes, descriptions):
    """The part-of-speech line of a sense, e.g. "noun, suru verb"."""
    rv = []
    for code in codes:
        label = tag_label(code, PART_OF_SPEECH_LABELS, descriptions)
        if label not in rv:
            rv.append(label)
    return ", ".join(rv)


def sense_notes(sense, descriptions):
    """
    The notes shown under a sense's meanings: usage (e.g. "usually kana"),
    subject field, dialect, then JMdict's free-text sense information.
    """
    rv = [tag_label(code, USAGE_LABELS, descriptions) for code in sense.get(USAGE, ())]
    for field in (FIELDS, DIALECTS):
        rv.extend(tag_label(code, {}, descriptions) for code in sense.get(field, ()))
    rv.extend(sense.get(INFORMATION, ()))
    return rv
