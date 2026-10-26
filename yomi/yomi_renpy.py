# -*- coding: utf-8 -*-
"""
Yomi: Ren'Py integration (hover detection, popup card).

How it works:

* A displayable in renpy.display.emulator.overlay (drawn above everything,
  including menus) receives every event first. When the scan key is held
  and the mouse moves, it asks to be redrawn; while rendering, it walks the
  render tree of the last frame to find the Text and glyph under the mouse
  (like Ren'Py's focus code does), looks the word up and draws the card.

* It also swallows wheel/clicks/Esc aimed at an open card, so reading the
  card doesn't scroll back or advance the dialogue.

Works on Python 2.7 and 3, Ren'Py 6.x - 8.x.
"""

from __future__ import unicode_literals, division

import collections
import io
import os
import sys
import time
import traceback
import weakref

import renpy
import renpy.display
import renpy.display.core
import renpy.display.render
import renpy.display.imagelike
import renpy.text.text

try:
    import pygame_sdl2 as pygame
except ImportError:
    import pygame

import yomi_core as core


################################################################################
# Files. Paths are relative to the game directory, with "/" as Ren'Py's
# loader expects.

MOD_DIRECTORY = "yomi"
DATA_DIRECTORY = MOD_DIRECTORY + "/data"
FONT_DIRECTORY = MOD_DIRECTORY + "/fonts"
LOG_FILE = MOD_DIRECTORY + "/yomi_log.txt"


################################################################################
# Configuration. Change these from yomi.rpy.

class Config(object):

    # Key that must be held to scan: "shift", "alt", "ctrl" or "always".
    key = "shift"

    # Fonts.
    font = FONT_DIRECTORY + "/NotoSansJP-Regular.otf"
    bold_font = FONT_DIRECTORY + "/NotoSansJP-Bold.otf"

    # Size multiplier for the card.
    scale = 1.0

    # Card width as a fraction of the screen width, and maximum height as a
    # fraction of the screen height.
    width = 0.46
    max_height = 0.62

    # Maximum number of dictionary entries on a card.
    max_results = core.MAX_RESULTS

    # Maximum number of characters scanned from the hovered one.
    max_length = core.MAX_SCAN_LENGTH

    # Colors.
    background = "#16181dee"
    border = "#4a5060"
    separator = "#353a45"
    text_color = "#e9e9ec"
    dim_color = "#9aa1ad"
    headword_color = "#ffffff"
    reading_color = "#b9c3d3"
    reason_color = "#f3c66f"
    part_of_speech_color = "#82b4ff"
    common_color = "#6fcf8f"
    highlight = "#ffd54a55"

    # Swallow clicks on the card / highlighted word, so reading the card
    # doesn't advance the dialogue.
    consume_clicks = True

    # Write each lookup to yomi/yomi_log.txt (errors are always written).
    debug = False


config = Config()


################################################################################
# Logging (never crash the game).

def log(message):
    try:
        path = os.path.join(renpy.config.gamedir, LOG_FILE)
        with io.open(path, "a", encoding="utf-8") as f:
            f.write("%s %s\n" % (time.strftime("%H:%M:%S"), message))
    except Exception:
        pass


def debug(message):
    if config.debug:
        log(message)


def log_exception(where):
    log("Error in %s:\n%s" % (where, traceback.format_exc()))


################################################################################
# Dictionary.

_dictionary = None


def get_dictionary():
    global _dictionary

    if _dictionary is None:
        directory = os.path.join(renpy.config.gamedir, DATA_DIRECTORY)

        if os.path.exists(os.path.join(directory, core.META_FILE)):
            _dictionary = core.Dictionary(directory)
        else:
            # The game keeps the mod inside an archive.
            _dictionary = core.Dictionary(
                directory, lambda name: renpy.loader.load(DATA_DIRECTORY + "/" + name))

    return _dictionary


################################################################################
# Finding the text under the mouse.
#
# Rather than relying on events reaching each Text (custom displayables,
# like Katawa Shoujo's main menu, don't pass them on), we walk the render
# tree of the last drawn frame, the same way Ren'Py computes focus
# rectangles. This finds every Text that is actually on screen.

