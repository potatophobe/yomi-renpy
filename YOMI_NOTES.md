# Yomi notes: how this mod was built, and how to build the next one

Notes for building a similar mod (hover over in-game text → dictionary card)
for another game or engine. They record the questions asked, the decisions
made and why, the problems hit and how they were solved.

The notes are split in three:

1. **Common to any such mod**: process, design, dictionary data, ranking,
   testing, packaging, licensing. Reusable as is.
2. **Specific to Ren'Py**: loading the mod, finding text under the mouse,
   drawing the card, input, version differences.
3. **Specific to Python**: Python 2/3 compatibility, the data format, tooling.

A checklist for starting a new port is at the end.

---

## 1. Common to any similar mod

### 1.1 Goal and scope

The original request was a Yomitan-like Japanese learning mod for any Ren'Py
game, with two features:

* **Hover dictionary** (kept): hold a key, point at any text (dialogue,
  choices, menus, settings), get a card with furigana, meanings, part of
  speech and the conjugation that was undone.
* **Full-line translation**, Disco Elysium style (dropped by the user).
  The game's own translation where it exists, otherwise a free translator.
  After the feasibility research the user decided to drop it and keep only
  the dictionary. Don't re-add translation unless asked.

References the user gave: Yomitan (main model for lookup behavior and card
content), LunaTranslator, Wagotabi, Disco Elysium.

### 1.2 Questions to ask the user up front

These were all real decision points. Ask them early, with a recommended
option, because each changes the architecture:

| Question | Chosen here | Why it matters |
|---|---|---|
| Translation feature too, or dictionary only? | Dictionary only | Translation needs online services or large models |
| Architecture: in-game only, or a helper program outside the game? | Single drop-in folder, fully offline, no helper process | Decides packaging, portability, dependencies |
| Which dictionary? | JMdict only (no Yomitan dictionary import) | Data size, licensing, build pipeline |
| Meanings in which language? | English | JMdict_e vs the multilingual JMdict |
| How much on a card? | Several matches, scrollable | UI complexity |
| Kanji breakdown, frequency/JLPT tags, Anki export? | Not in v1 | Each is a separate feature |
| Which key to hold? | Shift (configurable: shift/alt/ctrl/always) | Ctrl is often the game's skip key; avoid it |
| Card behavior | Stays after the key is released; closes on mouse-away, Esc or click; wheel scrolls | Approved after the first prototype |
| A word-frequency list for better ranking? | **Still open**: needs the user's OK, since they chose "JMdict only" | See 1.6 |
| Test game | Katawa Shoujo (Steam, Ren'Py 6.16) | Pick an old and a new engine version |
| License for the mod's code | MIT, © 2026 potatophobe | See 1.10 |
| Release zip name | `yomi-renpy-<version>.zip` (folder inside stays `yomi`) | |

### 1.3 Working process that worked

1. **Back up first**: the whole game install plus its save/persistent data,
   and verify the copy (`diff -rq`). Later, keep `backups/` out of git.
2. **Research what's possible** before building, and present the findings
   with a recommendation. The user asked: "research what's really possible
   and how hard it is, then go on while asking me to confirm decisions."
3. **Prototype the hardest part first**: finding the character under the
   mouse in *every* kind of text (dialogue, main menu, in-game menu,
   custom menus). The dictionary is comparatively easy.
4. Build the dictionary pipeline, then the card UI.
5. **Verify on several engine versions** in real games (see 2.10), with
   screenshots, not only unit tests.
6. Write table-style tests, then review them with the user (see 1.8).
7. Code review against clean-code rules (see 1.9), confirming bigger
   changes with the user first.
8. Package, document, license, privacy check (see 1.11).

User preferences learned along the way (they apply to any project for this
user):

* **Ask before decisions**: confirm design choices and any major change to
  code or file structure before making it. Small fixes are fine to just do.
* **No abbreviations** in names: files, folders, variables, settings
  (`entries.dat`, not `ents.dat`). Rename only unclear existing names
  (`i`, `x`, `y`, `rv` may stay); established external names (JMdict tag
  codes) stay.
* **No magic values or hard-coding**: named constants with a comment;
  paths found at runtime (Steam library, git location), not written in.
* **Readable tests**: tables of cases that read like a specification.
* Keep the repository free of personal or machine information.
* Report honestly: correct your own earlier claims when they turn out wrong.

### 1.4 Architecture (engine-independent part)

```
yomi/                  the mod, copied as one folder into the game
  yomi.rpy             entry point + user settings (engine-specific)
  yomi_renpy.py        engine integration: hit testing, card, input (engine-specific)
  yomi_core.py         pure logic: dictionary reader, deinflection, ranking, card text
  data/                built dictionary (generated)
  fonts/               bundled Japanese font + its license
  README.txt, LICENSES.txt
assets/                downloaded sources: dictionaries/, furigana/, fonts/
utils/                 build_dict.py, deploy.sh, package.sh, test-driving scripts
tests/                 table tests for yomi_core and the build
```

**Keep `yomi_core.py` free of any engine code.** Everything in it ports
unchanged to another engine that can run Python, and it is what the unit
tests cover. That covers the dictionary format and reader, scanning,
deinflection, ranking, headword/furigana selection, and card text (labels,
notes, escaping).
Only the engine integration has to be rewritten for a new engine.

### 1.5 Dictionary data

Sources (put in `assets/`):

* `dictionaries/JMdict_e.gz`, from http://ftp.edrdg.org/pub/Nihongo/JMdict_e.gz
  (original XML, English). The only dictionary source.
* `furigana/JmdictFurigana.json`, from
  https://github.com/Doublevil/JmdictFurigana/releases (which kana go over
  which kanji).
