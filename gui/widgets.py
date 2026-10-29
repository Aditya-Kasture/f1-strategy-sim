# Pit Strategy: F1 pit stop strategy simulator (COMP9001). To run the program: python main.py (see README.txt)
"""Custom widgets drawn on tk.Canvas: glossy buttons, segmented controls, sliders, tire
stint bars, track maps and interactive charts. Every widget redraws itself when its
background colour changes (see glass.retint), so it always blends into the glass.

Sizes are written in pixels at 96 DPI and scaled with theme.px / theme.scaled (here `u`),
so on a Windows screen at 125% or 150% the boxes grow with the text inside them."""

from __future__ import annotations

import tkinter as tk
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from . import theme
from .glass import rounded_rect

u = theme.scaled


class CanvasWidget(tk.Canvas):
    """A canvas that redraws on resize and when told its background changed.

    width and height are in pixels at 96 DPI. focusable=True makes it reachable with the
    Tab key. The focus ring only shows when focus arrived from the keyboard, not after a
    mouse click (like :focus-visible).
    """

    def __init__(self, parent, focusable=False, **kwargs):
        kwargs["width"] = theme.px(kwargs.get("width", 10))
        if "height" in kwargs:
            kwargs["height"] = theme.px(kwargs["height"])
        kwargs.setdefault("bg", theme.CARD)
        super().__init__(parent, highlightthickness=0, bd=0,
                         takefocus=1 if focusable else 0, **kwargs)
        self.focus_visible = False
        self._clicked = False
        self.bind("<Configure>", lambda e: self.refresh())
        if focusable:
            self.bind("<ButtonPress-1>", self._pointer_focus, add="+")
            self.bind("<FocusIn>", self._focus_in, add="+")
            self.bind("<FocusOut>", self._focus_out, add="+")

    def _pointer_focus(self, _event):
        self._clicked = True
        self.focus_set()

    def _focus_in(self, _event):
        self.focus_visible = not self._clicked
        self._clicked = False
        self.refresh()

    def _focus_out(self, _event):
        self.focus_visible = False
        self.refresh()

    def _key(self):
        """A key was pressed while focused, so show where the focus is."""
        if not self.focus_visible:
            self.focus_visible = True

    def focus_ring(self, x1, y1, x2, y2, r):
        if self.focus_visible:
            rounded_rect(self, x1, y1, x2, y2, r, fill="", outline=theme.ACCENT, width=u(2.5))

    @property
    def bg(self) -> str:
        return self.cget("bg")

    def refresh(self):
        self.delete("all")
        if self.winfo_width() > 4:
            self.draw()

    def draw(self):
        raise NotImplementedError


class PillButton(CanvasWidget):
    """A glossy, rounded button."""

    def __init__(self, parent, text: str, command: Callable[[], None], fonts, height=50,
                 colour=theme.ACCENT, hover=theme.ACCENT_HOVER):
        super().__init__(parent, focusable=True, height=height, cursor="hand2")
        self.text, self.command, self.fonts = text, command, fonts
        self.colour, self.hover_colour = colour, hover
        self.enabled = True
        self._hover = self._pressed = False
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<ButtonPress-1>", lambda e: self._set_pressed(True), add="+")
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<space>", self._activate)
        self.bind("<Return>", self._activate)

    def _set_hover(self, value):
        self._hover = value
        if not value:
            self._pressed = False
        self.refresh()

    def _set_pressed(self, value):
        self._pressed = value
        self.refresh()

    def _release(self, _event):
        was_pressed = self._pressed
        self._set_pressed(False)
        if was_pressed and self._hover and self.enabled:
            self.command()

    def _activate(self, _event):
        self._key()
        if self.enabled:
            self.command()
        return "break"  # don't also trigger the window's Enter shortcut

    def set_text(self, text: str):
        self.text = text
        self.refresh()

    def set_enabled(self, enabled: bool):
        self.enabled = enabled
        self.configure(cursor="hand2" if enabled else "arrow")
        self.refresh()

    def _font(self, width):
        """The bold body font, or a smaller one if the label would not fit."""
        if self.fonts.body_bold.measure(self.text) <= width - u(28):
            return self.fonts.body_bold
        return self.fonts.small_bold

    def draw(self):
        w, h = self.winfo_width(), self.winfo_height()
        if not self.enabled:
            colour = theme.blend(self.bg, theme.INK, 0.12)
        elif self._pressed:
            colour = theme.blend(self.hover_colour, theme.INK, 0.2)
        else:
            colour = self.hover_colour if self._hover else self.colour
        dy = u(1) if self._pressed else 0
        r = u(theme.RADIUS["control"] + 2)
        rounded_rect(self, u(3), u(5), w - u(3), h - u(2), r,
                     fill=theme.blend(self.bg, colour, 0.22), outline="")
        rounded_rect(self, u(3), u(3) + dy, w - u(3), h - u(5) + dy, r, fill=colour,
                     outline=theme.blend(colour, "#FFFFFF", 0.3))
        self.create_text(w / 2, (h - u(2)) / 2 + dy, text=self.text,
                         fill="#FFFFFF" if self.enabled else theme.SECONDARY,
                         font=self._font(w))
        self.focus_ring(u(0.5), u(0.5), w - u(0.5), h - u(1.5), r + u(2))