# Remembered Text renders, and the number of glyph snapshots above which
# snapshots of layouts that no longer exist are cleaned up.
RENDERS_REMEMBERED = 3000
SNAPSHOTS_BEFORE_CLEANUP = 500

# Render trees deeper than this are cut off (protects against cycles).
MAX_RENDER_DEPTH = 100

# Shown in the looked-up text for a glyph that isn't a character (an image
# inside the text).
OBJECT_REPLACEMENT_CHARACTER = "\ufffc"

# Highlight rectangles of neighbouring glyphs closer than these (pixels) are
# merged into one.
SAME_LINE_TOLERANCE = 1
NEIGHBOUR_TOLERANCE = 2


class GlyphInfo(object):
    __slots__ = ("x", "extent", "character")

    def __init__(self, glyph):
        self.x = glyph.x
        # The glyph's box: its advance, or its ink if that is wider.
        self.extent = max(glyph.advance, glyph.width)
        self.character = glyph.character


class LineInfo(object):
    __slots__ = ("y", "height", "ends_paragraph", "glyphs")

    def __init__(self, line):
        self.y = line.y
        self.height = line.height
        self.ends_paragraph = line.eop
        self.glyphs = [GlyphInfo(glyph) for glyph in line.glyphs]


class Snapshot(object):
    """
    The geometry of a text Layout (glyph positions and characters). Layouts
    own textures, so we keep this copy rather than the Layout itself.
    """

    def __init__(self, layout):
        self.xoffset = layout.xoffset
        self.yoffset = layout.yoffset
        self.lines = [LineInfo(line) for line in layout.lines]


# Snapshots of recent layouts: id(layout) -> (weakref(layout), Snapshot).
_snapshots = {}

# id(render) -> (weakref(text), width, height, Snapshot) for recently
# rendered Text. Ren'Py only keeps a Text's layout for a frame or two, but a
# render can stay on screen much longer through the render cache, so we
# remember what produced each render ourselves.
_renders = collections.OrderedDict()


def _snapshot(layout):
    key = id(layout)
    known = _snapshots.get(key)
    if known is not None and known[0]() is layout:
        return known[1]

    if len(_snapshots) > SNAPSHOTS_BEFORE_CLEANUP:
        for old_key, (reference, _) in list(_snapshots.items()):
            if reference() is None:
                del _snapshots[old_key]

    rv = Snapshot(layout)
    _snapshots[key] = (weakref.ref(layout), rv)
    return rv


def _remember_layout(render, text):
    layout = text.get_layout()
    if layout is None:
        return

    key = id(render)
    _renders.pop(key, None)
    _renders[key] = (weakref.ref(text), render.width, render.height, _snapshot(layout))

    while len(_renders) > RENDERS_REMEMBERED:
        _renders.popitem(last=False)


def _layout_for(render, text):
    """The Snapshot of the layout that produced `render` from `text`, or None."""
    remembered = _renders.get(id(render))
    if remembered is None:
        return None
    reference, width, height, snapshot = remembered
    if reference() is not text or width != render.width or height != render.height:
        return None
    return snapshot


def _wrap_text_render(original):

    def render(self, width, height, st, at):
        rv = original(self, width, height, st, at)
        try:
            _remember_layout(rv, self)
        except Exception:
            pass
        return rv

    render._yomi_wrapped = True
    return render


def _transform(matrix, x, y):
    rv = matrix.transform(x, y)
    return rv[0], rv[1]


IDENTITY = renpy.display.render.Matrix2D(1, 0, 0, 1)


class Placed(object):
    """A Text render placed on screen."""

    def __init__(self, text, layout, x, y, forward, reverse):
        self.text = text
        self.layout = layout
        # Screen position of the render's origin.
        self.x = x
        self.y = y
        # Screen -> render and render -> screen transforms.
        self.forward = forward
        self.reverse = reverse

    def to_local(self, screen_x, screen_y):
        return _transform(self.forward, screen_x - self.x, screen_y - self.y)

    def to_screen(self, local_x, local_y):
        x, y = _transform(self.reverse, local_x, local_y)
        return self.x + x, self.y + y