* `fonts/NotoSansJP-*.otf` (SIL OFL).

Decisions and findings:

* **Original JMdict XML, not jmdict-simplified JSON.** The JSON reduces
  frequency to a yes/no "common" flag; the XML keeps the priority markers
  (news1/2, ichi1/2, spec1/2, gai1/2, nfXX). The project first used both,
  matched by entry number, but the two files came from different dates.
  Converting the XML alone gave identical entries (checked entry by entry:
  only real dictionary updates differed).
* **JMdict writes tags as XML entities** (`<pos>&v1;</pos>`); a parser
  expands them to long descriptions ("Ichidan verb"). Replace `&name;` with
  `name` (except the 5 standard XML entities) before parsing to keep the
  short codes. Read the descriptions from the DTD
  (`<!ENTITY name "description">`) into `meta.json` as fallback labels.
* A sense without `<pos>` inherits the previous sense's part of speech
  (JMdict's DTD says so).
* `<re_nokanji/>` means the reading is not a reading of the kanji (e.g.
  ノマ for 々); store "applies to" as `[]`, and `None` for "all kanji".
* "Common" = any of news1, ichi1, spec1, spec2, gai1 (same rule as Yomitan).
* **JmdictFurigana is up to date with JMdict** (checked: all its pairs still
  exist, words added in the last week are covered). It leaves out words it
  can't split (ateji, jukujikun, Chinese readings, irregular rendaku):
  about 5% of pairs. **Fallback: the whole reading over the whole word.**
  Without it, the alternative is Yomitan-style splitting by matching kana
  anchors (gives one reading over a run of kanji). Keep both files from the
  same time when updating.
* The engine had no SQLite in old versions, so the data is a trivial custom
  format (see 3.3): sorted key file + offset index + zlib-compressed JSON
  blocks of 32 entries. About 29 MB on disk, almost nothing in memory,
  about 3 ms per lookup.
* Version the data format (`meta.json: "format"`) and make the reader refuse
  an old build with a clear "rebuild it" message.

### 1.6 Lookup and ranking (Yomitan-style)

* **Scan** from the hovered character, up to 16 characters, stopping at
  punctuation, spaces and line breaks (`STOP_CHARS`). `ー` is not a stop.
  Hovering a non-Japanese character gives nothing.
* **Longest prefix first**: try every prefix of the scanned text, longest
  first; for each, try the text as written and in hiragana (katakana words
  are often listed in hiragana and vice versa).
* **Deinflection** with a rule table: a rule turns an ending into another
  ending, with conditions in/out (godan classes v5u…v5r, v1, vk, vs, adj-i,
  plus intermediate "masu", "te", "end"). Breadth-first, at most 6 steps.
  A candidate is accepted only if the entry's part of speech matches the
  conditions (so きた gives 着る and 来る but not 切る).
  * Verb classes are described as records (dictionary ending, negative stem,
    masu stem, past, te, …) and the common forms are generated from them.
  * Special cases: 行く (行った), honorific v5aru (いらっしゃいます,
    ください), short causative (書かす: 書かされる is its passive), て-form
    helpers (ている/てる, てしまう/ちゃう, ておく/とく, ちゃ).
  * **Don't add shortcut rules** that combine steps (せられる as one
    "causative" step): the explanation then misses a step. Let the chain
    build "causative « passive".