class SegmentedControl(CanvasWidget):
    """A row of options where one (or none) is selected.

    Each segment is as wide as its label needs, plus an equal share of the spare room, so
    long labels such as "Intermediate" never get squashed. The control asks for its
    natural width, and steps down to a smaller font only if it is given less room.
    """

    def __init__(self, parent, options: Sequence[str], fonts, command=None, value=None,
                 dots: Optional[Dict[str, str]] = None, height=34, font=None, labels=None):
        super().__init__(parent, focusable=True, height=height, cursor="hand2")
        self.options = list(options)
        self.labels = labels or {}
        self.value = value
        self.fonts, self.command, self.dots = fonts, command, dots or {}
        self.font = font or fonts.small_bold
        self._hover_index = None
        self.configure(width=self.natural_width())
        self.bind("<ButtonRelease-1>", self._click)
        self.bind("<Motion>", self._motion)
        self.bind("<Leave>", lambda e: self._set_hover_index(None))
        self.bind("<Left>", lambda e: self._step(-1))
        self.bind("<Right>", lambda e: self._step(1))

    def _needs(self, font) -> List[float]:
        return [font.measure(self.labels.get(o, o)) + (u(17) if o in self.dots else 0) + u(22)
                for o in self.options]

    def natural_width(self) -> int:
        return int(sum(self._needs(self.font)) + u(8))

    def _layout(self):
        """(font, [(x1, x2) for each segment]) for the current width."""
        w = self.winfo_width()
        fonts = [self.font] + [f for f in (self.fonts.small_bold, self.fonts.small,
                                           self.fonts.caption) if f is not self.font]
        for font in fonts:
            needs = self._needs(font)
            if sum(needs) <= w:
                break
        spare = (w - sum(needs)) / len(needs)
        edges, x = [], 0.0
        for need in needs:
            width = max(1.0, need + spare)
            edges.append((x, x + width))
            x += width
        return font, edges

    def _index_at(self, x):
        _, edges = self._layout()
        for i, (_, x2) in enumerate(edges):
            if x < x2:
                return i
        return len(edges) - 1

    def _motion(self, event):
        self._set_hover_index(self._index_at(event.x))

    def _set_hover_index(self, index):
        if index != self._hover_index:
            self._hover_index = index
            self.refresh()

    def _step(self, direction):
        self._key()
        index = self.options.index(self.value) if self.value in self.options else -1
        index = (index + direction) % len(self.options)
        self.set(self.options[index], notify=True)
        return "break"

    def set(self, value, notify=False):
        self.value = value
        self.refresh()
        if notify and self.command:
            self.command(value)

    def _click(self, event):
        index = self._index_at(event.x)
        if self.options[index] != self.value:
            self.set(self.options[index], notify=True)

    def draw(self):
        w, h = self.winfo_width(), self.winfo_height()
        bg = self.bg
        r = u(theme.RADIUS["control"])
        rounded_rect(self, 0, 0, w, h, r, fill=theme.blend(bg, theme.INK, 0.08),
                     outline=theme.blend(bg, theme.INK, 0.10))
        font, edges = self._layout()
        inset = u(3)
        for i, (option, (x1, x2)) in enumerate(zip(self.options, edges)):
            selected = option == self.value
            if selected:
                rounded_rect(self, x1 + inset, inset + u(1), x2 - inset, h - u(2), r - inset,
                             fill=theme.blend(bg, theme.INK, 0.14), outline="")
                rounded_rect(self, x1 + inset, inset, x2 - inset, h - inset, r - inset,
                             fill="#FFFFFF", outline=theme.blend(bg, theme.INK, 0.10))
            elif i == self._hover_index:
                rounded_rect(self, x1 + inset, inset, x2 - inset, h - inset, r - inset,
                             fill=theme.blend(bg, "#FFFFFF", 0.55), outline="")
            colour = theme.TEXT if selected else theme.SECONDARY
            label = self.labels.get(option, option)
            cx = (x1 + x2) / 2
            if option in self.dots:
                text_w = font.measure(label)
                dot_x = cx - text_w / 2 - u(3)
                d = u(5)
                self.create_oval(dot_x - d, h / 2 - d, dot_x + d, h / 2 + d,
                                 fill=self.dots[option], outline=theme.blend(bg, theme.INK, 0.2))
                cx += u(8.5)
            self.create_text(cx, h / 2, text=label, fill=colour, font=font)
        self.focus_ring(u(0.5), u(0.5), w - u(0.5), h - u(0.5), r)


class Slider(CanvasWidget):
    """A thin glass track with a round white knob."""

    def __init__(self, parent, from_: float, to: float, value: float, command=None,
                 step: float = 0.01, height=26):
        super().__init__(parent, focusable=True, height=height, cursor="hand2")
        self.from_, self.to, self.step = from_, to, step
        self.value = value
        self.command = command
        self.bind("<Button-1>", self._drag, add="+")
        self.bind("<B1-Motion>", self._drag)
        self.bind("<Left>", lambda e: self._nudge(-1))
        self.bind("<Right>", lambda e: self._nudge(1))

    def _nudge(self, direction):
        self._key()
        self.set(self.value + direction * self.step, notify=True)
        return "break"

    def set(self, value: float, notify=False):
        self.value = min(self.to, max(self.from_, round(value / self.step) * self.step))
        self.refresh()
        if notify and self.command:
            self.command(self.value)

    def _drag(self, event):
        k = u(11)
        ratio = (event.x - k) / max(1, self.winfo_width() - 2 * k)
        self.set(self.from_ + ratio * (self.to - self.from_), notify=True)

    def draw(self):
        w, h = self.winfo_width(), self.winfo_height()
        k, t = u(11), u(2.5)  # knob radius, half the track thickness
        y = h / 2
        x = k + (self.value - self.from_) / (self.to - self.from_) * (w - 2 * k)
        rounded_rect(self, k, y - t, w - k, y + t, t,
                     fill=theme.blend(self.bg, theme.INK, 0.12), outline="")
        if x > k + u(2):
            rounded_rect(self, k, y - t, x, y + t, t, fill=theme.ACCENT, outline="")
        self.create_oval(x - k, y - k + u(2), x + k, y + k + u(1),
                         fill=theme.blend(self.bg, theme.INK, 0.15), outline="")
        self.create_oval(x - k, y - k, x + k, y + k, fill="#FFFFFF",
                         outline=theme.blend(self.bg, theme.INK, 0.12))
        if self.focus_visible:
            ring = k + u(2)
            self.create_oval(x - ring, y - ring, x + ring, y + ring, outline=theme.ACCENT,
                             width=u(2.5))


