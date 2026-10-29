# Pit Strategy: F1 pit stop strategy simulator (COMP9001). To run the program: python main.py (see README.txt)
"""Tests for the simulation logic. Run with:  python -m unittest discover tests"""

import json
import os
import random
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from simulator.data_loader import DataError, find_circuit, load_data, load_outlines  # noqa: E402
from simulator.engine import (generate_events, no_events, pit_time_loss,  # noqa: E402
                              simulate_driver)
from simulator.explain import build_recommendation, format_race_time  # noqa: E402
from simulator.models import DAMP, DRY, WET, Driver, RaceEvents, Tire  # noqa: E402
from simulator.montecarlo import MonteCarloSimulator, validate_settings  # noqa: E402
from simulator.strategy import plan_strategy  # noqa: E402

CIRCUITS, COMPOUNDS = load_data()


def circuit(name="Bahrain"):
    return find_circuit(CIRCUITS, name)


class DataLoadingTests(unittest.TestCase):
    def test_default_file_loads(self):
        self.assertEqual(len(CIRCUITS), 24)  # the full 2026 calendar
        self.assertEqual([c.round for c in CIRCUITS], list(range(1, 25)))
        self.assertIn("Wet", COMPOUNDS)

    def test_every_circuit_has_a_track_map(self):
        outlines = load_outlines()
        for c in CIRCUITS:
            self.assertGreater(len(outlines.get(c.name, [])), 50, c.name)

    def test_missing_outline_file_gives_no_maps(self):
        self.assertEqual(load_outlines("does/not/exist.json"), {})

    def test_history_is_normalised(self):
        for c in CIRCUITS:
            self.assertAlmostEqual(sum(c.historical_strategies.values()), 1.0)

    def _write(self, content):
        handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        handle.write(content)
        handle.close()
        self.addCleanup(os.remove, handle.name)
        return handle.name

    def test_missing_file(self):
        with self.assertRaises(DataError):
            load_data("does/not/exist.json")

    def test_invalid_json(self):
        with self.assertRaises(DataError):
            load_data(self._write("{ not json"))

    def test_missing_field(self):
        with open(os.path.join(os.path.dirname(__file__), "..", "data", "circuits.json")) as f:
            data = json.load(f)
        del data["circuits"][0]["pit_loss"]
        with self.assertRaises(DataError):
            load_data(self._write(json.dumps(data)))

    def test_wrong_type(self):
        with open(os.path.join(os.path.dirname(__file__), "..", "data", "circuits.json")) as f:
            data = json.load(f)
        data["circuits"][0]["laps"] = "lots"
        with self.assertRaises(DataError):
            load_data(self._write(json.dumps(data)))

    def test_find_circuit(self):
        self.assertEqual(find_circuit(CIRCUITS, "monza").name, "Italy")
        with self.assertRaises(ValueError):
            find_circuit(CIRCUITS, "Narnia")


class TireTests(unittest.TestCase):
    def test_wear_increases_with_age(self):
        tire = Tire(COMPOUNDS["Soft"], circuit())
        losses = []
        for _ in range(30):
            losses.append(tire.wear_loss())
            tire.run_lap()
        self.assertEqual(losses, sorted(losses))
        self.assertEqual(losses[0], 0.0)

    def test_softs_wear_faster_than_hards(self):
        soft, hard = Tire(COMPOUNDS["Soft"], circuit(), 15), Tire(COMPOUNDS["Hard"], circuit(), 15)
        self.assertGreater(soft.wear_loss(), hard.wear_loss())

    def test_less_wear_behind_safety_car(self):
        tire = Tire(COMPOUNDS["Medium"], circuit())
        tire.run_lap(neutralised=True)
        self.assertLess(tire.age, 1.0)

    def test_slicks_are_slow_in_the_wet(self):
        self.assertGreater(Tire(COMPOUNDS["Medium"], circuit()).weather_penalty(DAMP), 0)
        self.assertLess(Tire(COMPOUNDS["Intermediate"], circuit()).weather_penalty(DAMP), 0)


