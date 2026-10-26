"""
Builds the compact on-disk dictionary used by the Yomi Ren'Py mod.

Inputs:
    assets/dictionaries/JMdict_e.gz          JMdict (English), original XML
    assets/furigana/JmdictFurigana.json      JmdictFurigana

Outputs (into yomi/data/, or the directory given on the command line):
    keys.dat     sorted lines "key<TAB>id,id,...\\n" (UTF-8, sorted bytewise)
    keys.idx     uint32 little-endian offsets of every line in keys.dat
    entries.dat  zlib-compressed blocks of ENTRIES_PER_BLOCK entries, one JSON per line
    entries.idx  uint32 little-endian offsets of every block (+ end offset)
    meta.json    format version, block size, tag descriptions

Entry format (read by yomi/yomi_core.py, which names each field and
position; keys are short to keep the files small):
    id   JMdict entry number
    k    kanji spellings: [text, common, tags, priority]
    r    readings: [text, common, tags, applies to (None = all kanji, [] = none), priority]
    s    senses: {g: glosses, p: parts of speech, m: usage, i: note, f: fields,
                  d: dialects, ak: only for these kanji, ar: only for these readings}
    fu   furigana: {"kanji|reading": [[text, reading above it] or [text], ...]}

The format is deliberately trivial so that the reader can be pure Python
that runs on both Python 2.7 (Ren'Py 6/7) and Python 3 (Ren'Py 8) without
sqlite3, and with almost no memory.
"""

import gzip
import io
import json
import os
import re
import struct
import sys
import zlib
import xml.etree.ElementTree as ET

# Must match yomi_core.DATA_FORMAT.
DATA_FORMAT = 2

ENTRIES_PER_BLOCK = 32

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets")
JMDICT_FILE = os.path.join(ASSETS, "dictionaries", "JMdict_e.gz")
FURIGANA_FILE = os.path.join(ASSETS, "furigana", "JmdictFurigana.json")
OUTPUT_DIRECTORY = os.path.join(ROOT, "yomi", "data")

# Priority markers that make a form "common" (same rule as Yomitan and
# jmdict-simplified).
COMMON_MARKERS = set(["news1", "ichi1", "spec1", "spec2", "gai1"])

# Frequency score (see priority_score). yomi_core.COMMON_PRIORITY equals
# TOP_LIST_SCORE: one top-list marker makes a word "common" for ranking.
TOP_LISTS = ("news1", "ichi1", "spec1", "gai1")
SECOND_LISTS = ("news2", "ichi2", "spec2", "gai2")
TOP_LIST_SCORE = 20
SECOND_LIST_SCORE = 5
NEWSPAPER_BANDS = 48            # nf01 (most frequent 500 words) ... nf48

# Entities the XML standard defines; all others are JMdict's tags.
XML_ENTITIES = set(["amp", "lt", "gt", "quot", "apos"])


def priority_score(markers):
    """
    Turns JMdict priority markers into a number (higher = more common).
    nfXX ranks words in bands of 500 by newspaper frequency (nf01 first);
    the top lists mark the most common words.
    """

    score = 0
    for marker in markers:
        if marker.startswith("nf"):
            band = int(marker[2:])
            score += NEWSPAPER_BANDS + 1 - band
        elif marker in TOP_LISTS:
            score += TOP_LIST_SCORE
        elif marker in SECOND_LISTS:
            score += SECOND_LIST_SCORE
    return score


def read_jmdict(path):
    """
    Returns (entries, tags, date): an iterator over the <entry> elements of
    the JMdict XML, the tag descriptions from its DTD, and its creation date.

    JMdict writes tags as entities (<pos>&v1;</pos>), which the XML parser
    would expand to their descriptions ("Ichidan verb"). The entity
    references are replaced by their names before parsing, so tags come out
    as the short codes the mod uses.
    """

    with gzip.open(path, "rt", encoding="utf-8") as f:
        text = f.read()

    dtd_end = text.index("]>") + len("]>")
    dtd, body = text[:dtd_end], text[dtd_end:]

    tags = {}
    for name, description in re.findall(r'<!ENTITY\s+([\w-]+)\s+"([^"]*)"\s*>', dtd):
        tags[name] = " ".join(description.split())

    def entity_name(match):
        name = match.group(1)
        return match.group(0) if name in XML_ENTITIES else name

    body = re.sub(r"&([\w-]+);", entity_name, body)

    date = re.search(r"<!-- JMdict created: (\S+) -->", body)
    date = date.group(1) if date else ""

    def entries():
        for _event, element in ET.iterparse(io.BytesIO(body.encode("utf-8"))):
            if element.tag == "entry":
                yield element
                element.clear()

    return entries(), tags, date


def texts(element, tag):
    return [child.text for child in element.findall(tag)]


