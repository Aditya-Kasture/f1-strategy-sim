# Pit Strategy: F1 pit stop strategy simulator (COMP9001). To run the program: python main.py (see README.txt)
"""Design tokens: colours, type scale, spacing and colour maths.

Rules this file follows (checked by tests/test_design.py):
* Every colour has one job (text, secondary text, action, success, error, ...).
* Every text colour passes WCAG AA (4.5:1) on the surfaces it is used on.
* One type scale (ratio 1.25 from a 14 pt base) and one spacing scale are used everywhere.
"""

from __future__ import annotations

from typing import Tuple

# --- surfaces (elevation 0 = backdrop, 1 = panels, 2 = floating tooltips) ---------------
BASE = "#E8ECF3"      # level 0: the backdrop behind the glass
CARD = "#FFFFFF"      # placeholder background for widgets inside glass panels
FLOAT = "#FCFDFF"     # level 2: tooltips and popovers

# --- text ----------------------------------------------------------------------------
TEXT = "#1B1F27"       # primary text
SECONDARY = "#4D5361"  # supporting text, labels
TERTIARY = "#5F6573"   # axis labels, hints (still AA on every surface)

# --- one job per colour ----------------------------------------------------------------
ACCENT = "#0A62D0"        # primary action, links, selection, focus ring
ACCENT_HOVER = "#084FAA"  # primary action under the pointer
ACCENT_SOFT = "#E1ECFB"   # selected/recommended background tint
GREEN = "#13703A"         # success: "recommended", "ahead of rival"
GREEN_SOFT = "#E1F3E7"
RED = "#B42318"           # error messages, "behind rival"
RED_SOFT = "#FDECEA"
INK = "#1C2333"           # hairlines and shadows, always heavily diluted

# Strategy colours fill lines and bars; the _TEXT versions are darker so text stays readable.
STRATEGY_COLOURS = {1: "#FF9500", 2: "#0A62D0", 3: "#AF52DE"}
STRATEGY_TEXT = {1: "#9A4F00", 2: "#0A62D0", 3: "#7D33AD"}
RIVAL_COLOUR = "#8E8E93"

# --- display scaling -----------------------------------------------------------------
# Fonts are sized in points, so Tk already makes text bigger on a high-DPI screen (Windows
# at 125% or 150%). Every layout size in this app is written in pixels at 96 DPI and goes
# through px() or scaled(), so the boxes grow by the same factor as the text inside them.
SCALE = 1.0


def set_scale(root) -> float:
    """Read the screen's DPI from Tk (pixels per point) and set SCALE to match."""
    global SCALE
    try:
        pixels_per_point = float(root.tk.call("tk", "scaling"))
    except Exception:
        pixels_per_point = 96 / 72
    SCALE = max(1.0, min(3.0, pixels_per_point / (96 / 72)))
    return SCALE


def px(value: float) -> int:
    """A layout size in whole pixels for this screen."""
    return int(round(value * SCALE))


def scaled(value: float) -> float:
    """A drawing coordinate for this screen."""
    return value * SCALE


def pad(value):
    """px() for pack/grid padding, which can be one number or a (before, after) pair."""
    if isinstance(value, (tuple, list)):
        return tuple(px(v) for v in value)
    return px(value)


# --- spacing scale (pixels at 96 DPI) ------------------------------------------------
SPACE = {"xs": 4, "s": 8, "m": 12, "l": 16, "xl": 24, "xxl": 32, "huge": 48}

# --- corner radius by elevation ----------------------------------------------------------
RADIUS = {"panel": 18, "inner": 12, "control": 10}

# A quiet backdrop: low-saturation colour washes, spaced so they never overlap.
# (x, y, radius, colour) as fractions of the area's width.
_MAIN = [
    (0.15, 0.05, 0.30, "#B4CCF5"),
    (0.90, 0.12, 0.30, "#D5C8F2"),
    (0.50, 0.62, 0.30, "#BFE3D8"),
    (0.05, 1.15, 0.30, "#F2D3C4"),
    (0.92, 1.05, 0.30, "#C3CCEE"),
    (0.50, 1.62, 0.30, "#E8CDE0"),
    (0.05, 2.15, 0.30, "#BED8F0"),
    (0.95, 2.20, 0.30, "#CEC8EE"),
]
_SIDE = [
    (0.35, 0.25, 0.85, "#CEC6EE"),
    (0.70, 2.30, 0.85, "#BCD6EE"),
]

# Mac and Windows system fonts first; the rest are fallbacks for Linux.
PREFERRED_FAMILIES = ("SF Pro Text", "SF Pro", "Helvetica Neue", "Avenir Next", "Segoe UI",
                      "Inter", "Ubuntu", "Cantarell", "DejaVu Sans", "Helvetica", "Arial")


def to_rgb(colour: str) -> Tuple[int, int, int]:
    colour = colour.lstrip("#")
    return int(colour[0:2], 16), int(colour[2:4], 16), int(colour[4:6], 16)


def to_hex(rgb) -> str:
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(c)))) for c in rgb)


def blend(a: str, b: str, t: float) -> str:
    """Mix colour a with colour b. t=0 gives a, t=1 gives b."""
    ra, rb = to_rgb(a), to_rgb(b)
    return to_hex(x + (y - x) * t for x, y in zip(ra, rb))


def same_colour(a: str, b: str) -> bool:
    return str(a).lower() == str(b).lower()


def luminance(colour: str) -> float:
    """WCAG relative luminance."""
    def channel(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(c) for c in to_rgb(colour))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    """WCAG contrast ratio between two colours (1 to 21)."""
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def text_on(fill: str) -> str:
    """Dark or white text, whichever is easier to read on this fill."""
    return TEXT if contrast(TEXT, fill) >= contrast("#FFFFFF", fill) else "#FFFFFF"


def readable(colour: str, background: str, ratio: float = 4.5) -> str:
    """The colour, darkened just enough to be readable as text on the background."""
    for step in range(21):
        candidate = blend(colour, TEXT, step / 20)
        if contrast(candidate, background) >= ratio:
            return candidate
    return TEXT


MAIN_BLOBS = _MAIN
SIDE_BLOBS = _SIDE


class Fonts:
    """The type scale: ratio 1.25 from a 14 pt body, sized to read on a projector."""

    def __init__(self, root):
        from tkinter import font as tkfont  # imported here so the colour maths needs no Tk

        available = set(tkfont.families(root))
        family = next((f for f in PREFERRED_FAMILIES if f in available), "TkDefaultFont")
        self.family = family

        def make(size, weight="normal"):
            return tkfont.Font(root=root, family=family, size=size, weight=weight)

        self.hero = make(34, "bold")     # the recommendation
        self.title = make(27, "bold")    # page title
        self.stat = make(27, "bold")     # big numbers
        self.large = make(22, "bold")    # card titles
        self.heading = make(17, "bold")  # section headings
        self.body = make(14)
        self.body_bold = make(14, "bold")
        self.small = make(12)            # labels, chart text (smallest readable size)
        self.small_bold = make(12, "bold")
        self.caption = make(11, "bold")  # upper-case eyebrow labels only