def placed_texts(root, skip):
    """
    Returns a list of Placed for every Text render in the tree under `root`,
    in drawing order (topmost last). Subtrees rendered by `skip` are ignored.
    """

    Text = renpy.text.text.Text
    Render = renpy.display.render.Render
    rv = []

    def walk(render, x, y, forward, reverse, depth):
        if depth > MAX_RENDER_DEPTH:
            return

        displayables = render.render_of or ()
        # By identity: Ren'Py displayables can define their own equality.
        if any(displayable is skip for displayable in displayables):
            return

        if render.forward is not None:
            forward = render.forward * forward
        if render.reverse is not None:
            reverse = reverse * render.reverse

        for displayable in displayables:
            if isinstance(displayable, Text):
                layout = _layout_for(render, displayable)
                if layout is not None:
                    rv.append(Placed(displayable, layout, x, y, forward, reverse))
                    return
                # Otherwise (e.g. a clipping wrapper), look at the children.

        for child, child_x, child_y, _focus, _main in render.children:
            if not isinstance(child, Render):
                continue
            offset_x, offset_y = _transform(reverse, child_x, child_y)
            walk(child, x + offset_x, y + offset_y, forward, reverse, depth + 1)

    if root is not None:
        walk(root, 0, 0, IDENTITY, IDENTITY, 0)

    return rv


def glyph_at(layout, x, y):
    """
    Returns (line_index, glyph_index) of the glyph at layout coordinates
    (x, y), or None.
    """

    for line_index, line in enumerate(layout.lines):
        if not (line.y <= y < line.y + line.height):
            continue

        for glyph_index, glyph in enumerate(line.glyphs):
            if glyph.x <= x < glyph.x + glyph.extent:
                return line_index, glyph_index

        return None

    return None


def paragraph(layout, line_index, glyph_index):
    """
    Returns (text, glyphs, index): the text of the paragraph containing the
    glyph, the list of (line, glyph) pairs for each character, and the
    index of the glyph in the text.
    """

    lines = layout.lines

    start = line_index
    while start > 0 and not lines[start - 1].ends_paragraph:
        start -= 1

    end = line_index
    while end < len(lines) - 1 and not lines[end].ends_paragraph:
        end += 1

    characters = []
    glyphs = []
    index = 0

    for current_line in range(start, end + 1):
        line = lines[current_line]
        for current_glyph, glyph in enumerate(line.glyphs):
            if current_line == line_index and current_glyph == glyph_index:
                index = len(characters)
            if glyph.character:
                characters.append(core.character_from_code(glyph.character))
            else:
                characters.append(OBJECT_REPLACEMENT_CHARACTER)
            glyphs.append((line, glyph))

    return "".join(characters), glyphs, index


class Hit(object):
    """The glyph under the mouse."""

    def __init__(self, placed, line_index, glyph_index):
        self.placed = placed
        self.text = placed.text
        self.layout = placed.layout
        self.line_index = line_index
        self.glyph_index = glyph_index


def find_hit(texts, screen_x, screen_y):
    """Returns the Hit for the topmost glyph at the screen position, or None."""

    for placed in reversed(texts):
        layout = placed.layout
        local_x, local_y = placed.to_local(screen_x, screen_y)
        found = glyph_at(layout, local_x - layout.xoffset, local_y - layout.yoffset)
        if found is not None:
            return Hit(placed, *found)

    return None


def word_rects(hit, glyphs, index, length):
    """Screen rectangles (x, y, w, h) covering the matched characters."""

    layout = hit.layout
    rv = []

    for line, glyph in glyphs[index:index + length]:
        left = layout.xoffset + glyph.x
        top = layout.yoffset + line.y
        x0, y0 = hit.placed.to_screen(left, top)
        x1, y1 = hit.placed.to_screen(left + glyph.extent, top + line.height)
        x0, x1 = min(x0, x1), max(x0, x1)
        y0, y1 = min(y0, y1), max(y0, y1)

        if rv:
            last_x, last_y, last_w, last_h = rv[-1]
            same_line = abs(last_y - y0) < SAME_LINE_TOLERANCE
            touching = abs(last_x + last_w - x0) < NEIGHBOUR_TOLERANCE
            if same_line and touching:
                rv[-1] = (last_x, last_y, x1 - last_x, max(last_h, y1 - y0))
                continue

        rv.append((x0, y0, x1 - x0, y1 - y0))

    return rv