class StintBar(CanvasWidget):
    """Shows a strategy as coloured tire stints with the pit laps underneath."""

    def __init__(self, parent, fonts, height=46):
        super().__init__(parent, height=height)
        self.fonts = fonts
        self.strategy = None

    def set_strategy(self, strategy):
        self.strategy = strategy
        self.refresh()

    def draw(self):
        if not self.strategy:
            return
        w = self.winfo_width()
        bar_h = u(24)
        gap = u(2)
        scale = (w - 2) / self.strategy.total_laps
        stints = self.strategy.stints
        for i, stint in enumerate(stints):
            x1 = 1 + (stint.start_lap - 1) * scale
            x2 = 1 + stint.end_lap * scale - (gap if i < len(stints) - 1 else 0)
            colour = stint.compound.colour
            rounded_rect(self, x1, 0, x2, bar_h, u(8), fill=colour,
                         outline=theme.blend(colour, theme.INK, 0.15))
            rounded_rect(self, x1 + gap, gap, x2 - gap, bar_h / 2, u(5),
                         fill=theme.blend(colour, "#FFFFFF", 0.25), outline="")
            name = stint.compound.name
            label = name if (x2 - x1) > self.fonts.small_bold.measure(name) + u(12) else name[0]
            if (x2 - x1) > self.fonts.small_bold.measure(label) + u(4):
                self.create_text((x1 + x2) / 2, bar_h / 2, text=label,
                                 fill=theme.text_on(colour), font=self.fonts.small_bold)
        last_right = -1000.0
        for lap in self.strategy.pit_laps:
            text = f"L{lap}"
            half = self.fonts.small.measure(text) / 2
            x = 1 + lap * scale
            if x - half < last_right + u(4):  # too close to the previous label: drop the "L"
                text = str(lap)
                half = self.fonts.small.measure(text) / 2
            x = min(max(x, last_right + u(4) + half, half), w - half)
            self.create_text(x, bar_h + u(12), text=text, fill=theme.SECONDARY,
                             font=self.fonts.small)
            last_right = x + half


class ProgressBar(CanvasWidget):
    def __init__(self, parent, height=6):
        super().__init__(parent, height=height)
        self.value = 0.0

    def set(self, value: float):
        self.value = max(0.0, min(1.0, value))
        self.refresh()

    def draw(self):
        w, h = self.winfo_width(), self.winfo_height()
        rounded_rect(self, 0, 0, w, h, h / 2, fill=theme.blend(self.bg, theme.INK, 0.08),
                     outline="")
        if self.value > 0:
            rounded_rect(self, 0, 0, max(h, w * self.value), h, h / 2, fill=theme.ACCENT,
                         outline="")


class ScrollBar(CanvasWidget):
    """A slim, always-visible scrollbar for a canvas (the thumb hides when nothing is hidden)."""

    def __init__(self, parent, target: tk.Canvas, width=14):
        super().__init__(parent, width=width, bg=theme.BASE)
        self.target = target
        self.first, self.last = 0.0, 1.0
        self._drag = None
        self._hover = False
        target.configure(yscrollcommand=self.set)
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<B1-Motion>", self._move)
        self.bind("<ButtonRelease-1>", lambda e: setattr(self, "_drag", None))
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))

    def set(self, first, last):
        self.first, self.last = float(first), float(last)
        self.refresh()

    def _set_hover(self, value):
        self._hover = value
        self.refresh()

    def _thumb(self):
        h = self.winfo_height() - u(8)
        y1 = u(4) + self.first * h
        return y1, max(y1 + u(36), u(4) + self.last * h)

    def draw(self):
        if self.last - self.first >= 0.999:
            return
        w = self.winfo_width()
        side = u(3)
        rounded_rect(self, side, u(4), w - side, self.winfo_height() - u(4), (w - 2 * side) / 2,
                     fill=theme.blend(self.bg, theme.INK, 0.06), outline="")
        y1, y2 = self._thumb()
        colour = theme.blend(self.bg, theme.INK, 0.55 if self._hover or self._drag else 0.38)
        rounded_rect(self, side, y1, w - side, y2, (w - 2 * side) / 2, fill=colour, outline="")

    def _press(self, event):
        y1, y2 = self._thumb()
        if not y1 <= event.y <= y2:  # clicking the track jumps there
            span = self.last - self.first
            self.target.yview_moveto(event.y / max(1, self.winfo_height()) - span / 2)
        self._drag = (event.y, self.first)

    def _move(self, event):
        if self._drag:
            start_y, start_first = self._drag
            delta = (event.y - start_y) / max(1, self.winfo_height() - u(8))
            self.target.yview_moveto(start_first + delta)


