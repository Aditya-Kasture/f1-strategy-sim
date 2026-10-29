# =====================================================================================
# RUN THIS FILE.
#   python main.py          opens the app (a tkinter window, so run it outside Ed)
#   python main.py --cli    text-only version, works in Ed's terminal
# Python 3.8 or newer, standard library only. Keep the data/ folder next to this file.
# Full instructions: README.txt
# =====================================================================================
"""F1 Pit Stop Strategy Simulator.

Run `python main.py` for the app, or `python main.py --cli` for a text-only version.
"""

from __future__ import annotations

import argparse
import sys

from simulator.data_loader import (DEFAULT_DATA_FILE, DataError, find_circuit, load_data,
                                   load_outlines)
from simulator.explain import build_recommendation, format_race_time, pct
from simulator.models import STARTING_COMPOUNDS
from simulator.montecarlo import MonteCarloSimulator


def ask(prompt: str, convert, default=None):
    """Keep asking until convert(answer) works. Empty input uses the default."""
    while True:
        try:
            answer = input(prompt).strip()
        except EOFError:
            print()
            sys.exit(0)
        if not answer and default is not None:
            return default
        try:
            return convert(answer)
        except ValueError as exc:
            print(f"  ✗ {exc}")


def parse_compound(text: str) -> str:
    shortcuts = {"s": "Soft", "m": "Medium", "h": "Hard", "i": "Intermediate",
                 "inter": "Intermediate", "inters": "Intermediate", "w": "Wet"}
    text = text.lower()
    for name in STARTING_COMPOUNDS:
        if text == name.lower():
            return name
    if text in shortcuts:
        return shortcuts[text]
    raise ValueError("Please type Soft, Medium, Hard, Intermediate or Wet (or S, M, H, I, W)")


def parse_percent(text: str) -> float:
    try:
        value = float(text.rstrip("%"))
    except ValueError:
        raise ValueError("Please enter a number between 0 and 100") from None
    if not 0 <= value <= 100:
        raise ValueError("Please enter a number between 0 and 100")
    return value / 100


def parse_runs(text: str) -> int:
    try:
        value = int(text.replace(",", ""))
    except ValueError:
        raise ValueError("Please enter a whole number, e.g. 3000") from None
    if not 100 <= value <= 20000:
        raise ValueError("Please choose between 100 and 20,000 races")
    return value


def parse_pace(text: str) -> float:
    try:
        value = float(text)
    except ValueError:
        raise ValueError("Please enter seconds per lap, e.g. -0.2 or 0.1") from None
    if not -2 <= value <= 2:
        raise ValueError("Please keep the rival pace between -2.0 and +2.0 s/lap")
    return value


def run_cli(circuits, compounds) -> None:
    print("\nF1 PIT STOP STRATEGY SIMULATOR\n" + "=" * 30)
    for i, c in enumerate(circuits, 1):
        print(f"  {i:2d}. {c.name:<14} {c.laps} laps, pit loss {c.pit_loss:.1f} s")

    def parse_circuit(text):
        if text.isdigit():
            index = int(text)
            if 1 <= index <= len(circuits):
                return circuits[index - 1]
            raise ValueError(f"Pick a number from 1 to {len(circuits)}")
        return find_circuit(circuits, text)

    print()
    circuit = ask("Circuit (number or name): ", parse_circuit)
    compound = ask("Starting tire [Soft/Medium/Hard/Intermediate/Wet] (Medium): ",
                   parse_compound, "Medium")
    rain = ask(f"Rain chance % ({circuit.rain_chance * 100:.0f}): ", parse_percent,
               circuit.rain_chance)
    rival = ask("Rival pace in s/lap, negative = faster (0): ", parse_pace, 0.0)
    runs = ask("Number of simulated races (3000): ", parse_runs, 3000)

    try:
        sim = MonteCarloSimulator(circuit, compounds, compound, runs, rain, rival)
    except ValueError as exc:
        print(f"\n✗ {exc}")
        return

    def progress(value):
        bar = "█" * int(value * 30)
        print(f"\r  Simulating [{bar:<30}] {value * 100:3.0f}%", end="", flush=True)

    result = sim.run(progress=progress)
    rec = build_recommendation(result)
    print("\n")
    print(f"{'Strategy':<10}{'Plan':<34}{'Win %':>7}{'Avg time':>13}{'Gap':>8}{'Beat rival':>12}")
    best_mean = min(s.mean for s in result.stats)
    for s in result.stats:
        plan = f"{s.strategy.short_sequence}  pit {', '.join(map(str, s.strategy.pit_laps))}"
        print(f"{s.strategy.name:<10}{plan:<34}{pct(s.win_probability):>7}"
              f"{format_race_time(s.mean):>13}{s.mean - best_mean:>+7.1f}s"
              f"{pct(s.rival_probability):>12}")
    print("\n" + "=" * 84)
    print(rec.as_text())


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="F1 pit stop strategy simulator")
    parser.add_argument("--cli", action="store_true", help="use the text version instead of the app")
    parser.add_argument("--data", default=DEFAULT_DATA_FILE, help="path to a circuits JSON file")
    args = parser.parse_args(argv)

    try:
        circuits, compounds = load_data(args.data)
    except DataError as exc:
        print(f"Could not load circuit data: {exc}", file=sys.stderr)
        return 1

    if not args.cli:
        try:
            from gui.app import run_app
        except ImportError as exc:  # e.g. Python installed without tkinter
            print(f"The window could not open ({exc}). Starting the text version instead.\n")
        else:
            from tkinter import TclError
            try:
                run_app(circuits, compounds, load_outlines())
                return 0
            except TclError as exc:  # no screen to draw on, e.g. Ed or a remote terminal
                print(f"The window could not open ({exc}). Starting the text version instead.\n")
    try:
        run_cli(circuits, compounds)
    except KeyboardInterrupt:
        print("\nBye!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
