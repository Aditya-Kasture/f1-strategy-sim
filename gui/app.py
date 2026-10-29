# Pit Strategy: F1 pit stop strategy simulator (COMP9001). To run the program: python main.py (see README.txt)
"""The main window: a glass settings panel on the left, results on the right."""

from __future__ import annotations

import math
import queue
import random
import sys
import threading
import tkinter as tk
from tkinter import messagebox
from typing import Dict, List, Optional

from simulator.engine import generate_events, no_events, simulate_driver
from simulator.explain import Recommendation, build_recommendation, pct
from simulator.models import DRY, SLICKS, WET_TIRES, Circuit, Compound, Driver
from simulator.montecarlo import MonteCarloSimulator, SimulationResult, StrategyStats
from simulator.strategy import expected_drying_lap

from . import theme
from .glass import Backdrop, GlassCard, Scene, TextBackdrop, rounded_rect
from .widgets import (DensityChart, GroupedBarChart, LineChart, MeterBar, PillButton,
                      ProgressBar, ScrollBar, SegmentedControl, Slider, StintBar, TrackMap)

TABS = ("Overview", "Why", "Race trace", "Lap times", "Scenarios", "Rival")
SIDEBAR_WIDTH = 344
BAND_COLOURS = {"SC": "#FFD84D", "VSC": "#FFE9A8", "RAIN": "#9CC3FF", "WET START": "#B9D3FF"}
MIN_RUNS, MAX_RUNS = 100, 20000
FIELD_BORDER = "#878E9C"  # 3:1 against the panel, as WCAG asks for control outlines
HAIRLINE = "#D3D8E2"
CONDITION_NAMES = {"dry": "Dry", "damp": "Damp (Intermediates)", "wet": "Heavy rain (Wets)"}