class StrategyTests(unittest.TestCase):
    def test_plans_are_legal(self):
        for c in CIRCUITS:
            for stops in (1, 2, 3):
                for start in ("Soft", "Medium", "Hard"):
                    plan = plan_strategy(c, COMPOUNDS, stops, start)
                    self.assertEqual(len(plan.pit_laps), stops)
                    self.assertEqual(plan.compounds[0].name, start)
                    self.assertGreaterEqual(len({x.name for x in plan.compounds}), 2)
                    self.assertEqual(sum(s.length for s in plan.stints), c.laps)
                    self.assertTrue(all(s.length >= 5 for s in plan.stints))

    def test_high_degradation_needs_more_stops_than_low(self):
        bahrain = [plan_strategy(circuit("Bahrain"), COMPOUNDS, k, "Medium") for k in (1, 2)]
        monza = [plan_strategy(circuit("Italy"), COMPOUNDS, k, "Medium") for k in (1, 2)]
        self.assertLess(bahrain[1].expected_time, bahrain[0].expected_time)
        self.assertLess(monza[0].expected_time, monza[1].expected_time)

    def test_bad_start_compound(self):
        with self.assertRaises(ValueError):
            plan_strategy(circuit(), COMPOUNDS, 1, "Ultrasoft")


class EngineTests(unittest.TestCase):
    def test_vsc_stop_saves_five_to_six_seconds(self):
        rng = random.Random(1)
        c = circuit()
        for _ in range(50):
            saving = c.pit_loss - pit_time_loss(c, "VSC", rng, noise=False)
            self.assertAlmostEqual(saving, 5.5)
        green = pit_time_loss(c, None, rng, noise=False)
        vsc = pit_time_loss(c, "VSC", rng, noise=False)
        sc = pit_time_loss(c, "SC", rng, noise=False)
        self.assertLess(sc, vsc)
        self.assertLess(vsc, green)

    def test_clean_race_follows_plan(self):
        c = circuit()
        plan = plan_strategy(c, COMPOUNDS, 2, "Medium")
        result = simulate_driver(c, COMPOUNDS, Driver("You", plan), no_events(c),
                                 random.Random(0), noise=False)
        self.assertEqual([p.lap for p in result.pit_stops], plan.pit_laps)
        self.assertEqual(len(result.lap_times), c.laps)
        self.assertAlmostEqual(result.total_time, plan.expected_time, places=6)

    def test_pits_early_under_safety_car(self):
        c = circuit()
        plan = plan_strategy(c, COMPOUNDS, 1, "Medium")
        flags = [None] * c.laps
        sc_lap = plan.pit_laps[0] - 3
        for lap in range(sc_lap, sc_lap + 3):
            flags[lap - 1] = "SC"
        events = RaceEvents(neutralisation=flags, weather=[DRY] * c.laps)
        result = simulate_driver(c, COMPOUNDS, Driver("You", plan), events, random.Random(0),
                                 noise=False)
        self.assertEqual(result.pit_stops[0].lap, sc_lap)
        self.assertEqual(result.pit_stops[0].reason, "SC")

    def test_switches_to_intermediates_in_rain(self):
        c = circuit("Belgium")
        plan = plan_strategy(c, COMPOUNDS, 1, "Medium")
        weather = [DRY] * c.laps
        for lap in range(10, 20):
            weather[lap] = DAMP
        events = RaceEvents(neutralisation=[None] * c.laps, weather=weather)
        result = simulate_driver(c, COMPOUNDS, Driver("You", plan), events, random.Random(0),
                                 noise=False)
        self.assertIn("Intermediate", [p.new_compound for p in result.pit_stops])
        self.assertEqual(result.compounds_by_lap[-1] in ("Soft", "Medium", "Hard"), True)

    def test_events_are_reproducible(self):
        a = generate_events(circuit(), random.Random(42), 0.5)
        b = generate_events(circuit(), random.Random(42), 0.5)
        self.assertEqual(a, b)

    def test_no_rain_when_chance_is_zero(self):
        rng = random.Random(3)
        for _ in range(200):
            self.assertFalse(generate_events(circuit(), rng, 0.0).had_rain)


