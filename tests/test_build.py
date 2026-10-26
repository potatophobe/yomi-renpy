# -*- coding: utf-8 -*-
"""
Build: utils/build_dict.py turns JMdict's XML into the mod's entries. These
tests feed it a tiny hand-written JMdict, so each rule of the conversion is
checked on a known input, and against the field names the mod's reader
uses (yomi_core). The build script needs Python 3.
"""

from __future__ import unicode_literals

import gzip
import os
import shutil
import sys
import tempfile

from helpers import PY2, ROOT, core

TITLE = "Build: JMdict XML → the mod's entries"

SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE JMdict [
<!ENTITY v1 "Ichidan verb">
<!ENTITY vt "transitive verb">
<!ENTITY n "noun (common) (futsuumeishi)">
<!ENTITY uk "word usually written using kana alone">
<!ENTITY comp "computing">
<!ENTITY ksb "Kansai-ben">
<!ENTITY sK "search-only kanji form">
<!ENTITY gikun "gikun (meaning as reading) or jukujikun
    (special kanji reading)">
]>
<!-- JMdict created: 2026-01-02 -->
<JMdict>
<entry>
<ent_seq>1000001</ent_seq>
<k_ele><keb>食べる</keb><ke_pri>ichi1</ke_pri><ke_pri>news1</ke_pri><ke_pri>nf05</ke_pri></k_ele>
<k_ele><keb>喰べる</keb><ke_inf>&sK;</ke_inf></k_ele>
<r_ele><reb>たべる</reb><re_pri>ichi1</re_pri></r_ele>
<sense><pos>&v1;</pos><pos>&vt;</pos><gloss>to eat</gloss></sense>
<sense><gloss>to live on</gloss><misc>&uk;</misc></sense>
<sense><pos>&n;</pos><field>&comp;</field><dial>&ksb;</dial><s_inf>a note</s_inf><gloss>R&amp;D</gloss></sense>
</entry>
<entry>
<ent_seq>1000002</ent_seq>
<k_ele><keb>々</keb></k_ele>
<r_ele><reb>のま</reb></r_ele>
<r_ele><reb>ノマ</reb><re_nokanji/></r_ele>
<r_ele><reb>どう</reb><re_restr>々</re_restr><re_pri>spec2</re_pri></r_ele>
<sense><pos>&n;</pos><stagr>のま</stagr><gloss>repetition mark</gloss></sense>
</entry>
</JMdict>
"""

FURIGANA = {("食べる", "たべる"): [["食", "た"], ["べる"]]}


def run(t):
    if PY2:
        t.note("skipped on Python 2: the build script needs Python 3")
        return

    sys.path.insert(0, os.path.join(ROOT, "utils"))
    import build_dict

    directory = tempfile.mkdtemp()
    try:
        path = os.path.join(directory, "JMdict_e.gz")
        with gzip.open(path, "wt", encoding="utf-8") as f:
            f.write(SAMPLE)
        elements, tags, date = build_dict.read_jmdict(path)
        entries = [build_dict.compact_entry(e, FURIGANA) for e in elements]
    finally:
        shutil.rmtree(directory)

    taberu, noma = entries

    t.section("Reading the file")
    t.check("2 entries", len(entries), 2)
    t.check("the creation date: 2026-01-02", date, "2026-01-02")
    t.check("tag names from the DTD: v1 → Ichidan verb", tags.get("v1"), "Ichidan verb")
    t.check("a tag name over two lines is joined into one line",
            tags.get("gikun"), "gikun (meaning as reading) or jukujikun (special kanji reading)")
    t.check("the entry number is the id: 1000001", taberu["id"], 1000001)

    t.section("Spellings and readings")
    t.check("食べる: common (ichi1), frequency score 20 + 20 + 44 = 84, no tags",
            taberu[core.KANJI][0], ["食べる", 1, [], 84])
    t.check("喰べる: tag sK kept as a short code", taberu[core.KANJI][1], ["喰べる", 0, ["sK"], 0])
    t.check("たべる: common, applies to every spelling (None)", taberu[core.READINGS][0], ["たべる", 1, [], None, 20])
    t.check("ノマ: \"not a reading of the kanji\" → applies to no spelling ([])",
            noma[core.READINGS][1][core.READING_APPLIES_TO], [])
    t.check("どう: restricted to 々 → applies to [々]", noma[core.READINGS][2][core.READING_APPLIES_TO], ["々"])
    t.check("spec2 alone counts as common", noma[core.READINGS][2][core.READING_COMMON], 1)

    t.section("Meanings")
    first, second, third = taberu[core.SENSES]
    t.check("parts of speech are short codes: v1, vt", first.get(core.PARTS_OF_SPEECH), ["v1", "vt"])
    t.check("a meaning without part of speech inherits the previous one's", second.get(core.PARTS_OF_SPEECH), ["v1", "vt"])
    t.check("usage: uk", second.get(core.USAGE), ["uk"])
    t.check("subject field: comp", third.get(core.FIELDS), ["comp"])
    t.check("dialect: ksb", third.get(core.DIALECTS), ["ksb"])
    t.check("JMdict's note: a note", third.get(core.INFORMATION), ["a note"])
    t.check("&amp; in a meaning becomes &: R&D", third.get(core.GLOSSES), ["R&D"])
    t.check("restricted to the reading のま", noma[core.SENSES][0].get(core.ONLY_FOR_READINGS), ["のま"])
    t.check("no restriction stored when there is none", core.ONLY_FOR_KANJI in first or core.ONLY_FOR_READINGS in first, False)

    t.section("Furigana")
    t.check("食べる|たべる gets its furigana", taberu.get(core.FURIGANA), {"食べる|たべる": [["食", "た"], ["べる"]]})
    t.check("an entry without furigana stores none", core.FURIGANA in noma, False)