* **Ranking**, a sort key, higher first:
  1. longer source text, 2. fewer undone steps, 3. the text's own script
  before its kana counterpart, 4. frequency tier, 5. "common" flag,
  6. ordinary words before counters/suffixes/prefixes, 7. earlier spelling,
  8. lower entry id.
  * Frequency uses **three coarse tiers** of JMdict's markers (top-list,
    any marker, none). Fine nfXX ranks made 行う beat 行く for 行った.
  * A kana match of a word normally written in kanji ranks lower, unless
    the word is "usually kana". **Decide "usually kana" by the first
    meaning only**: a minor meaning marked uk (like one of 会う's) made
    あった show 会う before ある.
  * Prefer the exact reading spelling before the kana-normalized match
    (otherwise ノマ showed as 々 with reading のま).
  * An exact dictionary entry comes before a conjugated reading (来た shows
    its own entry, then 来る « past), like Yomitan.
* **Known ranking issues** (need a real frequency list, which needs the
  user's OK): 下手 → したて before へた, 方 → かた before ほう, kana 来る
  forms (きます → 着る, きて → 来手, きた → 北), half-width katakana not
  converted. Also not handled: noun + する as one verb (勉強しました
  matches 勉強), な-adjective + だった.

### 1.7 The card

Content, top to bottom, for each match: furigana over each kanji segment,
the headword, tags ("common", the undone steps "« polite « past"), "also:"
other spellings (without search-only ones), then numbered meanings
grouped under part-of-speech lines, with notes (usage, field, dialect,
JMdict's note) under each.

* Only meanings that apply to the matched spelling/reading are shown
  (JMdict's stagk/stagr).
* Labels: short labels of our own for common codes (`n` → noun,
  `uk` → usually kana), falling back to JMdict's description from
  `meta.json` (`comp` → computing), then the raw code.
* Bundle a Japanese font: many games' fonts lack kanji or a bold weight,
  and English games have no Japanese font at all.
* Escape the engine's markup characters in dictionary text.
* UX: hold the key and move to show; the card stays after the key is
  released so you can move onto it and scroll; it closes when the mouse
  leaves both word and card, on Esc, or on a click. **Clicks, wheel and Esc
  aimed at the card must not reach the game** (no advancing dialogue, no
  menu activation, no rollback).
* Size everything in units of a base font size derived from the screen
  height, so the card looks the same at any resolution. Place it below the
  word if it fits, else above, else on the side with more room.
* Hide the card when its text leaves the screen (dialogue advanced),
  tolerating one missed frame.

### 1.8 Testing

* **Table tests** for the pure logic, one file per topic in reading order:
  scanning, conjugation, ranking, card content, dictionary files, build
  (on a tiny hand-written JMdict), mod files (every source file compiles,
  license copies match).
* A tiny custom runner prints grouped `ok` / `FAIL` (with expected and
  actual) / `known` lines. **Known issues stay visible** in the tables
  instead of being deleted; they print "FIXED" when they start passing.
* Probe candidate cases first and confirm the expected values before
  writing them. Several probes revealed real bugs (causative-passive
  explanation, ノマ headword, あった ranking).
* A speed test (hovering each character of a sentence: average and worst
  case limits) guards the most important UX property.
* Compile-check every mod file, including the engine module that can't be
  imported outside the engine: a syntax error there once slipped past the
  unit tests.
* Also verify against the real game: hover, scroll, Esc, click-is-swallowed,
  card closes when the dialogue advances, on every engine version.
* Review the test plan with the user before writing, and review the tests
  again afterwards for missing important cases and for unrelated ones.

### 1.9 Code review rules applied

* Named constants with a one-line comment for every number (layout
  proportions, input codes, cache sizes, tolerances, timeouts).
* Folder and file names defined once.
* No duplicated logic (one wheel handler, one glyph-width function).
* Named fields for compact data (`entry[READINGS][i][READING_APPLIES_TO]`
  instead of `e["r"][i][3]`).
* Long functions split into named steps; records instead of long positional
  parameter lists.
* Debug output kept minimal (one line per lookup, plus errors); remove
  diagnosis-only aids once the problem is solved.
* Find unused code mechanically (pyflakes plus a script listing definitions
  that are never referenced), then re-read everything by hand.
* Verify a refactor with byte-identical output where possible (the rebuilt
  dictionary was compared file by file).

### 1.10 Licensing

* Dictionary data: JMdict (EDRDG licence, CC BY-SA 4.0) and JmdictFurigana
  (CC BY-SA 4.0). **The built data is a derived work and must stay CC BY-SA
  4.0.** Credit EDRDG.
* Font: Noto Sans JP, SIL OFL 1.1. The license text must ship with the font
  (`fonts/OFL.txt`).
* Mod code: MIT. `LICENSE` at the repository root (detected by GitHub) and
  the same text in the shipped `yomi/LICENSES.txt`, with a test checking they
  match. State clearly that the MIT license covers only the code.

### 1.11 Packaging, privacy, repository hygiene

* Release: a zip containing only the mod folder, without logs or compiled
  files. Install = unzip into the game's `game/` folder; uninstall = delete
  the folder.
* **Running games leaves personal and machine data** in test copies:
  engine logs (OS build, GPU, driver, monitor, user folder path), compiled
  caches with absolute paths, save/persistent files, the mod's own log.
  Delete them before sharing anything (`find … -newer <sdk zip> -delete`
  for files generated inside an SDK).
* `.gitignore`: the SDKs, `backups/`, and build output (`dist/`).
* Scan the repository for the user name, host name, email, home paths and
  hardware strings before publishing. Stock files can give false hits
  (Python's `C:/Users/Barney` example, "POTATO" in Unicode name tables).

### 1.12 Tooling pitfalls (Windows host)

* **Editing code through bash heredocs mangles backslashes**: `\n` inside a
  Python or PowerShell string became a real line break twice (once it
  crashed the game at startup). Write code with the file Write/Edit tools;
  compile-check after edits.
* In PowerShell, `bash` is **WSL's** bash, not Git Bash. WSL has `python3`
  and no `python`; scripts should try both. Find Git Bash through git's own
  location, never by a plain `bash`.
* A Windows "python3" can be a stub that only opens the Microsoft Store:
  test a candidate by running it.
* Claude Code keeps conversations per folder path
  (`~/.claude/projects/<path with - separators>/`); after renaming the project
  folder, move the `.jsonl` there to keep `claude -c`/`-r` working.
* Simulated input for test-driving games (Win32): `SetCursorPos`,
  `mouse_event`, `keybd_event` **with the scan code** (SDL2 ignores events
  without it; use `MapVirtualKey`). Focusing the game needs the Alt-tap
  trick before `SetForegroundWindow`; always assert the game has focus
  before sending input, so nothing goes to another window. Screenshots via
  `Graphics.CopyFromScreen` of the client area.

---

## 2. Specific to Ren'Py

### 2.1 Versions tested

| Ren'Py | Python | Notes |
|---|---|---|
| 6.16.5 (Katawa Shoujo, Steam) | 2.7.3, 32-bit, narrow Unicode build | pygame (SDL1); no ssl, sqlite3 or unicodedata; ships `.pyo` only, so run its Python with `-O` |
| 7.8.7 (SDK) | 2.7.18 | pygame_sdl2 |
| 8.5.3 (SDK) | 3.12 | pygame_sdl2 |

Test game for 7 and 8: **The Question**, which comes with the SDK and has a
Japanese translation. Make a copy and add a file with
`define config.language = "japanese"`, plus `init 1000 python:` to turn on
the mod's debug log. Launch: `renpy.exe "<project folder>"`.

### 2.2 Loading the mod

* A folder `game/yomi/` with `yomi.rpy`: Ren'Py runs every `.rpy` it finds.
  `init 999 python:` adds the folder to `sys.path`, imports the Python
  modules, applies settings and calls `install()`.
* **Wrap everything in try/except** and write failures to the mod's log: a
  broken mod must never stop the game from starting (a syntax error did
  crash Katawa Shoujo at startup once, before this wrapper existed).
* Settings live as commented lines in `yomi.rpy` (`settings.key = "shift"`).
* Data may be inside an `.rpa` archive in a packaged game: read through
  `renpy.loader.load(path)` when the folder doesn't exist on disk.
* Fonts are referenced relative to the game directory (`"yomi/fonts/…"`).
* "installed" may be logged twice in some versions (init runs twice); the
  hooks guard against double installation with a `_yomi_wrapped` mark.

### 2.3 Finding the text under the mouse (the hard part)

* **Hooking `Text.event` doesn't work**: custom displayables (Katawa
  Shoujo's menus) don't pass events on to their Text children.
* What works: walk the **render tree of the last drawn frame**,
  `renpy.display.render.screen_render`, the way Ren'Py computes focus:
  * `render.render_of` lists the displayables that produced a render; find
    `renpy.text.text.Text`.
  * `render.children` is a list of `(child, x, y, focus, main)`.
  * Accumulate transforms: `forward = render.forward * forward`,
    `reverse = reverse * render.reverse` (Matrix2D; `.transform(x, y)`).
    Child offsets are transformed with `reverse`. This also handles text
    oversampling and scaling in 7.4+/8 automatically.
  * Skip the mod's own layer; topmost text is last in drawing order.
  * Compare displayables **by identity** (`is`): Ren'Py displayables can
    define their own equality.
* **Glyph geometry**: `Text.get_layout()` returns None for renders served
  from the render cache, and Ren'Py rotates its layout cache every frame.
  So `Text.render` is wrapped to snapshot each layout's glyphs per render:
  map `id(render)` → (weakref to Text, width, height, snapshot). Don't keep
  Layout objects: they own textures (and `Render.kill()` is a no-op in
  6.16). Glyph fields: `x, y, character, width, advance, ascent,
  line_spacing`; line fields: `y, height, eop` (end of paragraph),
  `glyphs`; layout: `xoffset, yoffset, lines`.
* The looked-up text is the whole paragraph around the glyph (lines joined
  until `eop`), so words wrapped across lines are found (気付いた worked).
* Text drawn as images (logos, image buttons) can't be looked up.

### 2.4 Drawing the card and receiving input

* Put the card layer displayable in **`renpy.display.emulator.overlay`**:
  drawn above everything (menus included) and it receives events first.
  `init_emulator()` recreates that list, so wrap it and re-add the layer.
  Fallback for versions without it: `config.overlay_functions`.
* Event "passes": mouse motion and key events bump a serial number and call
  `renpy.display.render.redraw(layer, 0)`; the pass is evaluated in the
  layer's `render()` (after event dispatch, with the latest frame
  available). Evaluating at the end of an event pass in an underlay did not
  work.
* Swallow input with `raise renpy.display.core.IgnoreEvent()`.
* Wheel: old Ren'Py reports buttons 4/5 (`MOUSEBUTTONDOWN`); newer versions
  also send `MOUSEWHEEL` (`event.y`). Handle both in one function.
* Key held: `pygame.key.get_mods()` with `KMOD_SHIFT/ALT/CTRL`; import
  `pygame_sdl2 as pygame`, falling back to `pygame` for 6.x.
* Card Text: set **every** style property explicitly (font, size, color,
  bold, outlines, drop_shadow, kerning, spacing, alignment, indents…) so the
  game's styles can't leak in; `substitute=False` (no `[variable]`
  interpolation); escape `{` as `{{`; on 7.4+ set `adjust_spacing=False`
  (otherwise letter spacing looks off).
* Measure text with `renpy.display.render.render(text, width, height, 0, 0)`;
  backgrounds with `renpy.display.imagelike.Solid`; scrolling by rendering
  the full content and blitting `content.subsurface((0, scroll, w, h))`.
* Coordinates are in the virtual resolution (`config.screen_width/height`).
  The window letterboxes the virtual screen, so test tools must map
  virtual → window coordinates with scale and offset.

### 2.5 Ren'Py testing notes

* Katawa Shoujo shows a ~15 s studio splash; wait before testing the menu.
* A restart script: kill the game, deploy, delete the mod log, start the
  game, wait until the mod logs "installed" or `traceback.txt` appears.
* Ren'Py 7 with Python 2 writes `.pyo` files next to the mod's modules, and
  every run writes `log.txt` (with hardware info), `game/cache`, saves and
  persistent data (in the game folder and under `%APPDATA%\RenPy`).
* A crash at startup leaves `traceback.txt` in the game folder (and opens it
  in Notepad).

---

## 3. Specific to Python

### 3.1 One codebase for Python 2.7 and 3

* `from __future__ import unicode_literals, division, absolute_import`.
* `struct.Struct(str("<I"))`: Python 2.7.3's struct rejects a unicode
  format string.
* `unichr` raises ValueError above U+FFFF on narrow builds (Ren'Py 6's
  Python): fall back to U+FFFD. pyflakes reports `unichr` as undefined
  (false alarm on Python 3).
* No f-strings, no `subTest` (2.7.3), no `exist_ok` in the shared code;
  `io.open(..., encoding="utf-8")` for text files; avoid `u''` reprs in
  user-facing output (format strings with `%s`).
* Running a game's own Python 2.7 for tests:
  `PYTHONHOME=<game>/lib/windows-i686 PYTHONPATH="<game>/lib/windows-i686/Lib;<game>/lib/pythonlib2.7" <game>/lib/windows-i686/python.exe -B -O tests/run_tests.py`
  (`-O` because only `.pyo` files ship; `-B` and `sys.dont_write_bytecode`
  keep `__pycache__`/`.pyc` out of the mod folder).
* The build script may be Python 3 only (it never runs inside the game).

### 3.2 Useful idioms

* `collections.namedtuple` for rules and verb classes (readable, hashable,
  works on 2.7).
* Named constants for positions in compact lists, documented next to the
  format.
* `xml.etree.ElementTree.iterparse` + `element.clear()` to stream the 58 MB
  JMdict XML.
* `weakref.ref` + `id()` maps to remember engine objects without keeping
  them alive; `collections.OrderedDict` as a small LRU (`popitem(last=False)`).

### 3.3 Data format without SQLite

* `keys.dat`: lines `key<TAB>id,id,…` sorted by UTF-8 bytes (byte order =
  code point order); `keys.idx`: uint32 offsets of each line → binary search
  reading one line per step (about 19 reads).
* `entries.dat`: zlib-compressed blocks of 32 JSON lines; `entries.idx`:
  block offsets (+ end). One lookup decompresses one small block.
* Caches: looked-up keys and decompressed blocks, cleared when large.
* Compact JSON keys (`k`, `r`, `s`, `g`, `p`…) keep the files small; the
  reader names every field and position.

---

## 4. Checklist for a new game or engine

1. Ask the questions in 1.2 (scope, architecture, dictionary, language,
   card, key, test game, license, names). Recommend an option for each.
2. Back up the game and its saves; verify the backup.
3. Research the engine:
   * Can a mod run code inside the game, and in which language/version?
   * How does text reach the screen: real text with glyph positions, or
     images/bitmap fonts? Where can glyph geometry be read?
   * How can a layer be drawn above everything (menus included), and
     receive input before the game?
   * What breaks across engine versions?
   Present findings and a plan before building.
4. Prototype hit testing on dialogue, menus and settings first.
5. Reuse `yomi_core.py`, `build_dict.py` and the tests as they are if the
   engine runs Python. Otherwise port `yomi_core.py` with its tests as the
   specification; the data format is trivial to read in any language.
6. Rewrite only the engine part: loading, hit testing, overlay, input,
   card drawing, logging that can never crash the game.
7. Test-drive the real game (input simulation + screenshots + the mod's
   log) on several engine versions.
8. Tests, review, packaging, licenses, privacy cleanup (1.8–1.11).

---

## 5. Quick reference (this repository)

```
python utils/build_dict.py                 build yomi/data from assets/
python tests/run_tests.py [topic]          tests (also run with a game's Python 2.7)
utils/deploy.sh "<game folder>"            copy the mod into a game
utils/restart_ks.ps1 [-Root <folder>]      deploy + restart Katawa Shoujo (found via Steam)
utils/restart_game.ps1 -Root … -Exe … [-ExeArgs …] -Process …
. utils/gamectl.ps1                        Focus-Game, Glide-V, Click-V, Wheel, Key-Down/Up, Press, Shot
bash utils/package.sh [version]            dist/yomi-renpy-<version>.zip
```

Status at the time of writing: v0.1 works on Ren'Py 6.16, 7.8 and 8.5;
218 test checks on Python 3 and 196 on Python 2.7 pass, with 6 known
ranking issues recorded. Open decisions for the user: a word-frequency list
for ranking; handling noun + する as one verb.
