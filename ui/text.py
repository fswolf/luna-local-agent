"""Measuring and laying out text: display widths (wide characters and
emoji count double), wrapping, the key hints, and the frame drawn round
each pane.

Part of the ui package (it was one ui.py); see ui/__init__.py.
"""
import re

from prompt_toolkit.formatted_text import split_lines
from prompt_toolkit.layout import HSplit, VSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl

from .shared import view, wcswidth


# ---------------------------------------------------------------------------
# Text measuring / wrapping
# ---------------------------------------------------------------------------
def vwidth(s: str) -> int:
    """Visible width in terminal cells.

    Emoji and other wide characters break len()-based wrapping - an emoji
    is usually 2 cells but len() counts 1 - and Luna uses them, so
    measure properly when wcwidth is available.
    """
    if wcswidth is None:
        return len(s)

    w = wcswidth(s)

    return w if w is not None and w >= 0 else len(s)


def _wrap_text(text: str, width: int):
    """Word-wrap on visible width rather than character count."""
    words = text.split()

    if not words:
        return [""]

    lines = []
    current = []
    current_width = 0

    for word in words:
        w = vwidth(word)
        space = 1 if current else 0

        if current_width + space + w > width and current:
            lines.append(" ".join(current))
            current = [word]
            current_width = w
        else:
            current.append(word)
            current_width += space + w

    if current:
        lines.append(" ".join(current))

    return lines or [""]


def _width():
    if view.app is None:
        return 80

    # minus the frame's two borders and two padding columns
    return max(20, view.app.output.get_size().columns - 4)


def _rendered_lines(fragments):
    """How tall prompt_toolkit thinks this content is.

    Counting newlines ourselves is off by one whenever the last line
    ends in a newline - it opens a further line that nothing can scroll
    to, and the scrollbar sizes itself off the library's count rather
    than ours. Asking the library is the only way the two agree.
    """
    return len(list(split_lines(fragments)))


def _keyed(text, label_style="class:footer"):
    """Colour the (key) parts like sfav does, leave the labels muted."""
    fragments = []

    for piece in re.split(r"(\([^)]*\))", text):
        if not piece:
            continue

        style = "class:key" if piece.startswith("(") else label_style
        fragments.append((style, piece))

    return fragments


# ---------------------------------------------------------------------------
# Rounded frame
#
# prompt_toolkit's Frame draws square corners and centres the title
# between two rules, which renders as "───|  Title  |───". This draws
# rounded corners with the title sitting on the top rule, left-aligned,
# the way sfav does it.
# ---------------------------------------------------------------------------
_TOP_LEFT, _TOP_RIGHT = "╭", "╮"
_BOTTOM_LEFT, _BOTTOM_RIGHT = "╰", "╯"
_HORIZONTAL, _VERTICAL = "─", "│"


def _rule(char, width=None):
    return Window(char=char, style="class:frame.border", width=width, height=1)


def _framed(body, title=None):
    if title is None:
        top = VSplit([
            _rule(_TOP_LEFT, 1), _rule(_HORIZONTAL), _rule(_TOP_RIGHT, 1),
        ], height=1)
    else:
        def label():
            text = title() if callable(title) else title
            return [("class:frame.label", f" {text} ")]

        top = VSplit([
            _rule(_TOP_LEFT, 1),
            _rule(_HORIZONTAL, 1),
            Window(
                content=FormattedTextControl(label),
                height=1,
                dont_extend_width=True,
            ),
            _rule(_HORIZONTAL),
            _rule(_TOP_RIGHT, 1),
        ], height=1)

    return HSplit([
        top,
        VSplit([
            Window(char=_VERTICAL, style="class:frame.border", width=1),
            body,
            Window(char=_VERTICAL, style="class:frame.border", width=1),
        ]),
        VSplit([
            _rule(_BOTTOM_LEFT, 1), _rule(_HORIZONTAL), _rule(_BOTTOM_RIGHT, 1),
        ], height=1),
    ])
