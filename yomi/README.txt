Yomi - hover dictionary for Ren'Py games
=========================================

Learn Japanese while you read: hold Shift and point at any Japanese text in a
Ren'Py game (dialogue, choices, menus, settings...) to see a dictionary card
with furigana, meanings, part of speech and the conjugation that was undone
(e.g. 落ちた -> 落ちる « past). Works offline. Inspired by Yomitan.


Install
-------
1. Find the game's folder: the one that contains a "game" folder (for Steam
   games: right click the game > Manage > Browse local files).
2. Copy this whole "yomi" folder into that "game" folder, so you get
   <game folder>/game/yomi/yomi.rpy
3. Start the game.

To uninstall, delete the game/yomi folder.

Tested with Ren'Py 6.16 (Katawa Shoujo), 7.8 and 8.5. Should work with any
Ren'Py game from 6.15 on, as long as its text is real text (not images).


Use
---
  Hold Shift + point at a word ...... show the card for the word
  Mouse wheel over the card ......... scroll through the results
  Esc, or click the card ............ close it (doesn't advance the dialogue)
  Move the mouse away ............... close it

The card stays open after you release Shift, so you can move onto it and
scroll. Results are listed longest match first, like Yomitan.


Settings
--------
Open game/yomi/yomi.rpy in a text editor, uncomment (remove the "# " in
front of) a setting and change it:

  settings.key = "shift"   key to hold: "shift", "alt", "ctrl" or "always"
                           ("ctrl" is Ren'Py's skip key; avoid it)
  settings.scale = 1.0     card size
  settings.width = 0.46    card width, as a fraction of the screen width
  settings.debug = True    write each lookup to game/yomi/yomi_log.txt

More settings (colors, number of results) are in the Config class at the top
of yomi_renpy.py and can be set the same way, e.g. settings.max_results = 10.


Troubleshooting
---------------
* Nothing happens: look at game/yomi/yomi_log.txt. If the mod failed to load,
  the error is there (the game itself still starts).
* Text drawn as images (some titles, logos, buttons) can't be looked up.
* If the game ships its scripts inside an .rpa archive, that's fine; the yomi
  folder just has to be a normal folder next to them.


Credits and licenses
--------------------
See LICENSES.txt. Yomi's code: MIT License, (c) 2026 potatophobe.
Dictionary: JMdict (EDRDG, CC BY-SA 4.0); furigana: JmdictFurigana
(CC BY-SA 4.0); font: Noto Sans JP (SIL OFL 1.1).