class MeterBar(CanvasWidget):
    """A small horizontal bar for a percentage."""

    def __init__(self, parent, colour, height=8):
        super().__init__(parent, height=height)
        self.colour, self.value = colour, 0.0

    def set(self, value: float):
        self.value = max(0.0, min(1.0, value))
        self.refresh()

    def draw(self):
        w, h = self.winfo_width(), self.winfo_height()
        rounded_rect(self, 0, 0, w, h, h / 2, fill=theme.blend(self.bg, theme.INK, 0.08),
                     outline="")
        if self.value > 0.005:
            rounded_rect(self, 0, 0, max(h, w * self.value), h, h / 2, fill=self.colour,
                         outline="")


class TrackMap(CanvasWidget):
    """Draws a circuit layout. With animate=True a car laps the track."""

    def __init__(self, parent, height=120, line_width=5, animate=False, glow=True):
        super().__init__(parent, height=height)
        self.points: List[Tuple[float, float]] = []
        self.line_width = u(line_width)
        self.animate, self.glow = animate, glow
        self.colour = theme.TEXT
        self._screen: List[Tuple[float, float]] = []
        self._car_index = 0
        self._running = False

    def set_points(self, points, colour=None):
        self.points = list(points or [])
        if colour:
            self.colour = colour
        self._car_index = 0
        self.refresh()
        if self.animate and not self._running:
            self._running = True
            self.after(60, self._tick)

    def draw(self):
        if len(self.points) < 3:
            self.create_text(self.winfo_width() / 2, self.winfo_height() / 2, text="No map",
                             fill=theme.SECONDARY)
            return
        w, h = self.winfo_width(), self.winfo_height()
        lw = self.line_width
        pad = lw * 2 + u(6)
        xs = [p[0] for p in self.points]
        ys = [p[1] for p in self.points]
        span_x, span_y = max(xs) - min(xs) or 1, max(ys) - min(ys) or 1
        scale = max(1e-6, min((w - 2 * pad) / span_x, (h - 2 * pad) / span_y))
        ox = (w - span_x * scale) / 2 - min(xs) * scale
        oy = (h - span_y * scale) / 2 - min(ys) * scale
        pts = [(x * scale + ox, y * scale + oy) for x, y in self.points]
        if pts[0] != pts[-1]:
            pts.append(pts[0])
        self._screen = pts
        flat = [c for p in pts for c in p]
        bg = self.bg
        if self.glow:
            self.create_line(flat, fill=theme.blend(bg, theme.ACCENT, 0.12),
                             width=lw + u(9), capstyle="round", joinstyle="round")
        shift = u(1.5)
        self.create_line([c + shift for c in flat], fill=theme.blend(bg, theme.INK, 0.18),
                         width=lw, capstyle="round", joinstyle="round")
        self.create_line(flat, fill=self.colour, width=lw, capstyle="round",
                         joinstyle="round")
        if lw >= u(4):
            self.create_line(flat, fill=theme.blend(self.colour, "#FFFFFF", 0.35), width=u(1),
                             capstyle="round", joinstyle="round")
        # start / finish line
        (sx, sy), (nx, ny) = pts[0], pts[1]
        dx, dy = nx - sx, ny - sy
        length = max(1e-6, (dx * dx + dy * dy) ** 0.5)
        px, py = -dy / length, dx / length
        half = lw + u(3)
        self.create_line(sx - px * half, sy - py * half, sx + px * half, sy + py * half,
                         fill="#FFFFFF", width=u(3))
        self.create_line(sx - px * half, sy - py * half, sx + px * half, sy + py * half,
                         fill=theme.RED, width=u(1.5), dash=(2, 2))
        if self.animate:
            self._draw_car()

    def _draw_car(self):
        self.delete("car")
        if not self._screen:
            return
        x, y = self._screen[self._car_index % len(self._screen)]
        r = self.line_width / 2 + u(3)
        halo = r + u(2)
        self.create_oval(x - halo, y - halo, x + halo, y + halo,
                         fill=theme.blend(self.bg, "#E10600", 0.25), outline="", tags="car")
        self.create_oval(x - r, y - r, x + r, y + r, fill="#E10600", outline="#FFFFFF",
                         width=u(1.5), tags="car")

    def _tick(self):
        try:
            if self.winfo_ismapped() and self._screen:
                self._car_index = (self._car_index + 1) % len(self._screen)
                self._draw_car()
                self.after(45, self._tick)
            else:
                self.after(400, self._tick)
        except tk.TclError:
            self._running = False


# ---------------------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------------------

def nice_ticks(lo: float, hi: float, count: int = 5) -> List[float]:
    """Round axis tick values that cover lo..hi."""
    if hi <= lo:
        hi = lo + 1
    raw = (hi - lo) / count
    magnitude = 10 ** (len(str(int(raw))) - 1) if raw >= 1 else 0.1
    step = magnitude
    for m in (1, 2, 2.5, 5, 10):
        step = m * magnitude
        if raw <= step:
            break
    start = int(lo / step) * step
    if start > lo:
        start -= step
    ticks = [round(start, 6)]
    while ticks[-1] < hi - step * 0.001:  # keep going until the top value is covered
        ticks.append(round(ticks[-1] + step, 6))
    return ticks