class WetStartTests(unittest.TestCase):
    def test_wet_start_plans(self):
        for start in ("Intermediate", "Wet"):
            for stops in (1, 2, 3):
                plan = plan_strategy(circuit("Great Britain"), COMPOUNDS, stops, start)
                self.assertEqual(plan.compounds[0].name, start)
                self.assertTrue(all(c.is_slick for c in plan.compounds[1:]))
                self.assertEqual(len(plan.pit_laps), stops)
                self.assertEqual(sum(s.length for s in plan.stints), plan.total_laps)

    def test_intermediate_start_switches_to_slicks_when_dry(self):
        c = circuit("Great Britain")
        plan = plan_strategy(c, COMPOUNDS, 1, "Intermediate")
        events = no_events(c, "Intermediate")
        self.assertEqual(events.weather[0], DAMP)
        self.assertFalse(events.had_rain)  # the wet start itself is not a "shower"
        result = simulate_driver(c, COMPOUNDS, Driver("You", plan), events, random.Random(0),
                                 noise=False)
        self.assertEqual(result.pit_stops[0].reason, "drying")
        self.assertEqual(result.pit_stops[0].lap, events.wet_start_laps + 1)
        self.assertEqual(result.pit_stops[0].lap, plan.pit_laps[0])
        self.assertTrue(result.compounds_by_lap[-1] in ("Soft", "Medium", "Hard"))

    def test_full_wet_start_behind_safety_car(self):
        c = circuit("Belgium")
        events = no_events(c, "Wet")
        self.assertEqual(events.neutralisation[:3], ["SC"] * 3)
        self.assertFalse(events.had_sc)  # the start SC is not counted as an incident
        plan = plan_strategy(c, COMPOUNDS, 2, "Wet")
        result = simulate_driver(c, COMPOUNDS, Driver("You", plan), events, random.Random(0),
                                 noise=False)
        new = [p.new_compound for p in result.pit_stops]
        self.assertEqual(new[0], "Intermediate")  # rain eases: Wets -> Inters -> slicks

    def test_wet_tires_beat_slicks_in_rain(self):
        c = circuit()
        def lap_loss(name, state):
            tire = Tire(COMPOUNDS[name], c)
            return COMPOUNDS[name].pace_offset + tire.weather_penalty(state)
        self.assertLess(lap_loss("Intermediate", DAMP), lap_loss("Medium", DAMP))
        self.assertLess(lap_loss("Wet", WET), lap_loss("Intermediate", WET))
        self.assertLess(lap_loss("Intermediate", DAMP), lap_loss("Wet", DAMP))
        self.assertLess(lap_loss("Medium", DRY), lap_loss("Intermediate", DRY))

    def test_wet_monte_carlo_runs(self):
        result = MonteCarloSimulator(circuit("Canada"), COMPOUNDS, "Wet", runs=200, seed=2).run()
        self.assertAlmostEqual(sum(s.win_probability for s in result.stats), 1.0)
        self.assertEqual(result.rival_strategy.compounds[0].name, "Wet")
        self.assertIn("Wet start", [t for t, _ in build_recommendation(result).reasons])


class MonteCarloTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = MonteCarloSimulator(circuit(), COMPOUNDS, "Medium", runs=400, seed=7).run()

    def test_win_probabilities_sum_to_one(self):
        self.assertAlmostEqual(sum(s.win_probability for s in self.result.stats), 1.0)
        self.assertEqual(self.result.runs, 400)

    def test_same_seed_same_answer(self):
        again = MonteCarloSimulator(circuit(), COMPOUNDS, "Medium", runs=400, seed=7).run()
        self.assertEqual([s.times for s in again.stats], [s.times for s in self.result.stats])

    def test_bahrain_prefers_two_stops(self):
        self.assertEqual(self.result.best().strategy.stops, 2)

    def test_recommendation_explains_alternatives(self):
        rec = build_recommendation(self.result)
        self.assertEqual(len(rec.comparisons), 2)
        for comparison in rec.comparisons:
            self.assertGreaterEqual(comparison.mean_gap, -1.0)
            self.assertIn(comparison.other.strategy.name, comparison.text)
        titles = [title for title, _ in rec.reasons]
        self.assertIn("What you gain", titles)
        self.assertIn("The rival", titles)

    def test_progress_callback(self):
        seen = []
        MonteCarloSimulator(circuit(), COMPOUNDS, "Soft", runs=200, seed=1).run(seen.append)
        self.assertAlmostEqual(seen[-1], 1.0)

    def test_settings_validation(self):
        self.assertEqual(validate_settings("Hard", "2,000", 30, "-0.2"), ("Hard", 2000, 0.3, -0.2))
        for bad in [("Ultrasoft", 1000, 0, 0), ("Soft", "lots", 0, 0), ("Soft", 5, 0, 0),
                    ("Soft", 1000, 150, 0), ("Soft", 1000, 0, "fast"), ("Soft", 1000, 0, 9)]:
            with self.assertRaises(ValueError):
                validate_settings(*bad)


class FormattingTests(unittest.TestCase):
    def test_format_race_time(self):
        self.assertEqual(format_race_time(5716.04), "1:35:16.0")


if __name__ == "__main__":
    unittest.main()
