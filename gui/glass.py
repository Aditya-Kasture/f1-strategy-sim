# Pit Strategy: F1 pit stop strategy simulator (COMP9001). To run the program: python main.py (see README.txt)
"""The "liquid glass" look.

tkinter widgets can't be see-through, so the effect is built by hand:

* A Scene describes a soft, colourful backdrop (blurred colour blobs) in one shared
  coordinate system.
* Backdrop is a layout container (a Canvas you can pack or grid widgets into) that paints
  its own slice of the scene, so the gaps between widgets show one continuous picture.
* GlassCard paints the slice of the scene behind it and then a frosted panel on top: its
  fill is the local backdrop colour mixed with white, with a bright rim, a soft shadow and a
  specular highlight along the top edge. Because the fill is worked out from what is behind
  the card, cards over a blue patch look bluish and cards over a pink patch look pinkish,
  just like frosted glass.
"""

from __future__ import annotations

import math
import tkinter as tk
from typing import List, Optional

from . import theme

RINGS = 26


def rounded_rect(canvas: tk.Canvas, x1, y1, x2, y2, r, **kwargs):
    """Draw a rectangle with rounded corners (a smoothed polygon)."""
    r = max(0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    points = [x1 + r, y1, x1 + r, y1, x2 - r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y1 + r,
              x2, y2 - r, x2, y2 - r, x2, y2, x2 - r, y2, x2 - r, y2, x1 + r, y2, x1 + r, y2,
              x1, y2, x1, y2 - r, x1, y2 - r, x1, y1 + r, x1, y1 + r, x1, y1]
    return canvas.create_polygon(points, smooth=True, **kwargs)


class Scene:
    """A backdrop of colour blobs, measured relative to an origin widget."""

    def __init__(self, blobs, base: str = theme.BASE):
        self.blobs = blobs
        self.base = base
        self.origin: Optional[tk.Widget] = None
        self.members: List[tk.Widget] = []

    def width(self) -> int:
        return max(300, self.origin.winfo_width() if self.origin else 1000)

    def offset(self, widget: tk.Widget):
        if self.origin is None:
            return 0, 0
        return (widget.winfo_rootx() - self.origin.winfo_rootx(),
                widget.winfo_rooty() - self.origin.winfo_rooty())

    def colour_at(self, x: float, y: float) -> str:
        w = self.width()
        colour = self.base
        for fx, fy, fr, blob in self.blobs:
            distance = math.hypot(x - fx * w, y - fy * w) / (fr * w)
            if distance < 1:
                colour = theme.blend(self.base, blob, self._strength(distance))
        return colour

    @staticmethod
    def _strength(distance: float) -> float:
        return (1 - distance) ** 1.6

    def paint(self, canvas: tk.Canvas, ox: float, oy: float, w: float, h: float, tag: str):
        """Paint the part of the scene at (ox, oy, w, h) onto a canvas at (0, 0)."""
        canvas.create_rectangle(-2, -2, w + 2, h + 2, fill=self.base, outline="", tags=tag)
        width = self.width()
        for fx, fy, fr, blob in self.blobs:
            cx, cy, radius = fx * width - ox, fy * width - oy, fr * width
            if cx + radius < 0 or cx - radius > w or cy + radius < 0 or cy - radius > h:
                continue
            for i in range(RINGS, 0, -1):
                t = i / RINGS
                colour = theme.blend(self.base, blob, self._strength(t))
                r = radius * t
                canvas.create_oval(cx - r, cy - r, cx + r, cy + r, fill=colour, outline="",
                                   tags=tag)

    def refresh(self):
        """Repaint every visible member (after the layout changed)."""
        for widget in list(self.members):
            try:
                if widget.winfo_exists() and widget.winfo_ismapped():
                    widget.redraw_glass()
            except tk.TclError:
                self.members.remove(widget)


def retint(widget: tk.Misc, old: str, new: str):
    """Give every descendant that used the old background the new one."""
    for child in widget.winfo_children():
        if isinstance(child, GlassCard):
            child.configure(bg=new)
            child.redraw_glass()
            continue
        try:
            bg = child.cget("bg")
        except tk.TclError:
            bg = None
        if bg is not None and (theme.same_colour(bg, old) or theme.same_colour(bg, theme.CARD)):
            child.configure(bg=new)
            if hasattr(child, "refresh"):
                child.refresh()
        retint(child, old, new)


class Backdrop(tk.Canvas):
    """A container that shows its slice of the scene behind its children."""

    def __init__(self, parent, scene: Scene, **kwargs):
        # width and height are in pixels at 96 DPI, like every size in the app
        kwargs["width"] = theme.px(kwargs.get("width", 1))
        kwargs["height"] = theme.px(kwargs.get("height", 1))
        super().__init__(parent, bg=scene.base, highlightthickness=0, bd=0, **kwargs)
        self.scene = scene
        scene.members.append(self)
        self._pending = False
        self.bind("<Configure>", lambda e: self._schedule())

    def _schedule(self):
        if not self._pending:
            self._pending = True
            self.after_idle(self.redraw_glass)

    def redraw_glass(self):
        self._pending = False
        w, h = self.winfo_width(), self.winfo_height()
        if w < 2 or h < 2:
            return
        ox, oy = self.scene.offset(self)
        self.delete("scene")
        self.scene.paint(self, ox, oy, w, h, "scene")
        self.tag_lower("scene")
        # Plain widgets sitting straight on the backdrop take the colour behind them
        for child in self.winfo_children():
            if isinstance(child, (Backdrop, GlassCard)) or not child.winfo_ismapped():
                continue
            cx = child.winfo_x() + child.winfo_width() / 2
            cy = child.winfo_y() + child.winfo_height() / 2
            colour = self.scene.colour_at(ox + cx, oy + cy)
            try:
                if not theme.same_colour(child.cget("bg"), colour):
                    child.configure(bg=colour)
                    if hasattr(child, "refresh"):
                        child.refresh()
            except tk.TclError:
                pass


class TextBackdrop(Backdrop):
    """A strip of backdrop with text drawn straight onto it (no label boxes)."""

    def __init__(self, parent, scene: Scene, height: int):
        super().__init__(parent, scene, height=height)
        self.items = {}  # key -> (x, y, text, font, colour, anchor); x < 0 counts from the right

    def set_text(self, key, x, y, text, font, colour, anchor="w"):
        """x and y are in pixels at 96 DPI; a negative x counts from the right edge."""
        self.items[key] = (theme.scaled(x), theme.scaled(y), text, font, colour, anchor)
        self._draw_text()

    def redraw_glass(self):
        super().redraw_glass()
        self._draw_text()

    def _draw_text(self):
        self.delete("text")
        width = self.winfo_width()
        for x, y, text, font, colour, anchor in self.items.values():
            self.create_text(x if x >= 0 else width + x, y, text=text, font=font, fill=colour,
                             anchor=anchor, tags="text")


class GlassCard(tk.Canvas):
    """A frosted-glass panel. Put child widgets in `card.body` with bg=theme.CARD.

    scene: the backdrop it floats over. Leave it out (solid_parent) for glass inside glass.
    By default the card grows to fit its content; fill_height=True stretches the body to
    the card's height instead.
    """

    def __init__(self, parent, scene: Optional[Scene] = None, padding=20, radius=22,
                 mix=0.72, fill_height=False, **kwargs):
        kwargs.setdefault("width", 10)
        super().__init__(parent, bg=theme.BASE, highlightthickness=0, bd=0, **kwargs)
        # padding and radius are in pixels at 96 DPI
        padding, radius = theme.px(padding), theme.scaled(radius)
        self.scene, self.padding, self.radius, self.mix = scene, padding, radius, mix
        self.fill_height = fill_height
        self.fill = theme.CARD
        self.accent_outline: Optional[str] = None
        self.accent_width = 1
        self.body = tk.Frame(self, bg=theme.CARD)
        self._window = self.create_window(padding, padding, window=self.body, anchor="nw")
        self._pending = False
        if scene is not None:
            scene.members.append(self)
        self.bind("<Configure>", lambda e: self._schedule())
        if not fill_height:
            self.body.bind("<Configure>", self._fit_height)

    def set_outline(self, colour: Optional[str], width: int = 1):
        self.accent_outline, self.accent_width = colour, width
        self.redraw_glass()

    def _fit_height(self, event):
        wanted = event.height + 2 * self.padding
        if int(self.cget("height")) != wanted:
            self.configure(height=wanted)

    def _schedule(self):
        if not self._pending:
            self._pending = True
            self.after_idle(self.redraw_glass)

    def _local_colour(self, w, h) -> str:
        if self.scene is not None:
            ox, oy = self.scene.offset(self)
            return self.scene.colour_at(ox + w / 2, oy + h / 2)
        return self.master.cget("bg")

    def redraw_glass(self):
        self._pending = False
        w, h = self.winfo_width(), self.winfo_height()
        if w < 8 or h < 8:
            return
        self.delete("glass")
        local = self._local_colour(w, h)
        if self.scene is not None:
            ox, oy = self.scene.offset(self)
            self.scene.paint(self, ox, oy, w, h, "glass")
        else:
            self.configure(bg=local)
            self.create_rectangle(-2, -2, w + 2, h + 2, fill=local, outline="", tags="glass")

        r = self.radius
        u = theme.scaled
        x1, y1, x2, y2 = 1, 1, w - 2, h - u(4)
        # soft shadow underneath
        rounded_rect(self, x1, y1 + u(3), x2, y2 + u(3), r,
                     fill=theme.blend(local, theme.INK, 0.06), outline="", tags="glass")
        rounded_rect(self, x1, y1 + u(1), x2, y2 + u(1), r,
                     fill=theme.blend(local, theme.INK, 0.05), outline="", tags="glass")
        # the frosted panel
        fill = theme.blend(local, "#FFFFFF", self.mix)
        rim = self.accent_outline or theme.blend(local, theme.INK, 0.10)
        rounded_rect(self, x1, y1, x2, y2, r, fill=fill, outline=rim,
                     width=u(self.accent_width) if self.accent_outline else u(1), tags="glass")
        # bright inner rim and a specular sheen along the top edge
        inset = u(1.5)
        rounded_rect(self, x1 + inset, y1 + inset, x2 - inset, y2 - inset, r - inset, fill="",
                     outline=theme.blend(fill, "#FFFFFF", 0.75), width=u(1.2), tags="glass")
        sheen = min(self.padding - 2, r)
        for k in range(2, int(sheen)):
            inset = r - math.sqrt(max(0.0, r * r - (r - k) ** 2)) if k < r else 0
            colour = theme.blend(fill, "#FFFFFF", 0.55 * (1 - k / sheen) ** 2)
            self.create_line(x1 + inset + 2, y1 + k, x2 - inset - 2, y1 + k, fill=colour,
                             tags="glass")
        self.tag_lower("glass")

        self.itemconfigure(self._window, width=max(1, w - 2 * self.padding))
        if self.fill_height:
            self.itemconfigure(self._window, height=max(1, h - u(4) - 2 * self.padding))
        if not theme.same_colour(fill, self.fill):
            old, self.fill = self.fill, fill
            self.body.configure(bg=fill)
            retint(self.body, old, fill)