class Chart(CanvasWidget):
    """Base class: margins, gridlines, a glass legend and a hover tooltip."""

    margin = (60, 44, 24, 44)  # left, top, right, bottom, in pixels at 96 DPI

    empty_message = "Run a simulation to see this chart"

    def __init__(self, parent, fonts, height=320):
        super().__init__(parent, height=height)
        self.fonts = fonts
        self.bind("<Motion>", self._motion)
        self.bind("<Leave>", lambda e: self.delete("hover"))

    def refresh(self):
        super().refresh()
        if not self.find_all() and self.winfo_width() >= u(120):
            self.draw_empty()

    def draw_empty(self):
        """Empty state: say what will appear here instead of showing a blank panel."""
        w, h = self.winfo_width(), self.winfo_height()
        e = u(8)
        rounded_rect(self, e, e, w - e, h - e, u(theme.RADIUS["inner"]),
                     fill=self.tint("#FFFFFF", 0.35), outline=self.tint(theme.INK, 0.12),
                     dash=(4, 4))
        self.create_text(w / 2, h / 2, text=self.empty_message, fill=theme.SECONDARY,
                         font=self.fonts.body)

    def text_colour(self, colour: str) -> str:
        """A series colour darkened enough to read as text on this chart."""
        return theme.readable(colour, self.tint("#FFFFFF", 0.35))

    def extra_right(self) -> float:
        """Room a chart needs on the right, e.g. for labels at the end of lines."""
        return 0.0

    def plot_area(self) -> Tuple[float, float, float, float]:
        left, top, right, bottom = (u(m) for m in self.margin)
        left = max(left, self.fonts.small.measure("-100%") + u(20))
        right = max(right, self.extra_right())
        return left, top, self.winfo_width() - right, self.winfo_height() - bottom

    def tint(self, colour: str, amount: float) -> str:
        return theme.blend(self.bg, colour, amount)

    def draw_y_axis(self, lo, hi, label_fmt="{:g}", title=None):
        x1, y1, x2, y2 = self.plot_area()
        e = u(6)
        rounded_rect(self, x1 - e, y1 - e, x2 + e, y2 + e, u(14),
                     fill=self.tint("#FFFFFF", 0.35), outline=self.tint(theme.INK, 0.06))
        for tick in nice_ticks(lo, hi):
            if tick < lo - 1e-9 or tick > hi + 1e-9:
                continue
            y = y2 - (tick - lo) / (hi - lo) * (y2 - y1)
            self.create_line(x1, y, x2, y, fill=self.tint(theme.INK, 0.07), dash=(2, 4))
            self.create_text(x1 - u(12), y, text=label_fmt.format(tick), anchor="e",
                             fill=theme.TERTIARY, font=self.fonts.small)
        if title:
            self.create_text(x1 - e, u(15), text=title, anchor="w", fill=theme.SECONDARY,
                             font=self.fonts.small_bold)

    def legend_width(self, items: List[Tuple[str, str]]) -> float:
        return sum(self.fonts.small_bold.measure(label) + u(48) for label, _ in items)

    def legend(self, items: List[Tuple[str, str]]):
        x = self.plot_area()[2] + u(6)
        for label, colour in reversed(items):
            width = self.fonts.small_bold.measure(label) + u(40)
            rounded_rect(self, x - width, u(3), x, u(27), u(12), fill=self.tint("#FFFFFF", 0.75),
                         outline=self.tint(theme.INK, 0.12))
            self.create_oval(x - width + u(12), u(10), x - width + u(22), u(20), fill=colour,
                             outline="")
            self.create_text(x - u(12), u(15), text=label, anchor="e", fill=theme.TEXT,
                             font=self.fonts.small_bold)
            x -= width + u(8)

    def fit_legend(self, full, short, title):
        """The full legend if it fits next to the chart title, otherwise the short one."""
        x1, _, x2, _ = self.plot_area()
        room = x2 - x1 - self.fonts.small_bold.measure(title) - u(20)
        return full if self.legend_width(full) <= room else short

    def tooltip(self, x, y, title: str, rows: List[Tuple[str, str, str]]):
        """rows: (colour or '', label, value)."""
        font, bold = self.fonts.small, self.fonts.small_bold
        line = max(font.metrics("linespace"), bold.metrics("linespace")) + u(4)
        width = max([bold.measure(title)] +
                    [font.measure(l) + bold.measure(v) + u(40) for _, l, v in rows])
        width += u(24)
        height = line * (len(rows) + 1) + u(14)
        gap = u(16)
        left = x + gap if x + gap + width < self.winfo_width() - u(4) else x - gap - width
        left = max(u(4), min(left, self.winfo_width() - width - u(4)))  # always fully visible
        top = max(u(4), min(y - height / 2, self.winfo_height() - height - u(4)))
        r = u(12)
        rounded_rect(self, left, top + u(3), left + width, top + height + u(3), r,
                     fill=self.tint(theme.INK, 0.10), outline="", tags="hover")
        rounded_rect(self, left, top, left + width, top + height, r, fill=theme.FLOAT,
                     outline=self.tint(theme.INK, 0.16), tags="hover")
        self.create_text(left + u(12), top + u(7) + line / 2, text=title, anchor="w",
                         fill=theme.TEXT, font=bold, tags="hover")
        d = u(4)
        for i, (colour, label, value) in enumerate(rows):
            ry = top + u(7) + line * (i + 1.5)
            tx = left + u(12)
            if colour:
                self.create_oval(tx, ry - d, tx + 2 * d, ry + d, fill=colour, outline="",
                                 tags="hover")
                tx += u(14)
            self.create_text(tx, ry, text=label, anchor="w", fill=theme.SECONDARY, font=font,
                             tags="hover")
            self.create_text(left + width - u(12), ry, text=value, anchor="e", fill=theme.TEXT,
                             font=bold, tags="hover")

    def _motion(self, event):
        self.delete("hover")
        x1, y1, x2, y2 = self.plot_area()
        if x1 <= event.x <= x2 and y1 - u(6) <= event.y <= y2 + u(6):
            self.hover(event.x, event.y)

    def hover(self, x, y):
        pass


