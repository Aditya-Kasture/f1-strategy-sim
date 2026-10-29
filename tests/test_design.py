# Pit Strategy: F1 pit stop strategy simulator (COMP9001). To run the program: python main.py (see README.txt)
"""Checks that the colour tokens stay readable (WCAG AA: 4.5:1 for normal text)."""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gui import theme  # noqa: E402

# The lightest and darkest surfaces text sits on: a glass panel over the strongest backdrop
# colour, a panel over the plain backdrop, and tooltips.
SURFACES = [theme.blend(c, "#FFFFFF", 0.72) for _, _, _, c in theme.MAIN_BLOBS + theme.SIDE_BLOBS]
SURFACES += [theme.blend(theme.BASE, "#FFFFFF", 0.72), theme.FLOAT, "#FFFFFF", theme.BASE]
AA = 4.5


class ContrastTests(unittest.TestCase):
    def test_text_colours_pass_aa_on_every_surface(self):
        for name in ("TEXT", "SECONDARY", "TERTIARY", "ACCENT", "GREEN", "RED"):
            colour = getattr(theme, name)
            for surface in SURFACES:
                ratio = theme.contrast(colour, surface)
                self.assertGreaterEqual(ratio, AA, f"{name} on {surface}: {ratio:.2f}")

    def test_badges_pass_aa(self):
        self.assertGreaterEqual(theme.contrast(theme.GREEN, theme.GREEN_SOFT), AA)
        self.assertGreaterEqual(theme.contrast(theme.RED, theme.RED_SOFT), AA)
        self.assertGreaterEqual(theme.contrast(theme.ACCENT, theme.ACCENT_SOFT), AA)

    def test_strategy_text_colours_pass_aa(self):
        for colour in theme.STRATEGY_TEXT.values():
            for surface in SURFACES:
                self.assertGreaterEqual(theme.contrast(colour, surface), AA)

    def test_recommended_column_passes_aa(self):
        for colour in [theme.TEXT, theme.SECONDARY] + list(theme.STRATEGY_TEXT.values()):
            self.assertGreaterEqual(theme.contrast(colour, theme.ACCENT_SOFT), AA, colour)

    def test_readable_darkens_light_colours(self):
        for colour in theme.STRATEGY_COLOURS.values():
            self.assertGreaterEqual(theme.contrast(theme.readable(colour, "#FFFFFF"), "#FFFFFF"), AA)

    def test_disabled_button_label_is_readable(self):
        for surface in SURFACES:
            fill = theme.blend(surface, theme.INK, 0.12)
            self.assertGreaterEqual(theme.contrast(theme.SECONDARY, fill), AA)

    def test_button_label_passes_aa(self):
        self.assertGreaterEqual(theme.contrast("#FFFFFF", theme.ACCENT), AA)
        self.assertGreaterEqual(theme.contrast("#FFFFFF", theme.ACCENT_HOVER), AA)

    def test_tire_labels_are_readable(self):
        path = os.path.join(os.path.dirname(__file__), "..", "data", "circuits.json")
        with open(path) as handle:
            compounds = json.load(handle)["compounds"]
        for name, data in compounds.items():
            fill = data["colour"]
            self.assertGreaterEqual(theme.contrast(theme.text_on(fill), fill), AA, name)


if __name__ == "__main__":
    unittest.main()