def is_common(markers):
    return int(bool(COMMON_MARKERS.intersection(markers)))


def compact_entry(element, furigana):
    """Converts a JMdict <entry> element into the compact format."""

    entry = {"id": int(element.findtext("ent_seq"))}

    kanji = []
    for spelling in element.findall("k_ele"):
        markers = texts(spelling, "ke_pri")
        kanji.append([spelling.findtext("keb"), is_common(markers), texts(spelling, "ke_inf"),
                      priority_score(markers)])
    entry["k"] = kanji

    readings = []
    for reading in element.findall("r_ele"):
        markers = texts(reading, "re_pri")
        if reading.find("re_nokanji") is not None:
            applies_to = []
        else:
            applies_to = texts(reading, "re_restr") or None
        readings.append([reading.findtext("reb"), is_common(markers), texts(reading, "re_inf"),
                         applies_to, priority_score(markers)])
    entry["r"] = readings

    senses = []
    parts_of_speech = []
    for sense in element.findall("sense"):
        # A sense without part of speech inherits the previous one's.
        parts_of_speech = texts(sense, "pos") or parts_of_speech

        compact = {"g": texts(sense, "gloss")}
        for key, tag in (("m", "misc"), ("i", "s_inf"), ("f", "field"), ("d", "dial"),
                         ("ak", "stagk"), ("ar", "stagr")):
            values = texts(sense, tag)
            if values:
                compact[key] = values
        if parts_of_speech:
            compact["p"] = parts_of_speech
        senses.append(compact)
    entry["s"] = senses

    entry_furigana = {}
    for spelling in kanji:
        for reading in readings:
            segments = furigana.get((spelling[0], reading[0]))
            if segments:
                entry_furigana[spelling[0] + "|" + reading[0]] = segments
    if entry_furigana:
        entry["fu"] = entry_furigana

    return entry


def load_furigana(path):
    """Returns {(kanji spelling, reading): [[text, reading above it] or [text], ...]}."""

    with open(path, encoding="utf-8-sig") as f:
        words = json.load(f)

    return {
        (word["text"], word["reading"]): [
            [segment["ruby"], segment["rt"]] if segment.get("rt") else [segment["ruby"]]
            for segment in word["furigana"]
        ]
        for word in words
    }


def write_offsets(path, offsets):
    with open(path, "wb") as f:
        f.write(struct.pack("<%dI" % len(offsets), *offsets))


def main():
    output = sys.argv[1] if len(sys.argv) > 1 else OUTPUT_DIRECTORY

    print("Loading", FURIGANA_FILE)
    furigana = load_furigana(FURIGANA_FILE)

    print("Loading", JMDICT_FILE)
    elements, tags, date = read_jmdict(JMDICT_FILE)
    entries = [compact_entry(element, furigana) for element in elements]

    os.makedirs(output, exist_ok=True)

    # Entries, in compressed blocks; and every spelling -> entry numbers.
    keys = {}
    block_offsets = []
    with open(os.path.join(output, "entries.dat"), "wb") as f:
        for start in range(0, len(entries), ENTRIES_PER_BLOCK):
            lines = []
            for i in range(start, min(start + ENTRIES_PER_BLOCK, len(entries))):
                entry = entries[i]
                lines.append(json.dumps(entry, ensure_ascii=False, separators=(",", ":")))

                for form in [spelling[0] for spelling in entry["k"]] + [reading[0] for reading in entry["r"]]:
                    ids = keys.setdefault(form, [])
                    if not ids or ids[-1] != i:
                        ids.append(i)

            block_offsets.append(f.tell())
            f.write(zlib.compress("\n".join(lines).encode("utf-8"), zlib.Z_BEST_COMPRESSION))
        block_offsets.append(f.tell())

    write_offsets(os.path.join(output, "entries.idx"), block_offsets)

    # Keys, sorted bytewise (UTF-8 byte order == code point order).
    key_offsets = []
    with open(os.path.join(output, "keys.dat"), "wb") as f:
        for key in sorted(keys, key=lambda key: key.encode("utf-8")):
            key_offsets.append(f.tell())
            line = key + "\t" + ",".join(str(i) for i in keys[key]) + "\n"
            f.write(line.encode("utf-8"))

    write_offsets(os.path.join(output, "keys.idx"), key_offsets)

    meta = {
        "format": DATA_FORMAT,
        "block": ENTRIES_PER_BLOCK,
        "entries": len(entries),
        "keys": len(key_offsets),
        "jmdict_date": date,
        "tags": tags,
    }
    with open(os.path.join(output, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=0)

    for name in sorted(os.listdir(output)):
        print("%-12s %8.1f MB" % (name, os.path.getsize(os.path.join(output, name)) / 1e6))


if __name__ == "__main__":
    sys.exit(main())