class LineChart(Chart):
    """Several series of values against lap number, with shaded race events."""

    def __init__(self, parent, fonts, height=320):
        super().__init__(parent, fonts, height)
        self.margin = (60, 44, 84, 44)
        self.series: List[Tuple[str, str, List[float]]] = []
        self.markers: List[Tuple[str, int, float]] = []
        self.bands: List[Tuple[int, int, str, str]] = []  # (first lap, last lap, colour, label)
        self.y_title = ""
        self.zero_label = ""
        self.value_fmt: Callable[[float], str] = lambda v: f"{v:.1f}"
        self.extra_rows: Callable[[int], List[Tuple[str, str, str]]] = lambda lap: []
        self._geometry = None

    def set_data(self, series, markers=None, y_title="", zero_label="", bands=None,
                 value_fmt=None, extra_rows=None):
        self.series, self.markers, self.bands = series, markers or [], bands or []
        self.y_title, self.zero_label = y_title, zero_label
        if value_fmt:
            self.value_fmt = value_fmt
        if extra_rows:
            self.extra_rows = extra_rows
        self.refresh()

    def _ends(self):
        out = []
        for name, colour, ys in self.series:
            last = next((v for v in reversed(ys) if v is not None), None)
            if last is not None:
                out.append((name, colour, last))
        return out

    def extra_right(self) -> float:
        # wide enough for the longest label at the end of a line
        widths = [max(self.fonts.small_bold.measure(name),
                      self.fonts.small.measure(self.value_fmt(last)))
                  for name, _, last in self._ends()]
        return max(widths, default=0) + u(20)

    def draw(self):
        if not self.series or self.winfo_width() < u(120):
            return
        values = [v for _, _, ys in self.series for v in ys if v is not None]
        if not values:
            return
        lo, hi = min(values), max(values)
        pad = (hi - lo) * 0.08 or 1
        ticks = nice_ticks(lo - pad, hi + pad)
        lo, hi = ticks[0], ticks[-1]
        self.draw_y_axis(lo, hi, title=self.y_title)
        x1, y1, x2, y2 = self.plot_area()
        n = max(len(ys) for _, _, ys in self.series)

        def px(i):
            return x1 + i / max(1, n - 1) * (x2 - x1)

        def py(v):
            return y2 - (v - lo) / (hi - lo) * (y2 - y1)

        self._geometry = (n, px, py)
        step = (x2 - x1) / max(1, n - 1)
        for first, last, colour, label in self.bands:
            bx1, bx2 = max(x1, px(first - 1) - step / 2), min(x2, px(last - 1) + step / 2)
            self.create_rectangle(bx1, y1, bx2, y2, fill=self.tint(colour, 0.55), outline="")
        caption = self.fonts.caption
        pill_h = caption.metrics("linespace") + u(5)
        taken = [[], []]  # x ranges already used by labels, in two rows
        for first, last, colour, label in self.bands:
            bx1, bx2 = max(x1, px(first - 1) - step / 2), min(x2, px(last - 1) + step / 2)
            width = caption.measure(label) + u(14)
            cx = min(max((bx1 + bx2) / 2, x1 + width / 2), x2 - width / 2)
            span = (cx - width / 2 - u(4), cx + width / 2 + u(4))
            for row, used in enumerate(taken):
                if all(span[1] < a or span[0] > b for a, b in used):
                    used.append(span)
                    cy = y2 - u(4) - pill_h / 2 - row * (pill_h + u(4))
                    rounded_rect(self, cx - width / 2, cy - pill_h / 2, cx + width / 2,
                                 cy + pill_h / 2, pill_h / 2, fill=self.tint(colour, 0.95),
                                 outline=self.tint(theme.INK, 0.14))
                    self.create_text(cx, cy, text=label, fill=theme.TEXT, font=caption)
                    break  # with no free row the label is left out; the tooltip still says it

        room_per_10 = (x2 - x1) / max(1, n - 1) * 10
        lap_step = 10 if room_per_10 > self.fonts.small.measure("Lap 00") + u(12) else 20
        for lap in range(lap_step, n + 1, lap_step):
            self.create_text(px(lap - 1), y2 + u(18), text=f"Lap {lap}", fill=theme.TERTIARY,
                             font=self.fonts.small)
        if self.zero_label and lo < 0 < hi:
            self.create_line(x1, py(0), x2, py(0), fill=self.tint(theme.INK, 0.35), dash=(5, 4))
        for _, colour, ys in self.series:
            # None values (e.g. Safety Car laps) break the line into separate pieces
            pieces, current = [], []
            for i, v in enumerate(ys):
                if v is None:
                    if current:
                        pieces.append(current)
                    current = []
                else:
                    current.extend((px(i), py(v)))
            if current:
                pieces.append(current)
            for points in pieces:
                if len(points) >= 4:
                    self.create_line(points, fill=self.tint(colour, 0.22), width=u(8),
                                     capstyle="round", joinstyle="round")
                    self.create_line(points, fill=colour, width=u(2.5), capstyle="round",
                                     joinstyle="round")
        r = u(6)
        for colour, lap, value in self.markers:
            if value is None:
                continue
            x, y = px(lap - 1), py(value)
            self.create_oval(x - r, y - r, x + r, y + r, fill="#FFFFFF", outline=colour,
                             width=u(2.5))
        # labels at the end of each line, nudged apart so they don't overlap
        line = self.fonts.small.metrics("linespace")
        block = 2 * line + u(4)  # name + value
        ends = sorted([py(last), name, colour, last] for name, colour, last in self._ends())
        for i in range(1, len(ends)):
            ends[i][0] = max(ends[i][0], ends[i - 1][0] + block)
        overflow = ends[-1][0] + block / 2 - y2 if ends else 0
        for y, name, colour, value in ends:
            y = max(y1 + block / 2, y - max(0, overflow))
            self.create_text(x2 + u(10), y - line / 2, text=name, anchor="w",
                             fill=self.text_colour(colour), font=self.fonts.small_bold)
            self.create_text(x2 + u(10), y + line / 2 + u(1), text=self.value_fmt(value),
                             anchor="w", fill=theme.SECONDARY, font=self.fonts.small)

    def hover(self, x, y):
        if not self._geometry:
            return
        n, px, py = self._geometry
        x1, y1, x2, y2 = self.plot_area()
        index = max(0, min(n - 1, round((x - x1) / max(1, x2 - x1) * (n - 1))))
        hx = px(index)
        self.create_line(hx, y1, hx, y2, fill=self.tint(theme.INK, 0.4), width=u(1),
                         tags="hover")
        rows = []
        r = u(5)
        for name, colour, ys in self.series:
            if index < len(ys) and ys[index] is not None:
                vy = py(ys[index])
                self.create_oval(hx - r, vy - r, hx + r, vy + r, fill=colour, outline="#FFFFFF",
                                 width=u(2), tags="hover")
                rows.append((colour, name, self.value_fmt(ys[index])))
        rows.extend(self.extra_rows(index + 1))
        self.tooltip(hx, y, f"Lap {index + 1}", rows)


