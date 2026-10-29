# Pit Strategy: F1 pit stop strategy simulator (COMP9001). To run the program: python main.py (see README.txt)
"""Layout check: opens the app, runs a simulation, visits every tab and reports any text
that doesn't fit in its box.

    python tools/check_layout.py            # at this screen's own display scaling
    python tools/check_layout.py 150        # pretend Windows display scaling is 150%

It needs a screen (it opens a window for a few seconds) and closes by itself.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import tkinter as tk  # noqa: E402

from gui import theme  # noqa: E402
from gui.app import TABS, StrategyApp  # noqa: E402
from gui.widgets import PillButton, SegmentedControl  # noqa: E402
from simulator.data_loader import load_data, load_outlines  # noqa: E402


def find_problems(widget, where, problems):
    for child in widget.winfo_children():
        try:
            if not child.winfo_ismapped():
                continue
        except tk.TclError:
            continue
        if isinstance(child, tk.Label) and child.cget("text").strip():
            if (child.winfo_width() + 1 < child.winfo_reqwidth()
                    or child.winfo_height() + 1 < child.winfo_reqheight()):
                problems.add(f"{where}: text {child.cget('text')[:40]!r} is cut off")
        if isinstance(child, SegmentedControl):
            if sum(child._needs(child.font)) > child.winfo_width() + 1:
                problems.add(f"{where}: selector {child.options} is squashed")
        if isinstance(child, PillButton):
            if child.fonts.body_bold.measure(child.text) > child.winfo_width():
                problems.add(f"{where}: button {child.text!r} is too narrow")
        find_problems(child, where, problems)


def main():
    root = tk.Tk()
    if len(sys.argv) > 1:
        percent = float(sys.argv[1].rstrip("%"))
        root.tk.call("tk", "scaling", percent / 100 * 96 / 72)
    circuits, compounds = load_data()
    app = StrategyApp(root, circuits, compounds, load_outlines())
    problems = set()

    def check(where):
        root.update()
        find_problems(root, where, problems)

    def finish():
        print(f"Display scaling {theme.SCALE * 100:.0f}%, window "
              f"{root.winfo_width()}x{root.winfo_height()}")
        print("\n".join(sorted(problems)) if problems else "All text fits.")
        root.destroy()

    def visit(i):
        if i >= len(TABS):
            finish()
            return
        app.tab_control.set(TABS[i], notify=True)
        root.after(300, lambda: (check(TABS[i]), visit(i + 1)))

    def wait_for_results():
        if (app.worker and app.worker.is_alive()) or app.result is None:
            root.after(200, wait_for_results)
        else:
            visit(0)

    def start():
        check("Circuit page")
        app.runs_var.set("1000")
        app.run_simulation()
        root.after(200, wait_for_results)

    root.after(800, start)
    root.mainloop()
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