################################################################################
# State.

# Distance (pixels) around the highlighted word within which the mouse
# still counts as being over it.
WORD_MARGIN = 4

# Evaluations in a row without the card's text on screen before the card is
# hidden (one miss can happen while the screen is redrawn).
MISSES_BEFORE_HIDE = 2


class State(object):
    """
    The card layer receives every event first. Mouse motion and key events
    start a "pass"; the pass is evaluated when the card layer is next
    rendered, by hit-testing the last drawn frame.
    """

    def __init__(self):
        # The mouse position of the latest pass.
        self.mouse_x = 0
        self.mouse_y = 0

        # Serial numbers of the latest and of the last evaluated pass.
        self.serial = 0
        self.evaluated = 0

        # Evaluations in a row where the card's Text wasn't on screen.
        self.missed = 0

        self.card = None

        # Set after an error in event handling, to keep the game playable.
        self.disabled = False

    def key_held(self):
        if config.key == "always":
            return True

        modifiers = pygame.key.get_mods()
        if config.key == "alt":
            return bool(modifiers & pygame.KMOD_ALT)
        elif config.key == "ctrl":
            return bool(modifiers & pygame.KMOD_CTRL)
        else:
            return bool(modifiers & pygame.KMOD_SHIFT)

    def begin_pass(self, event, x, y):
        if self.disabled:
            return

        if event.type not in (pygame.MOUSEMOTION, pygame.KEYDOWN, pygame.KEYUP):
            return

        if self.card is None and not self.key_held():
            return

        self.serial += 1
        self.mouse_x = x
        self.mouse_y = y
        renpy.display.render.redraw(card_layer, 0)

    def evaluate(self):
        """Evaluates the latest pass. Called from the card layer's render."""

        if self.evaluated == self.serial:
            return
        self.evaluated = self.serial

        x = self.mouse_x
        y = self.mouse_y
        card = self.card

        texts = placed_texts(renpy.display.render.screen_render, card_layer)

        # Hide the card once its text is gone (e.g. the dialogue advanced).
        if card is not None:
            if any(placed.text is card.hit.text for placed in texts):
                self.missed = 0
            else:
                self.missed += 1
                if self.missed >= MISSES_BEFORE_HIDE:
                    self.hide()
                    card = None

        if card is not None and card.contains(x, y):
            return

        hit = find_hit(texts, x, y) if self.key_held() else None

        if hit is not None:
            text, glyphs, index = paragraph(hit.layout, hit.line_index, hit.glyph_index)
            key = (id(hit.text), text, index)

            if card is not None and card.key == key:
                return

            matches = core.lookup(get_dictionary(), text, index,
                                  config.max_length, config.max_results)
            if config.debug:
                debug("lookup \"%s\" at %d: %s" % (
                    text.replace("\n", " "), index,
                    ", ".join(core.headword(match)[0] for match in matches) or "nothing"))

            if matches:
                rects = word_rects(hit, glyphs, index, matches[0].length)
                self.show(Card(key, hit, matches, rects))
                return

        if card is not None and not card.over_word(x, y):
            self.hide()

    def show(self, card):
        self.card = card
        self.missed = 0
        renpy.display.render.redraw(card_layer, 0)

    def hide(self):
        if self.card is not None:
            self.card = None
            renpy.display.render.redraw(card_layer, 0)


state = State()


################################################################################
# Card.
#
# Sizes are in units of the card's base font size, which follows the screen
# height so the card looks the same at any resolution.

# Base font size: the screen height divided by this, times config.scale.
SCREEN_HEIGHTS_PER_FONT_SIZE = 34
MIN_FONT_SIZE = 9          # pixels, for the base font
MIN_TEXT_SIZE = 6          # pixels, for any text