class GroupedBarChart(Chart):
    """Win probability for each strategy across race scenarios."""

    def __init__(self, parent, fonts, height=320):
        super().__init__(parent, fonts, height)
        self.margin = (60, 48, 24, 62)
        self.groups: List[Tuple[str, str, List[float]]] = []  # (label, sublabel, values)
        self.series: List[Tuple[str, str]] = []

    def set_data(self, groups, series):
        self.groups, self.series = groups, series
        self.refresh()

    def _layout(self):
        x1, y1, x2, y2 = self.plot_area()
        group_w = (x2 - x1) / max(1, len(self.groups))
        bar_w = min(u(40), group_w * 0.72 / max(1, len(self.series)))
        return x1, y1, x2, y2, group_w, bar_w

    def draw(self):
        if not self.groups or self.winfo_width() < u(120):
            return
        self.draw_y_axis(0, 100, "{:g}%", title="Win probability")
        x1, y1, x2, y2, group_w, bar_w = self._layout()
        caption = self.fonts.caption
        # percentages above the bars only when they fit side by side
        show_values = caption.measure("100%") + u(2) <= bar_w
        r = u(7)
        for g, (label, sub, values) in enumerate(self.groups):
            gx = x1 + g * group_w + group_w / 2
            start = gx - bar_w * len(values) / 2
            for i, value in enumerate(values):
                colour = self.series[i][1]
                bx1, bx2 = start + i * bar_w + u(3), start + (i + 1) * bar_w - u(3)
                rounded_rect(self, bx1, y1, bx2, y2, r, fill=self.tint(theme.INK, 0.04),
                             outline="")
                top = y2 - value * (y2 - y1)
                if value > 0.004:
                    rounded_rect(self, bx1, min(top, y2 - u(10)), bx2, y2, r, fill=colour,
                                 outline=theme.blend(colour, theme.INK, 0.15))
                    if y2 - top > u(18):
                        rounded_rect(self, bx1 + u(3), top + u(3), bx2 - u(3), top + u(14),
                                     u(5), fill=theme.blend(colour, "#FFFFFF", 0.35), outline="")
                if value >= 0.01 and show_values:
                    self.create_text((bx1 + bx2) / 2, min(top, y2 - u(10)) - u(11),
                                     text=f"{value * 100:.0f}%", fill=theme.TEXT, font=caption)
            self.create_text(gx, y2 + u(18), text=label, fill=theme.TEXT,
                             font=self.fonts.small_bold)
            self.create_text(gx, y2 + u(38), text=sub, fill=theme.SECONDARY,
                             font=self.fonts.small)
        self.legend(self.series)

    def hover(self, x, y):
        x1, y1, x2, y2, group_w, _ = self._layout()
        g = int((x - x1) / group_w)
        if not 0 <= g < len(self.groups):
            return
        label, sub, values = self.groups[g]
        gx1 = x1 + g * group_w
        rounded_rect(self, gx1 + u(4), y1 - u(2), gx1 + group_w - u(4), y2 + u(2), u(12),
                     fill="", outline=self.tint(theme.ACCENT, 0.6), width=u(2), tags="hover")
        rows = [(colour, name, f"{v * 100:.1f}%") for (name, colour), v in zip(self.series, values)]
        self.tooltip(gx1 + group_w / 2, y, f"{label} · {sub}", rows)