class StrategyApp:
    def __init__(self, root: tk.Tk, circuits: List[Circuit], compounds: Dict[str, Compound],
                 outlines: Optional[Dict[str, list]] = None):
        self.root = root
        theme.set_scale(root)  # before anything is sized: layout grows with the text
        self.circuits = circuits
        self.compounds = compounds
        self.outlines = outlines or {}
        self.fonts = theme.Fonts(root)
        self.circuit = circuits[0]
        self.result: Optional[SimulationResult] = None
        self.recommendation: Optional[Recommendation] = None
        self.worker: Optional[threading.Thread] = None
        self.messages: "queue.Queue" = queue.Queue()
        self.progress_value = 0.0
        self.side_scene = Scene(theme.SIDE_BLOBS)
        self.scene = Scene(theme.MAIN_BLOBS)
        self._refresh_pending = False
        self._gallery_columns = 0
        self.stale = False

        root.title("Pit Strategy Simulator")
        root.configure(bg=theme.BASE)
        screen_w, screen_h = root.winfo_screenwidth(), root.winfo_screenheight()
        root.minsize(min(theme.px(1080), screen_w - 40), min(theme.px(680), screen_h - 80))
        width = min(theme.px(1400), screen_w - 80)
        height = min(theme.px(900), screen_h - 100)
        root.geometry(f"{width}x{height}+40+30")

        self._build_sidebar()
        self._build_main()
        self.select_circuit(self.circuit.name)
        root.bind("<Return>", lambda e: self.run_simulation())
        root.bind("<Configure>", lambda e: self.refresh_glass() if e.widget is root else None,
                  add="+")

    # ------------------------------------------------------------------ helpers ----
    def refresh_glass(self):
        """Repaint the glass once the layout has settled."""
        if not self._refresh_pending:
            self._refresh_pending = True
            self.root.after(40, self._do_refresh)

    def _do_refresh(self):
        self._refresh_pending = False
        self.root.update_idletasks()
        self.side_scene.refresh()
        self.scene.refresh()

    def _label(self, parent, text="", font=None, fg=theme.TEXT, **kwargs):
        kwargs.setdefault("anchor", "w")
        kwargs.setdefault("justify", "left")
        return tk.Label(parent, text=text, bg=theme.CARD, fg=fg, font=font or self.fonts.body,
                        **kwargs)

    def _caption(self, parent, text, pady=(12, 5)):
        self._label(parent, text.upper(), self.fonts.caption, theme.SECONDARY).pack(
            anchor="w", pady=theme.pad(pady))

    def _wrap(self, label: tk.Label, parent: tk.Widget, margin: int = 0):
        """Keep a label's text wrapped to its parent's width."""
        parent.bind("<Configure>", lambda e: label.configure(
            wraplength=max(theme.px(120), e.width - theme.px(margin) - 4)), add="+")
        return label

    def _bind_click(self, widget, callback):
        widget.bind("<Button-1>", lambda e: callback(), add="+")
        for child in widget.winfo_children():
            self._bind_click(child, callback)

    @property
    def start_compound(self) -> str:
        return self.dry_control.value or self.wet_control.value or "Medium"

    # ------------------------------------------------------------------ sidebar ----
    def _build_sidebar(self):
        self.side_bg = Backdrop(self.root, self.side_scene, width=SIDEBAR_WIDTH)
        self.side_bg.pack(side="left", fill="y")
        self.side_bg.pack_propagate(False)
        self.side_scene.origin = self.side_bg
        panel = GlassCard(self.side_bg, self.side_scene, padding=20,
                          radius=theme.RADIUS["panel"] + 6, mix=0.62, fill_height=True)
        panel.pack(fill="both", expand=True, padx=theme.pad((14, 6)), pady=theme.pad(12))
        side = panel.body

        brand = tk.Frame(side, bg=theme.CARD)
        brand.pack(fill="x")
        u = theme.scaled
        logo = tk.Canvas(brand, width=theme.px(40), height=theme.px(40), bg=theme.CARD,
                         highlightthickness=0)
        logo.pack(side="left")
        rounded_rect(logo, 0, 0, u(40), u(40), u(12), fill="#E10600", outline="")
        rounded_rect(logo, u(2), u(2), u(38), u(20), u(9), fill="#F0443C", outline="")
        logo.create_oval(u(9), u(9), u(31), u(31), fill="#1D1D1F", outline="")
        logo.create_oval(u(14), u(14), u(26), u(26), fill="#F5C400", outline="")
        logo.create_oval(u(17), u(17), u(23), u(23), fill="#1D1D1F", outline="")
        names = tk.Frame(brand, bg=theme.CARD)
        names.pack(side="left", padx=theme.pad(10))
        self._label(names, "Pit Strategy", self.fonts.heading).pack(anchor="w")
        tagline = self._label(names, "Formula 1 race simulator", self.fonts.small,
                              theme.SECONDARY)
        tagline.pack(anchor="w")

        def fit_height(event):
            # on short screens the tagline goes so the controls and status still fit
            if event.widget is self.root:
                show = event.height >= theme.px(740)
                if show != bool(tagline.winfo_manager()):
                    if show:
                        tagline.pack(anchor="w")
                    else:
                        tagline.pack_forget()
        self.root.bind("<Configure>", fit_height, add="+")

        self._caption(side, "Circuit", pady=(14, 4))
        row = tk.Frame(side, bg=theme.CARD, cursor="hand2")
        row.pack(fill="x")
        self.side_map = TrackMap(row, height=44, line_width=2.5, glow=False)
        self.side_map.configure(width=theme.px(70))
        self.side_map.pack(side="left")
        text = tk.Frame(row, bg=theme.CARD)
        text.pack(side="left", fill="x", expand=True, padx=theme.pad((10, 0)))
        self.side_name = self._label(text, "", self.fonts.body_bold,
                                     wraplength=theme.px(SIDEBAR_WIDTH - 150))
        self.side_name.pack(anchor="w")
        self.side_detail = self._label(text, "", self.fonts.small, theme.SECONDARY,
                                       wraplength=theme.px(SIDEBAR_WIDTH - 150))
        self.side_detail.pack(anchor="w")
        browse = self._label(side, "Browse all 24 circuits  ›", self.fonts.small_bold,
                             theme.ACCENT, cursor="hand2")
        browse.pack(anchor="w", pady=theme.pad((6, 0)))
        self._bind_click(row, self.show_gallery)
        self._bind_click(browse, self.show_gallery)

        self._caption(side, "Starting tire")
        dots = {name: self.compounds[name].colour for name in SLICKS + WET_TIRES}
        self.dry_control = SegmentedControl(side, SLICKS, self.fonts, value="Medium", dots=dots,
                                            command=lambda v: self._tire_changed("dry"))
        self.dry_control.pack(fill="x")
        self.wet_control = SegmentedControl(side, WET_TIRES, self.fonts, value=None, dots=dots,
                                            command=lambda v: self._tire_changed("wet"))
        self.wet_control.pack(fill="x", pady=theme.pad((6, 0)))
        self.tire_hint = self._label(side, "", self.fonts.small, theme.SECONDARY,
                                     wraplength=theme.px(SIDEBAR_WIDTH - 70))
        self.tire_hint.pack(anchor="w", fill="x", pady=theme.pad((5, 0)))

        row = tk.Frame(side, bg=theme.CARD)
        row.pack(fill="x", pady=theme.pad((12, 0)))
        self.rain_caption = self._label(row, "RAIN CHANCE", self.fonts.caption, theme.SECONDARY)
        self.rain_caption.pack(side="left")
        self.rain_label = self._label(row, "", self.fonts.small_bold)
        self.rain_label.pack(side="right")
        self.rain_slider = Slider(side, 0.0, 1.0, 0.0, command=self._rain_changed, step=0.05)
        self.rain_slider.pack(fill="x", pady=theme.pad((4, 0)))

        row = tk.Frame(side, bg=theme.CARD)
        row.pack(fill="x", pady=theme.pad((8, 0)))
        self._label(row, "RIVAL PACE", self.fonts.caption, theme.SECONDARY).pack(side="left")
        self.rival_label = self._label(row, "", self.fonts.small_bold)
        self.rival_label.pack(side="right")
        self.rival_slider = Slider(side, -1.0, 1.0, 0.0, command=self._rival_changed, step=0.05)
        self.rival_slider.pack(fill="x", pady=theme.pad((4, 0)))
        self._rival_changed(0.0, stale=False)

        self._caption(side, "Simulated races", pady=(8, 5))
        entry_row = tk.Frame(side, bg=theme.CARD)
        entry_row.pack(fill="x")
        self.runs_box = tk.Frame(entry_row, bg=FIELD_BORDER, padx=theme.pad(1), pady=theme.pad(1))
        self.runs_box.pack(side="left")
        self.runs_var = tk.StringVar(value="3000")
        self.runs_entry = tk.Entry(self.runs_box, textvariable=self.runs_var, width=6,
                                   relief="flat", bg="#FFFFFF", fg=theme.TEXT,
                                   font=self.fonts.body, insertbackground=theme.TEXT,
                                   highlightthickness=0, bd=6)
        self.runs_entry.pack()
        self.runs_entry.bind("<FocusIn>", lambda e: self._style_runs_box(), add="+")
        self.runs_entry.bind("<FocusOut>", lambda e: self._style_runs_box(), add="+")
        self.runs_var.trace_add("write", lambda *a: self._runs_changed())
        for label, value in (("1,000", "1000"), ("3,000", "3000"), ("5,000", "5000")):
            link = self._label(entry_row, label, self.fonts.small_bold, theme.ACCENT,
                               cursor="hand2", padx=theme.pad(3))
            link.pack(side="left", padx=theme.pad((5, 0)))
            link.bind("<Button-1>", lambda e, v=value: self.runs_var.set(v))
            link.bind("<Enter>", lambda e, l=link: l.configure(font=self.fonts.small_bold,
                                                               fg=theme.ACCENT_HOVER))
            link.bind("<Leave>", lambda e, l=link: l.configure(fg=theme.ACCENT))
        self.runs_error = self._label(side, "", self.fonts.small_bold, theme.RED,
                                      wraplength=theme.px(SIDEBAR_WIDTH - 70))

        bottom = tk.Frame(side, bg=theme.CARD)
        bottom.pack(side="bottom", fill="x")
        self.run_button = PillButton(bottom, "Simulate 3,000 races", self.run_simulation,
                                     self.fonts)
        self.run_button.pack(fill="x")
        self.progress = ProgressBar(bottom)
        self.progress.pack(fill="x", pady=theme.pad((8, 0)))
        self.status = self._label(bottom, "Press Enter or click to start",
                                  self.fonts.small, theme.SECONDARY,
                                  wraplength=theme.px(SIDEBAR_WIDTH - 70))
        self.status.pack(anchor="w", fill="x", pady=theme.pad((4, 0)))

        # Widen the sidebar if its content needs more room than the default (long labels
        # in another font, or a high-DPI screen), so no control gets squashed.
        side.update_idletasks()
        needed = (max(child.winfo_reqwidth() for child in side.winfo_children())
                  + 2 * panel.padding + theme.px(14 + 6) + theme.px(4))
        if needed > int(self.side_bg.cget("width")):
            self.side_bg.configure(width=needed)

    # ------------------------------------------------------- run button and races ----
    def _runs_value(self):
        """(number of races, error message). Exactly one of them is set."""
        text = self.runs_var.get().strip().replace(",", "")
        try:
            runs = int(text)
        except ValueError:
            return None, "Enter a whole number of races, like 3000."
        if not MIN_RUNS <= runs <= MAX_RUNS:
            return None, f"Use {MIN_RUNS:,} to {MAX_RUNS:,} races."
        return runs, ""

    def _style_runs_box(self):
        _, error = self._runs_value()
        focused = self.root.focus_get() is self.runs_entry
        self.runs_box.configure(bg=theme.RED if error else theme.ACCENT if focused
                                else FIELD_BORDER,
                                padx=theme.px(2 if error or focused else 1),
                                pady=theme.px(2 if error or focused else 1))

    def _runs_changed(self):
        _, error = self._runs_value()
        self.runs_error.configure(text=error)
        if error:
            self.runs_error.pack(anchor="w", fill="x", pady=theme.pad((6, 0)), after=self.runs_box.master)
        else:
            self.runs_error.pack_forget()
        self._style_runs_box()
        self.mark_stale()
        self._update_run_button()

    def _update_run_button(self):
        """The button says exactly what pressing it will do."""
        if self.worker and self.worker.is_alive():
            return
        runs, error = self._runs_value()
        if error:
            self.run_button.set_text("Fix the number of races")
            self.run_button.set_enabled(False)
        elif self.stale:
            self.run_button.set_text("Re-run with new settings")
            self.run_button.set_enabled(True)
        else:
            self.run_button.set_text(f"Simulate {runs:,} races")
            self.run_button.set_enabled(True)

    def _tire_changed(self, which):
        if which == "dry":
            self.wet_control.set(None)
        else:
            self.dry_control.set(None)
        self._update_tire_hint()
        self.mark_stale()

    def _update_tire_hint(self):
        start = self.start_compound
        if start in WET_TIRES:
            lap = expected_drying_lap(self.circuit, start)
            start_text = "Heavy rain" if start == "Wet" else "Damp"
            self.tire_hint.configure(text=f"{start_text} start · dries ~lap {lap}")
            self.rain_caption.configure(text="LATER SHOWER CHANCE")
        else:
            self.tire_hint.configure(text="Dry race: two compounds required")
            self.rain_caption.configure(text="RAIN CHANCE")

    def _rain_changed(self, value, stale=True):
        self.rain_label.configure(text=f"{value * 100:.0f}%")
        if stale:
            self.mark_stale()

    def _rival_changed(self, value, stale=True):
        if abs(value) < 0.001:
            text = "Same pace"
        elif value < 0:
            text = f"{-value:.2f} s/lap faster"
        else:
            text = f"{value:.2f} s/lap slower"
        self.rival_label.configure(text=text)
        if stale:
            self.mark_stale()

    # --------------------------------------------------------------------- main ----
    def _build_main(self):
        self.canvas = tk.Canvas(self.root, bg=theme.BASE, highlightthickness=0, bd=0)
        self.scrollbar = ScrollBar(self.root, self.canvas)
        self.scrollbar.pack(side="right", fill="y", padx=theme.pad((0, 4)), pady=theme.pad(12))
        self.canvas.pack(side="left", fill="both", expand=True)
        self.content = Backdrop(self.canvas, self.scene)
        self.scene.origin = self.content
        self._content_window = self.canvas.create_window(0, 0, window=self.content, anchor="nw")
        self.canvas.bind("<Configure>", self._resize_content)
        self.content.bind("<Configure>", lambda e: self.canvas.configure(
            scrollregion=(0, 0, e.width, e.height)), add="+")
        self.root.bind_all("<MouseWheel>", self._on_wheel)
        self.root.bind_all("<Button-4>", lambda e: self._scroll(-1))
        self.root.bind_all("<Button-5>", lambda e: self._scroll(1))

        page = Backdrop(self.content, self.scene)
        page.pack(fill="both", expand=True, padx=theme.pad((22, 18)), pady=theme.pad(24))

        self.header = TextBackdrop(page, self.scene, height=74)
        self.header.pack(fill="x")
        self.empty_frame = Backdrop(page, self.scene)
        self.results_frame = Backdrop(page, self.scene)
        self._build_empty_state()
        self._build_results()
        self.empty_frame.pack(fill="both", expand=True, pady=theme.pad((18, 0)))

    def _resize_content(self, event):
        self.canvas.itemconfigure(self._content_window, width=event.width)
        needed = self.content.winfo_reqheight()
        self.canvas.itemconfigure(self._content_window, height=max(event.height, needed))

    def _on_wheel(self, event):
        if sys.platform == "darwin":
            self._scroll(-event.delta)
        else:
            self._scroll(-int(event.delta / 120))

    def _scroll(self, units):
        if self.content.winfo_height() > self.canvas.winfo_height():
            self.canvas.yview_scroll(units, "units")

    def _refresh_scroll(self):
        self.root.update_idletasks()
        needed = self.content.winfo_reqheight()
        self.canvas.itemconfigure(self._content_window,
                                  height=max(self.canvas.winfo_height(), needed))
        self.refresh_glass()

    # --------------------------------------------------------------- empty state ----
    def _build_empty_state(self):
        frame = self.empty_frame
        facts = GlassCard(frame, self.scene, padding=24)
        facts.pack(fill="x")
        body = facts.body
        body.columnconfigure(0, weight=4, uniform="f")
        body.columnconfigure(1, weight=7, uniform="f")
        map_col = tk.Frame(body, bg=theme.CARD)
        map_col.grid(row=0, column=0, sticky="nsew", padx=theme.pad((0, 22)))
        self._label(map_col, "TRACK LAYOUT", self.fonts.caption, theme.SECONDARY).pack(anchor="w")
        self.big_map = TrackMap(map_col, height=250, line_width=6, animate=True)
        self.big_map.pack(fill="both", expand=True, pady=theme.pad((6, 0)))

        info = tk.Frame(body, bg=theme.CARD)
        info.grid(row=0, column=1, sticky="nsew")
        self._label(info, "CIRCUIT FACTS  ·  APPROXIMATE", self.fonts.caption,
                    theme.SECONDARY).pack(anchor="w")
        grid = tk.Frame(info, bg=theme.CARD)
        grid.pack(fill="x", pady=theme.pad((8, 0)))
        for c in range(3):
            grid.columnconfigure(c, weight=1, uniform="g")
        self.fact_values = {}
        for i, key in enumerate(("Laps", "Lap length", "Pit stop loss", "Tire wear",
                                 "SC chance", "Rain chance")):
            cell = tk.Frame(grid, bg=theme.CARD)
            cell.grid(row=i // 3, column=i % 3, sticky="w", pady=theme.pad(6), padx=theme.pad((0, 8)))
            value = self._label(cell, "", self.fonts.large)
            value.pack(anchor="w")
            self._label(cell, key, self.fonts.small, theme.SECONDARY).pack(anchor="w")
            self.fact_values[key] = value
        self._label(info, "USUAL NUMBER OF STOPS HERE  ·  APPROX.", self.fonts.caption,
                    theme.SECONDARY).pack(anchor="w", pady=theme.pad((14, 6)))
        self.history_rows = {}
        for stops in (1, 2, 3):
            row = tk.Frame(info, bg=theme.CARD)
            row.pack(fill="x", pady=theme.pad(3))
            self._label(row, f"{stops}-stop", width=7).pack(side="left")
            share = self._label(row, "", fg=theme.SECONDARY, width=5, anchor="e")
            share.pack(side="right")
            bar = MeterBar(row, theme.STRATEGY_COLOURS[stops], height=12)
            bar.pack(side="left", fill="x", expand=True, padx=theme.pad(10))
            self.history_rows[stops] = (bar, share)

        self.gallery_title = TextBackdrop(frame, self.scene, height=40)
        self.gallery_title.pack(fill="x", pady=theme.pad((18, 6)))
        self.gallery_title.set_text("title", 2, 22, f"All {len(self.circuits)} circuits · "
                                    "2026 calendar", self.fonts.large, theme.TEXT)
        self.gallery_title.set_text("hint", -4, 26, "Click a track to select it",
                                    self.fonts.small, theme.SECONDARY, anchor="e")

        self.gallery = Backdrop(frame, self.scene)
        self.gallery.pack(fill="x")
        self.gallery_tiles: Dict[str, GlassCard] = {}
        for circuit in self.circuits:
            tile = GlassCard(self.gallery, self.scene, padding=12, radius=18, mix=0.66)
            tile.configure(cursor="hand2")
            track = TrackMap(tile.body, height=74, line_width=3, glow=False)
            track.pack(fill="x")
            track.set_points(self.outlines.get(circuit.name, []))
            name = self._label(tile.body, circuit.name, self.fonts.small_bold)
            name.pack(anchor="w", fill="x", pady=theme.pad((6, 0)))
            place = self._label(tile.body, f"R{circuit.round} · {circuit.country}",
                                self.fonts.small, theme.SECONDARY)
            place.pack(anchor="w", fill="x")
            self._wrap(name, tile.body)
            self._wrap(place, tile.body)
            self._bind_click(tile, lambda name=circuit.name: self.select_circuit(name, scroll=True))
            self._bind_hover(tile, circuit.name)
            self.gallery_tiles[circuit.name] = tile
        self.gallery.bind("<Configure>", self._layout_gallery, add="+")

        how = GlassCard(frame, self.scene, padding=24)
        how.pack(fill="x", pady=theme.pad((18, 0)))
        self._label(how.body, "HOW IT WORKS", self.fonts.caption, theme.SECONDARY).pack(anchor="w")
        steps = [
            ("1", "Plan", "Finds the best pit laps and tires for a 1, 2 and 3-stop race."),
            ("2", "Race", "Simulates every lap: tire wear, fuel, pit stops, Safety Cars, VSCs "
                          "and rain."),
            ("3", "Repeat", "Runs thousands of races so luck evens out and each strategy gets "
                            "a win probability."),
            ("4", "Explain", "Recommends the best strategy and shows how much time it gains "
                             "over the others, and why."),
        ]
        step_row = tk.Frame(how.body, bg=theme.CARD)
        step_row.pack(fill="x")
        for i, (number, title, text) in enumerate(steps):
            step_row.columnconfigure(i, weight=1, uniform="s")
            cell = tk.Frame(step_row, bg=theme.CARD)
            cell.grid(row=0, column=i, sticky="new", pady=theme.pad((12, 0)), padx=theme.pad((0, 16)))
            size = theme.px(26)
            badge = tk.Canvas(cell, width=size, height=size, bg=theme.CARD, highlightthickness=0)
            badge.pack(side="left", anchor="n")
            badge.create_oval(1, 1, size - 1, size - 1, fill=theme.ACCENT_SOFT, outline="")
            badge.create_text(size / 2, size / 2, text=number, fill=theme.ACCENT,
                              font=self.fonts.small_bold)
            col = tk.Frame(cell, bg=theme.CARD)
            col.pack(side="left", fill="x", expand=True, padx=theme.pad((10, 0)))
            self._label(col, title, self.fonts.body_bold).pack(anchor="w")
            body_label = self._label(col, text, self.fonts.small, theme.SECONDARY)
            body_label.pack(anchor="w", fill="x")
            step_row.bind("<Configure>", lambda e, b=body_label: b.configure(
                wraplength=max(theme.px(80), e.width / 4 - theme.px(56))), add="+")
        note = self._label(how.body, "The circuit and tire figures are simplified "
                           "approximations for teaching, not official Formula 1 data.",
                           self.fonts.small, theme.SECONDARY)
        note.pack(anchor="w", fill="x", pady=theme.pad((16, 0)))
        self._wrap(note, how.body)

    def _bind_hover(self, tile, name):
        """Hover state for gallery tiles: a light accent outline."""
        def inside():
            x, y = self.root.winfo_pointerxy()
            widget = self.root.winfo_containing(x, y)
            return widget is not None and str(widget).startswith(str(tile))

        def update(_event):
            if name == self.circuit.name:
                return
            hovered = inside()
            if hovered != getattr(tile, "hovered", False):
                tile.hovered = hovered
                tile.set_outline(theme.blend(theme.ACCENT, "#FFFFFF", 0.4) if hovered else None, 2)

        tile.bind("<Enter>", update, add="+")
        tile.bind("<Leave>", lambda e: self.root.after(10, lambda: update(e)), add="+")

    def _layout_gallery(self, event=None):
        width = self.gallery.winfo_width()
        columns = max(3, min(6, width // theme.px(160)))
        if columns == self._gallery_columns:
            return
        self._gallery_columns = columns
        for c in range(6):
            self.gallery.columnconfigure(c, weight=1 if c < columns else 0,
                                         uniform="t" if c < columns else "")
        for i, tile in enumerate(self.gallery_tiles.values()):
            tile.grid(row=i // columns, column=i % columns, sticky="new", padx=theme.pad(5), pady=theme.pad(5))
        self.root.after(30, self._refresh_scroll)

    # ------------------------------------------------------------------ results ----
    def _build_results(self):
        frame = self.results_frame

        hero = GlassCard(frame, self.scene, padding=26, radius=theme.RADIUS["panel"] + 6,
                         mix=0.8)
        hero.pack(fill="x", pady=theme.pad((18, 0)))
        self.hero = hero
        hero.body.columnconfigure(0, weight=3, uniform="h")
        hero.body.columnconfigure(1, weight=2, uniform="h")
        left = tk.Frame(hero.body, bg=theme.CARD)
        left.grid(row=0, column=0, sticky="nsew", padx=theme.pad((0, 24)))
        top = tk.Frame(left, bg=theme.CARD)
        top.pack(fill="x")
        self.hero_map = TrackMap(top, height=110, line_width=3.5, glow=True)
        self.hero_map.configure(width=theme.px(150))
        self.hero_map.pack(side="right", anchor="n")
        texts = tk.Frame(top, bg=theme.CARD)
        texts.pack(side="left", fill="x", expand=True)
        badge = tk.Label(texts, text="RECOMMENDED", bg=theme.GREEN_SOFT,
                         fg=theme.GREEN, font=self.fonts.caption, padx=theme.pad(10), pady=theme.pad(4))
        badge.pack(anchor="w")
        self.hero_title = self._label(texts, "", self.fonts.hero)
        self.hero_title.pack(anchor="w", pady=theme.pad((10, 2)))
        self.hero_sequence = self._label(texts, "", self.fonts.heading, theme.SECONDARY)
        self.hero_sequence.pack(anchor="w", fill="x")
        self._wrap(self.hero_sequence, texts, margin=8)
        self.hero_bar = StintBar(left, self.fonts)
        self.hero_bar.pack(fill="x", pady=theme.pad((12, 6)))
        self.hero_summary = self._label(left, "", self.fonts.body)
        self.hero_summary.pack(anchor="w", fill="x")
        self._wrap(self.hero_summary, left)

        tiles = tk.Frame(hero.body, bg=theme.CARD)
        tiles.grid(row=0, column=1, sticky="nsew")
        self.tiles = {}
        for i, key in enumerate(("Win probability", "Time gained", "Beats rival")):
            tile = GlassCard(tiles, None, padding=14, radius=theme.RADIUS["inner"], mix=0.55)
            tile.pack(fill="x", pady=theme.pad((0 if i == 0 else 8, 0)))
            value = self._label(tile.body, "", self.fonts.stat)
            value.pack(side="left")
            text = tk.Frame(tile.body, bg=theme.CARD)
            text.pack(side="left", fill="x", expand=True, padx=theme.pad((10, 0)))
            heading = self._label(text, key, self.fonts.small_bold)
            heading.pack(anchor="w", fill="x")
            note = self._label(text, "", self.fonts.small, theme.SECONDARY)
            note.pack(anchor="w", fill="x")
            tile.body.bind("<Configure>", lambda e, v=value, h=heading, n=note: [
                label.configure(wraplength=max(theme.px(80),
                                               e.width - v.winfo_reqwidth() - theme.px(14)))
                for label in (h, n)], add="+")
            self.tiles[key] = (value, note)

        self.tab_control = SegmentedControl(frame, TABS, self.fonts, value=TABS[0],
                                            command=self.show_tab, height=38,
                                            font=self.fonts.body)
        self.tab_control.configure(bg=theme.BASE)
        self.tab_control.pack(fill="x", pady=theme.pad((20, 14)))

        self.tab_holder = Backdrop(frame, self.scene)
        self.tab_holder.pack(fill="both", expand=True)
        self.tabs = {name: Backdrop(self.tab_holder, self.scene) for name in TABS}
        self._build_overview_tab(self.tabs["Overview"])
        self._build_why_tab(self.tabs["Why"])
        self._build_trace_tab(self.tabs["Race trace"])
        self._build_laps_tab(self.tabs["Lap times"])
        self._build_scenarios_tab(self.tabs["Scenarios"])
        self._build_rival_tab(self.tabs["Rival"])
        self.show_tab(TABS[0])

    def show_tab(self, name):
        for frame in self.tabs.values():
            frame.pack_forget()
        self.tabs[name].pack(fill="both", expand=True)
        self.root.after(30, self._refresh_scroll)

    def _chart_card(self, parent, title, chart_cls, height=330):
        card = GlassCard(parent, self.scene, padding=22, radius=theme.RADIUS["panel"])
        card.pack(fill="x")
        top = tk.Frame(card.body, bg=theme.CARD)
        top.pack(fill="x")
        self._label(top, title, self.fonts.heading).pack(side="left", anchor="w")
        sub = self._label(card.body, "", self.fonts.small, theme.SECONDARY)
        sub.pack(anchor="w", fill="x", pady=theme.pad((2, 10)))
        self._wrap(sub, card.body)
        chart = chart_cls(card.body, self.fonts, height=height)
        chart.pack(fill="x")
        hint = self._label(card.body, "Hover over the chart to see exact values",
                           self.fonts.small, theme.SECONDARY)
        hint.pack(anchor="e", pady=theme.pad((6, 0)))
        return top, sub, chart

    # Rows of the comparison table: (label, explanation shown under it)
    TABLE_ROWS = (
        ("Fastest in", "share of races this plan won"),
        ("Avg. gap to best", "average finishing time behind"),
        ("Beats the rival", "races finished ahead of them"),
        ("Time in pit lane", "average, including the stops"),
        ("Lost to tire wear", "average, versus new tires"),
        ("Stops made", "average, Safety Cars can add one"),
        ("Cheap stops", "made under a Safety Car or VSC"),
    )

    def _build_overview_tab(self, tab):
        """One table with a column per strategy, so every number lines up for comparing."""
        card = GlassCard(tab, self.scene, padding=24, radius=theme.RADIUS["panel"])
        card.pack(fill="x")
        self.overview_card = card
        self._label(card.body, "Compare the three strategies", self.fonts.large).pack(anchor="w")
        sub = self._label(card.body, "Every strategy raced the same simulated races, with the "
                          "same Safety Cars, VSCs and weather, so the numbers compare fairly. "
                          "The highlighted column is the recommendation.",
                          self.fonts.small, theme.SECONDARY)
        sub.pack(anchor="w", fill="x", pady=theme.pad((4, 14)))
        self._wrap(sub, card.body)

        table = tk.Frame(card.body, bg=theme.CARD)
        table.pack(fill="x")
        table.columnconfigure(0, weight=0, minsize=theme.px(180))
        for c in (1, 2, 3):
            table.columnconfigure(c, weight=1, uniform="strategy")
        self.table_columns = {c: [] for c in (1, 2, 3)}  # cells to tint per strategy column
        self.table_lines = {c: [] for c in (1, 2, 3)}
        self.table = {}

        def cell(row, column, **pad):
            frame = tk.Frame(table, bg=theme.CARD, padx=theme.pad(14), pady=theme.px(pad.get("pady", 9)))
            frame.grid(row=row, column=column, sticky="nsew")
            frame.bind("<Configure>", lambda e, f=frame: [
                child.configure(wraplength=max(theme.px(60), e.width - theme.px(28)))
                for child in f.winfo_children()
                if isinstance(child, tk.Label) and not getattr(child, "keep_bg", False)],
                add="+")
            if column:
                self.table_columns[column].append(frame)
            return frame

        def line(row):
            for column in range(4):
                rule = tk.Frame(table, bg=HAIRLINE, height=1)
                rule.grid(row=row, column=column, sticky="ew")
                if column:
                    self.table_lines[column].append(rule)

        # header: strategy name, recommended badge, tires and stint bar
        cell(0, 0)
        for c in (1, 2, 3):
            head = cell(0, c, pady=theme.pad(12))
            top = tk.Frame(head, bg=theme.CARD)
            top.pack(fill="x")
            dot = tk.Canvas(top, width=theme.px(12), height=theme.px(12), bg=theme.CARD,
                            highlightthickness=0)
            dot.pack(side="left")
            name = self._label(top, "", self.fonts.heading)
            name.pack(side="left", padx=theme.pad((8, 0)))
            badge = tk.Label(head, text="RECOMMENDED", bg=theme.GREEN_SOFT, fg=theme.GREEN,
                             font=self.fonts.caption, padx=theme.pad(8), pady=theme.pad(3))
            badge.keep_bg = True
            full = self.fonts.caption.measure("RECOMMENDED") + theme.px(16 + 28 + 4)
            head.bind("<Configure>", lambda e, b=badge, full=full: b.configure(
                text="RECOMMENDED" if e.width >= full else "BEST"), add="+")
            seq = self._label(head, "", self.fonts.small, theme.SECONDARY)
            seq.pack(anchor="w", fill="x", pady=theme.pad((6, 8)))
            head.bind("<Configure>", lambda e, l=seq: l.configure(
                wraplength=max(theme.px(80), e.width - theme.px(30))), add="+")
            bar = StintBar(head, self.fonts)
            bar.pack(fill="x")
            self.table[("head", c)] = {"dot": dot, "name": name, "badge": badge, "seq": seq,
                                       "bar": bar}
        for r, (label, note) in enumerate(self.TABLE_ROWS):
            row = 2 + r * 2
            line(row - 1)
            left = cell(row, 0)
            self._label(left, label, self.fonts.body_bold).pack(anchor="w")
            note_label = self._label(left, note, self.fonts.small, theme.SECONDARY,
                                     wraplength=theme.px(170))
            note_label.pack(anchor="w")
            for c in (1, 2, 3):
                box = cell(row, c)
                value = self._label(box, "", self.fonts.heading if r == 0 else self.fonts.body_bold)
                value.pack(anchor="w")
                extra = None
                if r == 0:
                    extra = MeterBar(box, theme.STRATEGY_COLOURS[c], height=8)
                    extra.pack(fill="x", pady=theme.pad((6, 0)))
                else:
                    extra = self._label(box, "", self.fonts.small, theme.SECONDARY)
                    extra.pack(anchor="w")
                self.table[(label, c)] = (value, extra)

    def _paint(self, widget, colour):
        """Give a widget and everything inside it a new background (badges keep theirs)."""
        if getattr(widget, "keep_bg", False):
            return
        try:
            widget.configure(bg=colour)
        except tk.TclError:
            pass
        if hasattr(widget, "refresh"):
            widget.refresh()
        for child in widget.winfo_children():
            self._paint(child, colour)

    def _build_why_tab(self, tab):
        card = GlassCard(tab, self.scene, padding=26, radius=theme.RADIUS["panel"])
        card.pack(fill="x")
        self._label(card.body, "Why this strategy?", self.fonts.large).pack(anchor="w")
        self.why_frame = tk.Frame(card.body, bg=theme.CARD)
        self.why_frame.pack(fill="x", pady=theme.pad((6, 0)))
        self.why_card = card

    def _build_trace_tab(self, tab):
        top, self.trace_sub, self.trace_chart = self._chart_card(tab, "Race trace", LineChart)
        new_race = self._label(top, "↻  Roll another race", self.fonts.small_bold, theme.ACCENT,
                               cursor="hand2")
        new_race.pack(side="right")
        new_race.bind("<Enter>", lambda e: new_race.configure(fg=theme.ACCENT_HOVER))
        new_race.bind("<Leave>", lambda e: new_race.configure(fg=theme.ACCENT))
        new_race.bind("<Button-1>", lambda e: self.draw_trace("Random race"))
        self.trace_mode_control = SegmentedControl(top, ("Typical race", "Random race"),
                                                   self.fonts, value="Typical race",
                                                   command=self.draw_trace, height=30)
        self.trace_mode_control.pack(side="right", padx=theme.pad(12))

    def _build_laps_tab(self, tab):
        _, self.laps_sub, self.laps_chart = self._chart_card(tab, "Lap times and tire wear",
                                                             LineChart)

    def _build_scenarios_tab(self, tab):
        _, self.scenario_sub, self.scenario_chart = self._chart_card(
            tab, "When does each strategy win?", GroupedBarChart)

    def _build_rival_tab(self, tab):
        _, self.rival_sub, self.rival_chart = self._chart_card(
            tab, "Finishing gap to the rival", DensityChart)

    # ---------------------------------------------------------------- actions ----
    def select_circuit(self, name, scroll=False):
        self.circuit = next(c for c in self.circuits if c.name == name)
        c = self.circuit
        points = self.outlines.get(c.name, [])
        self.header.set_text("title", 2, 22, c.title, self.fonts.title, theme.TEXT)
        self.header.set_text("subtitle", 2, 58, f"Round {c.round}  ·  {c.country}  ·  "
                             f"{c.laps} laps  ·  {c.laps * c.length_km:.0f} km race distance",
                             self.fonts.body, theme.SECONDARY)
        self.side_name.configure(text=c.name)
        self.side_detail.configure(text=f"Round {c.round} · {c.country}")
        self.side_map.set_points(points)
        self.big_map.set_points(points)
        self.hero_map.set_points(points)
        sc_chance = 1 - math.exp(-c.sc_rate)
        values = {"Laps": str(c.laps), "Lap length": f"{c.length_km:.2f} km",
                  "Pit stop loss": f"{c.pit_loss:.1f} s",
                  "Tire wear": f"x{c.deg_multiplier:.2f}",
                  "SC chance": f"{sc_chance * 100:.0f}%",
                  "Rain chance": f"{c.rain_chance * 100:.0f}%"}
        for key, label in self.fact_values.items():
            label.configure(text=values[key])
        for stops, (bar, share) in self.history_rows.items():
            value = c.historical_strategies.get(stops, 0.0)
            bar.set(value)
            share.configure(text=pct(value))
        for tile_name, tile in self.gallery_tiles.items():
            tile.set_outline(theme.ACCENT if tile_name == name else None, 2)
        self.rain_slider.set(c.rain_chance)
        self._rain_changed(c.rain_chance, stale=False)
        self._update_tire_hint()
        self.show_empty_state()

    def show_gallery(self):
        self.show_empty_state()
        self.root.after(80, lambda: self.canvas.yview_moveto(
            max(0.0, self.gallery_title.winfo_rooty() - self.content.winfo_rooty() - theme.px(20))
            / max(1, self.content.winfo_height())))

    def show_empty_state(self):
        self.result = None
        self.results_frame.pack_forget()
        self.empty_frame.pack(fill="both", expand=True, pady=theme.pad((18, 0)))
        self._set_stale(False)
        self.canvas.yview_moveto(0)
        self.root.after(30, self._refresh_scroll)

    def _set_stale(self, stale: bool):
        self.stale = stale
        self.header.set_text("stale", -4, 58, "Results are for the old settings"
                             if stale else "", self.fonts.small_bold, theme.ACCENT, anchor="e")
        if hasattr(self, "run_button"):
            self._update_run_button()

    def mark_stale(self):
        if self.result is not None and not self.stale:
            self._set_stale(True)

    def run_simulation(self):
        if self.worker and self.worker.is_alive():
            return
        runs, error = self._runs_value()
        try:
            if error:
                raise ValueError(error)
            simulator = MonteCarloSimulator(
                self.circuit, self.compounds, self.start_compound, runs=runs,
                rain_chance=self.rain_slider.value, rival_pace=self.rival_slider.value)
        except ValueError as exc:
            self.status.configure(text=str(exc), fg=theme.RED)
            self.runs_entry.focus_set()
            self._runs_changed()
            return

        self.run_button.set_enabled(False)
        self.run_button.set_text("Simulating…  0%")
        self.progress.set(0)
        self.progress_value = 0.0
        self.status.configure(text=f"Simulating {simulator.runs:,} races at {self.circuit.country}…",
                              fg=theme.SECONDARY)

        def work():
            try:
                result = simulator.run(progress=self._set_progress)
                self.messages.put(("done", result, build_recommendation(result)))
            except Exception as exc:  # report anything unexpected instead of crashing
                self.messages.put(("error", exc, None))

        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()
        self.root.after(50, self._poll_worker)

    def _set_progress(self, value):
        self.progress_value = value  # called from the worker thread; read by _poll_worker

    def _poll_worker(self):
        self.progress.set(self.progress_value)
        try:
            kind, payload, rec = self.messages.get_nowait()
        except queue.Empty:
            self.run_button.set_text(f"Simulating…  {self.progress_value * 100:.0f}%")
            self.root.after(50, self._poll_worker)
            return
        self.worker = None
        self._update_run_button()
        if kind == "error":
            self.status.configure(text="Something went wrong", fg=theme.RED)
            messagebox.showerror("Simulation failed", f"The simulation stopped: {payload}")
            return
        self.progress.set(1)
        self.status.configure(text=f"Done: {payload.runs:,} races at {payload.circuit.country}",
                              fg=theme.SECONDARY)
        try:
            self.show_results(payload, rec)
        except Exception as exc:  # never leave the demo with a frozen window
            messagebox.showerror("Could not show results", str(exc))

    # ---------------------------------------------------------------- results ----
    def show_results(self, result: SimulationResult, rec: Recommendation):
        self.result, self.recommendation = result, rec
        self._set_stale(False)
        best = rec.best
        plan = best.strategy

        self.hero_title.configure(text=plan.name.capitalize())
        self.hero_sequence.configure(text=plan.sequence)
        self.hero_bar.set_strategy(plan)
        self.hero_summary.configure(text=rec.summary)

        win_value, win_note = self.tiles["Win probability"]
        win_value.configure(text=pct(best.win_probability), fg=theme.STRATEGY_TEXT[plan.stops])
        win_note.configure(text=f"of {result.runs:,} races")
        gain_value, gain_note = self.tiles["Time gained"]
        if rec.comparisons:
            nearest = rec.comparisons[0]
            gain_value.configure(text=f"{nearest.mean_gap:.1f}s")
            gain_note.configure(text=f"vs {nearest.other.strategy.name}, on average")
        rival_value, rival_note = self.tiles["Beats rival"]
        rival_value.configure(text=pct(best.rival_probability))
        rival_note.configure(text=f"rival on a {result.rival_strategy.name}")

        self._fill_overview(result, best)
        self._fill_why(rec)
        self.draw_trace(self.trace_mode_control.value)
        self._fill_laps(result)
        self._fill_scenarios(result)
        self._fill_rival(result)

        self.empty_frame.pack_forget()
        self.results_frame.pack(fill="both", expand=True)
        self.tab_control.set("Overview")
        self.show_tab("Overview")
        self.canvas.yview_moveto(0)

    def _fill_overview(self, result: SimulationResult, best: StrategyStats):
        best_mean = min(s.mean for s in result.stats)
        by_stops = {s.strategy.stops: s for s in result.stats}
        for c in (1, 2, 3):
            stat = by_stops.get(c)
            recommended = stat is best
            fill = theme.ACCENT_SOFT if recommended else self.overview_card.fill
            for frame in self.table_columns[c]:
                self._paint(frame, fill)
            for rule in self.table_lines[c]:
                rule.configure(bg=theme.blend(theme.ACCENT_SOFT, theme.ACCENT, 0.18)
                               if recommended else HAIRLINE)
            if stat is None:
                continue
            plan = stat.strategy
            head = self.table[("head", c)]
            head["dot"].delete("all")
            size = theme.px(12)
            head["dot"].create_oval(1, 1, size - 1, size - 1, fill=theme.STRATEGY_COLOURS[c],
                                    outline="")
            head["name"].configure(text=plan.name.capitalize())
            if recommended:
                head["badge"].pack(anchor="w", pady=theme.pad((6, 0)), after=head["name"].master)
            else:
                head["badge"].pack_forget()
            head["seq"].configure(text=f"{plan.sequence}\nPit on lap "
                                       f"{', '.join(map(str, plan.pit_laps))}")
            head["bar"].set_strategy(plan)

            gap = stat.mean - best_mean
            cheap = stat.early_stops / max(1, stat.runs)
            values = {
                "Fastest in": (pct(stat.win_probability), stat.win_probability),
                "Avg. gap to best": ("Fastest" if gap < 0.05 else f"+{gap:.1f} s",
                                     "on average" if gap < 0.05 else "behind on average"),
                "Beats the rival": (pct(stat.rival_probability), "of races"),
                "Time in pit lane": (f"{stat.breakdown_mean('pit'):.1f} s", "per race"),
                "Lost to tire wear": (f"{stat.breakdown_mean('wear'):.1f} s", "per race"),
                "Stops made": (f"{stat.avg_stops:.2f}", f"planned {plan.stops}"),
                "Cheap stops": (f"{cheap:.2f}", "per race"),
            }
            for label, (text, extra_value) in values.items():
                value, extra = self.table[(label, c)]
                value.configure(text=text, fg=theme.STRATEGY_TEXT[c] if label == "Fastest in"
                                else theme.TEXT)
                if isinstance(extra, MeterBar):
                    extra.set(extra_value)
                else:
                    extra.configure(text=extra_value)

    def _fill_why(self, rec: Recommendation):
        for child in self.why_frame.winfo_children():
            child.destroy()
        bg = self.why_frame.cget("bg")
        for title, text in rec.reasons:
            row = tk.Frame(self.why_frame, bg=bg)
            row.pack(fill="x", pady=theme.pad((18, 0)))
            tk.Label(row, text=title, bg=bg, fg=theme.TEXT, font=self.fonts.body_bold,
                     anchor="w").pack(anchor="w")
            body = tk.Label(row, text=text, bg=bg, fg=theme.SECONDARY, font=self.fonts.body,
                            justify="left", anchor="w")
            body.pack(anchor="w", fill="x")
            # cap the line length at about 90 characters so paragraphs stay easy to read
            limit = self.fonts.body.measure("x" * 95)
            floor, margin = theme.px(300), theme.px(10)
            body.configure(wraplength=min(limit, max(floor,
                                                     self.why_card.body.winfo_width() - margin)))
            self.why_card.body.bind("<Configure>", lambda e, b=body: b.configure(
                wraplength=min(limit, max(floor, e.width - margin))), add="+")

    @staticmethod
    def _runs_of(values, test):
        """[(first lap, last lap)] for each run of consecutive laps where test(value)."""
        runs, lap = [], 0
        while lap < len(values):
            if test(values[lap]):
                start = lap
                while lap < len(values) and test(values[lap]):
                    lap += 1
                runs.append((start + 1, lap))
            else:
                lap += 1
        return runs

    def draw_trace(self, mode):
        if not self.result:
            return
        self.trace_mode_control.set(mode)
        result = self.result
        circuit = result.circuit
        start = result.start_compound
        if mode == "Random race":
            events = generate_events(circuit, random.Random(), result.rain_chance, start)
            noise = True
        else:
            events, noise = no_events(circuit, start), False
        seed = random.random()
        races = {}
        for stat in result.stats:
            races[stat.strategy.stops] = simulate_driver(
                circuit, self.compounds, Driver("You", stat.strategy), events,
                random.Random(seed), noise=noise)
        best_stops = self.recommendation.best.strategy.stops
        ref = races[best_stops]

        def cumulative(times):
            total, out = 0.0, []
            for t in times:
                total += t
                out.append(total)
            return out

        ref_cum = cumulative(ref.lap_times)
        series, markers = [], []
        for stops, race in sorted(races.items()):
            gaps = [c - r for c, r in zip(cumulative(race.lap_times), ref_cum)]
            colour = theme.STRATEGY_COLOURS[stops]
            series.append((f"{stops}-stop", colour, gaps))
            markers.extend((colour, p.lap, gaps[p.lap - 1]) for p in race.pit_stops)

        bands = []
        if events.wet_start_laps:
            bands.append((1, events.wet_start_laps, BAND_COLOURS["WET START"], "WET START"))
        for kind in ("SC", "VSC"):
            for first, last in self._runs_of(events.neutralisation, lambda v, k=kind: v == k):
                bands.append((first, last, BAND_COLOURS[kind], kind))
        later = [w if i >= events.wet_start_laps else DRY for i, w in enumerate(events.weather)]
        for first, last in self._runs_of(later, lambda v: v != DRY):
            bands.append((first, last, BAND_COLOURS["RAIN"], "RAIN"))

        def extra_rows(lap):
            rows = [("", "Track", CONDITION_NAMES[events.weather[lap - 1]])]
            flag = events.neutralisation[lap - 1]
            if flag:
                rows.append(("", "Race", "Safety Car" if flag == "SC" else "Virtual Safety Car"))
            for stops, race in sorted(races.items()):
                for stop in race.pit_stops:
                    if stop.lap == lap:
                        rows.append((theme.STRATEGY_COLOURS[stops], f"{stops}-stop pits",
                                     f"→ {stop.new_compound}"))
            return rows

        best_name = f"{best_stops}-stop"
        if mode == "Random race":
            things = []
            if events.wet_start_laps:
                things.append("a wet start")
            if events.had_sc:
                things.append("a Safety Car")
            if events.had_vsc:
                things.append("a Virtual Safety Car")
            if events.had_rain:
                things.append("a rain shower")
            happened = ", ".join(things) if things else "no incidents"
            winner = min(races.items(), key=lambda kv: kv[1].total_time)[0]
            text = (f"One randomly generated race with {happened}. The {winner}-stop won this "
                    f"one. " + ("Shaded bands mark what happened. " if things else "")
                    + "Press “Roll another race” to see a different one.")
        else:
            text = (f"Gap to the {best_name} lap by lap in a race with no incidents. Above the "
                    f"dashed line means behind. Each strategy drops back when it pits (circles) "
                    f"and claws time back on fresher tires.")
        self.trace_sub.configure(text=text)
        self.trace_chart.set_data(series, markers, y_title=f"Seconds behind the {best_name}",
                                  zero_label=best_name, bands=bands,
                                  value_fmt=lambda v: f"{v:+.1f} s", extra_rows=extra_rows)

    def _fill_laps(self, result: SimulationResult):
        series, markers, races = [], [], {}
        events = no_events(result.circuit, result.start_compound)
        neutral = events.neutralisation  # laps behind the Safety Car are left out
        for stat in result.stats:
            race = stat.clean_race
            races[stat.strategy.stops] = race
            pit_loss = {p.lap: p.time_lost for p in race.pit_stops}
            times = [None if neutral[i] else t - pit_loss.get(i + 1, 0.0)
                     for i, t in enumerate(race.lap_times)]
            colour = theme.STRATEGY_COLOURS[stat.strategy.stops]
            series.append((stat.strategy.name, colour, times))
            markers.extend((colour, lap, times[lap - 1]) for lap in pit_loss)

        def extra_rows(lap):
            rows = [(theme.STRATEGY_COLOURS[stops], f"{stops}-stop tire",
                     race.compounds_by_lap[lap - 1]) for stops, race in sorted(races.items())]
            if neutral[lap - 1]:
                rows.insert(0, ("", "Behind the Safety Car", "slow lap"))
            return rows

        bands = []
        if events.wet_start_laps:
            bands.append((1, events.wet_start_laps, BAND_COLOURS["WET START"], "WET START"))
        for first, last in self._runs_of(events.neutralisation, lambda v: v == "SC"):
            bands.append((first, last, BAND_COLOURS["SC"], "SC"))
        self.laps_chart.set_data(series, markers, y_title="Lap time (s)", bands=bands,
                                 value_fmt=lambda v: f"{v:.2f} s", extra_rows=extra_rows)
        wet = (" The race starts wet, so the first laps are much slower until the track dries "
               "and everyone switches to slicks." if result.wet_start else "")
        self.laps_sub.configure(text=(
            "Lap times in a race with no incidents (pit-lane time and Safety Car laps removed). Each line climbs as "
            "the tires wear out and drops after a stop onto fresh tires. Fuel burning off makes "
            "the car a little faster every lap." + wet))

    def _fill_scenarios(self, result: SimulationResult):
        groups = [("All races", f"{result.runs:,} races",
                   [s.win_probability for s in result.stats])]
        counts = [("No incidents", result.runs_clean, "wins_clean"),
                  ("Safety Car", result.runs_with_sc, "wins_with_sc"),
                  ("VSC", result.runs_with_vsc, "wins_with_vsc"),
                  ("Rain shower", result.runs_with_rain, "wins_with_rain")]
        notes = []
        for label, runs, attr in counts:
            if runs:
                groups.append((label, f"{runs:,} races",
                               [getattr(s, attr) / runs for s in result.stats]))
                notes.append(f"{label} {pct(runs / result.runs)}")
        self.scenario_chart.set_data(groups, [(s.strategy.name, theme.STRATEGY_COLOURS[
            s.strategy.stops]) for s in result.stats])
        self.scenario_sub.configure(text=(
            "Win probability split by what happened in the race (" + ", ".join(notes) + " of "
            "races). Safety Cars make pit stops cheap, which usually helps strategies with "
            "more stops."))

    def _fill_rival(self, result: SimulationResult):
        series = [(s.strategy.name, theme.STRATEGY_COLOURS[s.strategy.stops],
                   result.rival_gaps(s)) for s in result.stats]
        self.rival_chart.set_data(series, x_title="Your finishing time minus the rival's")
        stops = sorted(result.rival_stop_counts.items(), key=lambda kv: -kv[1])
        mix = ", ".join(f"{k}-stop {pct(v / result.runs)}" for k, v in stops)
        pace = result.rival_pace
        pace_text = ("the same pace as you" if abs(pace) < 0.001 else
                     f"{abs(pace):.2f} s/lap {'faster' if pace < 0 else 'slower'} than you")
        beats = ", ".join(f"{s.strategy.name} {pct(s.rival_probability)}" for s in result.stats)
        self.rival_sub.configure(text=(
            f"The rival is predicted from what teams did here before: most likely a "
            f"{result.rival_strategy.describe()}. Across the simulations they ran {mix}, with "
            f"{pace_text}. Chance you finish ahead: {beats}."))


def run_app(circuits, compounds, outlines=None):
    try:  # sharper text on Windows high-DPI screens
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    root = tk.Tk()
    StrategyApp(root, circuits, compounds, outlines)
    root.mainloop()