# Card width limits (the preferred width is config.width).
MIN_CARD_WIDTH = 17
MAX_CARD_WIDTH = 32

PADDING = 0.7              # inside the card's edges
HEADWORD_SIZE = 1.55
READING_SIZE = 0.72        # furigana
NOTE_SIZE = 0.8            # tags, "also:", part of speech, notes
READING_LINE_HEIGHT = 1.2  # × READING_SIZE
HEADWORD_LINE_HEIGHT = 1.45  # × HEADWORD_SIZE
TAG_SPACING = 0.6          # between the headword and its tags, and between tags
TAG_DROP = 0.55            # moves the smaller tag text down toward the headword's baseline
SPACE_ABOVE_SEPARATOR = 0.35
SPACE_BELOW_SEPARATOR = 0.45
GAP_TO_WORD = 0.3          # between the card and the highlighted word
MIN_SCROLLBAR_LENGTH = 1   # the scrollbar never gets shorter than this

MAX_OTHER_FORMS = 6        # spellings on the "also:" line
SENSE_NUMBER_SAMPLE = "00."  # the widest sense number, to align the meanings

# Pixels.
BORDER_WIDTH = 1
SEPARATOR_HEIGHT = 1
SCROLLBAR_WIDTH = 3
SCROLLBAR_MARGIN = 2       # between the scrollbar and the card's right edge

# Mouse wheel: one notch scrolls this fraction of the visible height, at
# least MIN_SCROLL_STEP pixels.
SCROLL_STEP = 0.15
MIN_SCROLL_STEP = 20

# Size used to render text when only its natural size matters.
UNLIMITED = 4096

# Style properties that only exist in newer Ren'Py versions.
_extra_text_properties = {}
if getattr(renpy, "version_tuple", (0,)) >= (7, 4):
    # Ren'Py 7.4+ tweaks letter spacing to match the virtual resolution;
    # the card looks better without it.
    _extra_text_properties["adjust_spacing"] = False


def make_text(text, size, color, bold=False):
    """
    A Text with every style property set, so the game's own text styles
    can't change how the card looks. `bold` selects the bold font.
    """
    return renpy.text.text.Text(
        core.escape_text_tags(text),
        substitute=False,
        slow=False,
        font=config.bold_font if bold else config.font,
        size=max(int(size), MIN_TEXT_SIZE),
        color=color,
        bold=False,
        italic=False,
        underline=False,
        strikethrough=False,
        outlines=[],
        drop_shadow=None,
        kerning=0,
        line_spacing=0,
        text_align=0,
        first_indent=0,
        rest_indent=0,
        justify=False,
        min_width=0,
        **_extra_text_properties
        )


def make_solid(color):
    return renpy.display.imagelike.Solid(color)


def render_child(displayable, width, height, st, at):
    return renpy.display.render.render(displayable, int(width), int(height), st, at)


def text_width(text, size, bold=False):
    displayable = make_text(text, size, config.text_color, bold)
    return int(render_child(displayable, UNLIMITED, UNLIMITED, 0, 0).width)


def text_height(displayable, width):
    return int(render_child(displayable, width, UNLIMITED, 0, 0).height)