class DensityChart(Chart):
    """Smoothed distributions of the finishing gap to the rival, one per strategy."""

    def __init__(self, parent, fonts, height=320):
        super().__init__(parent, fonts, height)
        self.margin = (60, 72, 24, 62)
        self.series: List[Tuple[str, str, List[float]]] = []
        self.x_title = ""
        self._model = None

    def set_data(self, series, x_title=""):
        self.series, self.x_title = series, x_title
        self.refresh()

    def _densities(self, bins=48):
        values = sorted(v for _, _, vs in self.series for v in vs)
        lo = values[int(0.01 * (len(values) - 1))]
        hi = values[int(0.99 * (len(values) - 1))]
        lo, hi = min(lo, -1.0), max(hi, 1.0)
        width = (hi - lo) / bins
        kernel = (1, 4, 6, 4, 1)
        out = []
        for _, _, vs in self.series:
            counts = [0] * bins
            for v in vs:
                if lo <= v <= hi:
                    counts[min(bins - 1, int((v - lo) / width))] += 1
            smooth = []
            for i in range(bins):
                total = sum(k * counts[i + j - 2] for j, k in enumerate(kernel)
                            if 0 <= i + j - 2 < bins)
                smooth.append(total / 16 / max(1, len(vs)))
            out.append(smooth)
        return lo, hi, width, out

    def draw(self):
        if not self.series or self.winfo_width() < u(120):
            return
        lo, hi, width, dens = self._densities()
        top = max(max(d) for d in dens) * 1.15 or 1
        self.draw_y_axis(0, top * 100, "{:g}%", title="Share of races")
        x1, y1, x2, y2 = self.plot_area()

        def px(v):
            return x1 + (v - lo) / (hi - lo) * (x2 - x1)

        def py(share):
            return y2 - share / top * (y2 - y1)

        self._model = (lo, hi, width, dens, px)
        zero = px(0)
        self.create_rectangle(x1, y1, zero, y2, fill=self.tint(theme.GREEN, 0.06), outline="")
        self.create_rectangle(zero, y1, x2, y2, fill=self.tint(theme.RED, 0.05), outline="")
        caption = self.fonts.caption
        ahead, behind = "◀  AHEAD OF RIVAL", "BEHIND RIVAL  ▶"
        if (zero - x1 < caption.measure(ahead) + u(14)
                or x2 - zero < caption.measure(behind) + u(14)):
            ahead, behind = "◀  AHEAD", "BEHIND  ▶"
        self.create_text(zero - u(10), y1 - u(20), text=ahead, anchor="e",
                         fill=theme.GREEN, font=caption)
        self.create_text(zero + u(10), y1 - u(20), text=behind, anchor="w",
                         fill=theme.RED, font=caption)

        lines = []
        for (name, colour, _), d in zip(self.series, dens):
            pts = [(px(lo + (i + 0.5) * width), py(share)) for i, share in enumerate(d)]
            poly = [px(lo), y2] + [c for p in pts for c in p] + [px(hi), y2]
            self.create_polygon(poly, fill=self.tint(colour, 0.16), outline="", smooth=True)
            lines.append(([c for p in pts for c in p], colour))
        for flat, colour in lines:
            self.create_line(flat, fill=colour, width=u(2.5), smooth=True, capstyle="round")
        self.create_line(zero, y1, zero, y2, fill=theme.TEXT, dash=(5, 4))

        legend = []
        for name, colour, vs in self.series:
            median = sorted(vs)[len(vs) // 2]
            if lo <= median <= hi:
                mx = px(median)
                self.create_line(mx, y1, mx, y2, fill=colour, dash=(2, 3), width=u(1.5))
            legend.append((f"{name} · median {median:+.1f} s", colour))
        ticks = [t for t in nice_ticks(lo, hi, 6) if lo <= t <= hi]
        widest = max((self.fonts.small.measure(f"{t:+g} s") for t in ticks), default=0)
        every = 1
        while every < len(ticks) and (x2 - x1) / len(ticks) * every < widest + u(12):
            every += 1
        for i, tick in enumerate(ticks):
            if i % every == 0:
                self.create_text(px(tick), y2 + u(18), text=f"{tick:+g} s" if tick else "0",
                                 fill=theme.TERTIARY, font=self.fonts.small)
        self.create_text((x1 + x2) / 2, y2 + u(40), text=self.x_title, fill=theme.SECONDARY,
                         font=self.fonts.small)
        short = [(name, colour) for name, colour, _ in self.series]
        self.legend(self.fit_legend(legend, short, "Share of races"))

    def hover(self, x, y):
        if not self._model:
            return
        lo, hi, width, dens, px = self._model
        x1, y1, x2, y2 = self.plot_area()
        value = lo + (x - x1) / max(1, x2 - x1) * (hi - lo)
        self.create_line(x, y1, x, y2, fill=self.tint(theme.INK, 0.4), tags="hover")
        rows = []
        for name, colour, vs in self.series:
            ahead = sum(1 for v in vs if v < value) / max(1, len(vs))
            rows.append((colour, f"{name} does better than this", f"{ahead * 100:.0f}%"))
        word = "ahead of" if value < 0 else "behind"
        self.tooltip(x, y, f"{abs(value):.1f} s {word} the rival", rows)
