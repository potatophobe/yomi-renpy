# Yomi for Ren'Py

A drop-in mod that adds a Yomitan-style hover dictionary to (ideally) any
Ren'Py visual novel: hold Shift, point at Japanese text, get a card with
furigana, meanings and deinflection. User documentation: `yomi/README.txt`.

## Layout

| Path | What |
|---|---|
| `yomi/` | The mod itself (what gets copied into `game/`) |
| `yomi/yomi.rpy` | Entry point and user settings; loads the modules safely |
| `yomi/yomi_renpy.py` | Ren'Py integration: hit testing, card UI |
| `yomi/yomi_core.py` | Pure-Python dictionary reader, deinflector, scanner, card text (no Ren'Py) |
| `yomi/data/` | Built dictionary (generated) |
| `utils/build_dict.py` | Builds `yomi/data/` from the sources in `assets/` |
| `utils/deploy.sh` | Copies the mod into a game: `utils/deploy.sh "<game root>"` |
| `utils/package.sh` | Builds `dist/yomi-<version>.zip` |
| `utils/restart_game.ps1` | Deploys the mod to a game and restarts it, waiting until the mod has loaded |
| `utils/restart_ks.ps1` | The same for Katawa Shoujo, found in your Steam libraries (or pass `-Root`) |
| `utils/gamectl.ps1` | Drives a game window for manual checks: focus, mouse, keys, screenshots |
| `tests/` | Tests of everything in `yomi_core.py` and the build; see below |
| `sdk/` | Ren'Py 7.8.7 / 8.5.3 SDKs and The Question test copies |

## How it works

* **Finding the text under the mouse.** A displayable added to
  `renpy.display.emulator.overlay` (drawn above everything, including menus)
  sees every event first. When the scan key is held and the mouse moves, it
  redraws itself; while rendering, it walks the render tree of the last
  frame (`renpy.display.render.screen_render`), using `render_of` to find
  Text renders and the `forward`/`reverse` matrices to map the mouse into
  each one, like Ren'Py's own focus code. Hooking `Text.event` doesn't work:
  custom displayables (e.g. Katawa Shoujo's menus) don't forward events.
* **Glyph geometry.** `Text.render` is wrapped to snapshot each layout's glyph
  positions per render, because Ren'Py drops layouts from its cache after a
  frame or two while cached renders stay on screen. Snapshots hold no
  textures.
* **Lookup.** Like Yomitan: from the hovered character, try the longest
  prefix first, undo conjugations with a rule table (written for this
  project), and keep candidates whose part of speech matches.
* **Data.** No sqlite3 in old Ren'Py, so the dictionary is a sorted key file
  searched by binary search plus zlib-compressed entry blocks. ~29 MB on
  disk, almost nothing in memory.
* **Compatibility.** All code runs on Python 2.7 and 3. Tested on Ren'Py
  6.16.5 (Katawa Shoujo), 7.8.7 and 8.5.3 (The Question in Japanese).

## Rebuilding the dictionary

Sources go in `assets/`:

* `dictionaries/JMdict_e.gz` from http://ftp.edrdg.org/pub/Nihongo/JMdict_e.gz (English JMdict, kept compressed)
* `furigana/JmdictFurigana.json` from https://github.com/Doublevil/JmdictFurigana/releases

Then `python utils/build_dict.py`.

## Tests

```
python tests/run_tests.py            # everything
python tests/run_tests.py ranking    # only files whose name contains "ranking"
```

The results are grouped by topic, one line per case (`ok`, `FAIL` with the
expected and actual values, or `known` for a recorded limitation). Each file
is a set of tables you can read as a specification:

| File | What it checks |
|---|---|
| `test_scanning.py` | Which text is looked up from the hovered character |
| `test_conjugation.py` | Conjugated words lead to the dictionary form, with the right steps |
| `test_ranking.py` | Which results are listed, and in which order |
| `test_card_content.py` | Headword, furigana, "also:", meanings, labels, notes, escaping |
| `test_dictionary_files.py` | The built `yomi/data` and the reader, including archived games |
| `test_build.py` | `utils/build_dict.py` on a tiny hand-written JMdict (Python 3 only) |
| `test_mod_files.py` | Every `.py` file of the mod compiles (catches errors in `yomi_renpy.py` too) |

The mod also runs on Python 2.7 (Ren'Py 6 and 7), so run the tests with a
game's Python 2.7 too. For Katawa Shoujo (from Git Bash):

```
KS="<your Katawa Shoujo folder>"   # e.g. .../steamapps/common/Katawa Shoujo
PYTHONHOME="$KS/lib/windows-i686" PYTHONPATH="$KS/lib/windows-i686/Lib;$KS/lib/pythonlib2.7" \
    "$KS/lib/windows-i686/python.exe" -B -O tests/run_tests.py
```

The Ren'Py side (`yomi_renpy.py`: hit testing, the card, keys) has no
automated tests; check it in a game with `utils/restart_game.ps1` and
`utils/gamectl.ps1`.

## License

The code (the mod in `yomi/`, `utils/` and `tests/`) is under the MIT
License, see `LICENSE`. The rest keeps its own license:

* `yomi/data/` is built from JMdict and JmdictFurigana, so it is under
  CC BY-SA 4.0 like them.
* `yomi/fonts/` holds Noto Sans JP, under the SIL Open Font License 1.1.
* `assets/` holds the unmodified downloads the build uses: JMdict and
  JmdictFurigana (CC BY-SA 4.0) and Noto Sans JP (SIL OFL 1.1, see
  `assets/fonts/LICENSE`).

`yomi/LICENSES.txt`, which ships with the mod, repeats the MIT text and lists
these; `tests/test_mod_files.py` checks that its MIT text matches `LICENSE`.