class CardContent(object):
    """
    Lays out the card's content in a column `width` pixels wide: a list of
    (displayable, x, y, width, height) items. Text items have height None
    (natural height).
    """

    def __init__(self, width, font_size):
        self.width = width
        self.font_size = font_size
        self.padding = int(font_size * PADDING)
        self.inner_width = width - 2 * self.padding
        self.items = []
        self.y = self.padding

        self.headword_size = font_size * HEADWORD_SIZE
        self.reading_size = font_size * READING_SIZE
        self.note_size = font_size * NOTE_SIZE

    def place(self, displayable, x, y, width=None, height=None):
        self.items.append((displayable, x, y, width, height))

    def add_paragraph(self, text, size, color, x):
        """Adds wrapped text at the current line and moves below it."""
        displayable = make_text(text, size, color)
        width = self.width - x - self.padding
        self.place(displayable, x, self.y, width)
        self.y += text_height(displayable, width)

    def add_separator(self):
        self.y += int(self.font_size * SPACE_ABOVE_SEPARATOR)
        self.place(make_solid(config.separator), self.padding, self.y, self.inner_width, SEPARATOR_HEIGHT)
        self.y += int(self.font_size * SPACE_BELOW_SEPARATOR)

    def add_match(self, match, descriptions):
        reading_height, headword_right = self.add_headword(match)
        self.add_tags(match, headword_right, reading_height)
        self.y += reading_height + int(self.headword_size * HEADWORD_LINE_HEIGHT)

        others = core.other_forms(match)
        if others:
            self.add_paragraph("also: " + "、".join(others[:MAX_OTHER_FORMS]),
                               self.note_size, config.dim_color, self.padding)

        self.add_senses(match, descriptions)

    def add_headword(self, match):
        """
        Adds the headword with furigana centred over each segment. Returns
        the height of the furigana row (0 if none) and the headword's right
        edge.
        """

        _form, _reading, segments = core.headword(match)
        has_furigana = any(len(segment) > 1 and segment[1] for segment in segments)
        reading_height = int(self.reading_size * READING_LINE_HEIGHT) if has_furigana else 0

        x = self.padding
        for segment in segments:
            text = segment[0]
            reading = segment[1] if len(segment) > 1 else None

            width = text_width(text, self.headword_size, bold=True)
            reading_width = text_width(reading, self.reading_size) if reading else 0
            segment_width = max(width, reading_width)

            self.place(make_text(text, self.headword_size, config.headword_color, bold=True),
                       x + (segment_width - width) // 2, self.y + reading_height)
            if reading:
                self.place(make_text(reading, self.reading_size, config.reading_color),
                           x + (segment_width - reading_width) // 2, self.y)
            x += segment_width

        return reading_height, x

    def add_tags(self, match, x, reading_height):
        """Adds "common" and the undone conjugation steps beside the headword."""

        tags = []
        if core.is_common(match):
            tags.append(("common", config.common_color))
        if match.reasons:
            tags.append(("« " + " « ".join(match.reasons), config.reason_color))

        spacing = int(self.font_size * TAG_SPACING)
        x += spacing
        y = self.y + reading_height + int((self.headword_size - self.note_size) * TAG_DROP)

        for label, color in tags:
            width = text_width(label, self.note_size)
            if x + width > self.width - self.padding:
                break
            self.place(make_text(label, self.note_size, color), x, y)
            x += width + spacing

    def add_senses(self, match, descriptions):
        """Adds the numbered meanings, each part-of-speech line, and notes."""

        number_width = text_width(SENSE_NUMBER_SAMPLE, self.font_size)
        meaning_x = self.padding + number_width
        last_parts_of_speech = None

        for number, sense in enumerate(core.senses(match), 1):
            parts_of_speech = sense.get(core.PARTS_OF_SPEECH)
            if parts_of_speech and parts_of_speech != last_parts_of_speech:
                self.add_paragraph(core.part_of_speech_text(parts_of_speech, descriptions),
                                   self.note_size, config.part_of_speech_color, self.padding)
                last_parts_of_speech = parts_of_speech

            self.place(make_text("%d." % number, self.font_size, config.dim_color), self.padding, self.y)
            self.add_paragraph("; ".join(sense[core.GLOSSES]), self.font_size, config.text_color, meaning_x)

            notes = core.sense_notes(sense, descriptions)
            if notes:
                self.add_paragraph("(" + "; ".join(notes) + ")", self.note_size, config.dim_color, meaning_x)


class Card(object):

    def __init__(self, key, hit, matches, rects):
        self.key = key
        self.hit = hit
        self.matches = matches
        self.rects = rects
        self.scroll = 0
        self.content_height = 0
        self.view_height = 0
        self.rect = (0, 0, 0, 0)
        self.items = None
        self.items_width = None

    # Geometry.

    def word_box(self):
        left = min(x for x, y, w, h in self.rects)
        top = min(y for x, y, w, h in self.rects)
        right = max(x + w for x, y, w, h in self.rects)
        bottom = max(y + h for x, y, w, h in self.rects)
        return left, top, right, bottom

    def contains(self, x, y):
        card_x, card_y, card_width, card_height = self.rect
        return card_x <= x < card_x + card_width and card_y <= y < card_y + card_height

    def over_word(self, x, y):
        for rect_x, rect_y, width, height in self.rects:
            if (rect_x - WORD_MARGIN <= x < rect_x + width + WORD_MARGIN
                    and rect_y - WORD_MARGIN <= y < rect_y + height + WORD_MARGIN):
                return True
        return False

    def scroll_by(self, pixels):
        """Scrolls the content; returns True if the position changed."""
        old = self.scroll
        limit = max(0, self.content_height - self.view_height)
        self.scroll = int(min(max(self.scroll + pixels, 0), limit))
        return self.scroll != old

    def scroll_notches(self, notches):
        """Scrolls by mouse-wheel notches (negative = up)."""
        step = int(self.view_height * SCROLL_STEP) or MIN_SCROLL_STEP
        return self.scroll_by(step * notches)

    # Content.

    def build(self, width, font_size):
        content = CardContent(width, font_size)
        descriptions = get_dictionary().tags

        for number, match in enumerate(self.matches):
            if number:
                content.add_separator()
            content.add_match(match, descriptions)

        self.items = content.items
        self.content_height = content.y + content.padding
        self.items_width = width

    def render(self, screen_width, screen_height, st, at):
        font_size = max(int(screen_height / SCREEN_HEIGHTS_PER_FONT_SIZE * config.scale), MIN_FONT_SIZE)
        width = int(min(max(screen_width * config.width, font_size * MIN_CARD_WIDTH),
                        font_size * MAX_CARD_WIDTH, screen_width))

        if self.items is None or self.items_width != width:
            self.build(width, font_size)

        self.view_height = min(self.content_height, int(screen_height * config.max_height))
        self.scroll_by(0)
        height = self.view_height

        content = renpy.display.render.Render(width, self.content_height)
        for displayable, x, y, item_width, item_height in self.items:
            child = render_child(displayable, item_width or width, item_height or UNLIMITED, st, at)
            content.blit(child, (int(x), int(y)))

        rv = renpy.display.render.Render(width, height)
        rv.blit(render_child(make_solid(config.border), width, height, st, at), (0, 0))
        rv.blit(render_child(make_solid(config.background), width - 2 * BORDER_WIDTH,
                             height - 2 * BORDER_WIDTH, st, at), (BORDER_WIDTH, BORDER_WIDTH))
        rv.blit(content.subsurface((0, self.scroll, width, height)), (0, 0))

        if self.content_height > height:
            self.render_scrollbar(rv, width, height, int(font_size * MIN_SCROLLBAR_LENGTH), st, at)

        self.rect = self.position(screen_width, screen_height, width, height, font_size)
        return rv

    def render_scrollbar(self, rv, width, height, min_length, st, at):
        length = max(int(height * height / self.content_height), min_length)
        y = int((height - length) * self.scroll / (self.content_height - height))
        bar = render_child(make_solid(config.dim_color), SCROLLBAR_WIDTH, length, st, at)
        rv.blit(bar, (width - SCROLLBAR_WIDTH - SCROLLBAR_MARGIN, y))

    def position(self, screen_width, screen_height, width, height, font_size):
        """
        The card's screen rectangle: below the word if it fits, otherwise
        above, otherwise on the side of the screen with more room.
        """

        left, top, _right, bottom = self.word_box()
        gap = int(font_size * GAP_TO_WORD)

        if bottom + gap + height <= screen_height:
            y = bottom + gap
        elif top - gap - height >= 0:
            y = top - gap - height
        elif screen_height - bottom > top:
            y = screen_height - height
        else:
            y = 0

        x = min(max(int(left), 0), max(screen_width - width, 0))
        return (x, int(y), width, height)


################################################################################
# Displayables.

# Mouse buttons in pygame events. Old Ren'Py reports wheel notches as
# buttons 4 and 5; newer versions also send MOUSEWHEEL events.
CLICK_BUTTONS = (1, 2, 3)
WHEEL_UP_BUTTON = 4
WHEEL_DOWN_BUTTON = 5


def wheel_notches(event):
    """Mouse-wheel notches in `event` (negative = up), or 0."""
    if event.type == pygame.MOUSEBUTTONDOWN:
        if event.button == WHEEL_UP_BUTTON:
            return -1
        if event.button == WHEEL_DOWN_BUTTON:
            return 1
    mouse_wheel = getattr(pygame, "MOUSEWHEEL", None)
    if mouse_wheel is not None and event.type == mouse_wheel:
        return -event.y
    return 0


class CardLayer(renpy.display.core.Displayable):
    """Topmost layer: starts each event pass, draws highlight and card."""

    def event(self, event, x, y, st):
        try:
            state.begin_pass(event, x, y)
        except Exception:
            log_exception("begin_pass")
            state.disabled = True
            return None

        card = state.card
        if card is None:
            return None

        try:
            over_card = card.contains(x, y) or card.over_word(x, y)
            notches = wheel_notches(event)

            if notches:
                if over_card:
                    if card.scroll_notches(notches):
                        renpy.display.render.redraw(self, 0)
                    raise renpy.display.core.IgnoreEvent()

            elif (event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP)
                  and event.button in CLICK_BUTTONS):
                if over_card and config.consume_clicks:
                    if event.type == pygame.MOUSEBUTTONUP:
                        state.hide()
                    raise renpy.display.core.IgnoreEvent()

            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                state.hide()
                raise renpy.display.core.IgnoreEvent()

        except renpy.display.core.IgnoreEvent:
            raise
        except Exception:
            log_exception("card event")
            state.hide()

        return None

    def render(self, width, height, st, at):
        rv = renpy.display.render.Render(width, height)

        try:
            state.evaluate()
        except Exception:
            log_exception("evaluate")
            state.card = None

        card = state.card
        if card is None:
            return rv

        try:
            highlight = make_solid(config.highlight)
            for x, y, w, h in card.rects:
                rv.blit(render_child(highlight, w, h, st, at), (int(x), int(y)))

            card_render = card.render(renpy.config.screen_width, renpy.config.screen_height, st, at)
            rv.blit(card_render, card.rect[:2])
        except Exception:
            log_exception("card render")
            state.card = None

        return rv

card_layer = CardLayer()


def ensure_card_layer():
    emulator = getattr(renpy.display, "emulator", None)
    overlay = getattr(emulator, "overlay", None)
    # By identity: Ren'Py displayables can define their own equality.
    if isinstance(overlay, list) and not any(layer is card_layer for layer in overlay):
        overlay.append(card_layer)


def _overlay_function():
    import renpy.ui
    renpy.ui.add(card_layer)


def install():
    """Installs the hooks. Safe to call more than once (e.g. after reload)."""

    Text = renpy.text.text.Text
    if not getattr(Text.render, "_yomi_wrapped", False):
        Text.render = _wrap_text_render(Text.render)

    emulator = getattr(renpy.display, "emulator", None)

    if isinstance(getattr(emulator, "overlay", None), list):
        # The emulator overlay is drawn above everything, menus included. It
        # is replaced when the display is (re)initialized, so re-add the
        # card layer after that.
        init = getattr(emulator, "init_emulator", None)
        if init is not None and not getattr(init, "_yomi_wrapped", False):
            def init_emulator(*args, **kwargs):
                rv = init(*args, **kwargs)
                ensure_card_layer()
                return rv

            init_emulator._yomi_wrapped = True
            emulator.init_emulator = init_emulator

        ensure_card_layer()

    elif _overlay_function not in renpy.config.overlay_functions:
        # Ren'Py without the emulator overlay: an overlay function instead.
        renpy.config.overlay_functions.append(_overlay_function)

    log("installed (Ren'Py %s, Python %s)" % (renpy.version, sys.version.split()[0]))
