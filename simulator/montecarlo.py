# Pit Strategy: F1 pit stop strategy simulator (COMP9001). To run the program: python main.py (see README.txt)
"""Monte Carlo: run thousands of races to get a win probability for each strategy."""

from __future__ import annotations

import random
import statistics
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from .engine import generate_events, no_events, simulate_driver
from .models import STARTING_COMPOUNDS, WET_TIRES, Circuit, Compound, Driver, RaceResult, Strategy
from .strategy import plan_strategy

BREAKDOWN_KEYS = ("pit", "wear", "compound", "weather", "neutralised")


@dataclass
class StrategyStats:
    """Aggregated results for one strategy across every simulated race."""

    strategy: Strategy
    times: List[float] = field(default_factory=list)
    wins: int = 0
    beat_rival: int = 0
    wins_with_sc: int = 0
    wins_with_vsc: int = 0
    wins_with_rain: int = 0
    wins_clean: int = 0
    stops_made: List[int] = field(default_factory=list)
    early_stops: int = 0  # stops brought forward to use a SC/VSC
    breakdown_totals: Dict[str, float] = field(default_factory=lambda: dict.fromkeys(BREAKDOWN_KEYS, 0.0))
    clean_race: Optional[RaceResult] = None

    @property
    def runs(self) -> int:
        return len(self.times)

    @property
    def mean(self) -> float:
        return statistics.fmean(self.times)

    @property
    def stdev(self) -> float:
        return statistics.pstdev(self.times) if self.runs > 1 else 0.0

    def percentile(self, p: float) -> float:
        ordered = sorted(self.times)
        return ordered[min(len(ordered) - 1, int(p * len(ordered)))]

    def breakdown_mean(self, key: str) -> float:
        return self.breakdown_totals[key] / max(1, self.runs)

    @property
    def win_probability(self) -> float:
        return self.wins / max(1, self.runs)

    @property
    def rival_probability(self) -> float:
        return self.beat_rival / max(1, self.runs)

    @property
    def avg_stops(self) -> float:
        return statistics.fmean(self.stops_made) if self.stops_made else 0.0


@dataclass
class SimulationResult:
    circuit: Circuit
    start_compound: str
    runs: int
    rain_chance: float
    rival_pace: float
    stats: List[StrategyStats]
    rival_strategy: Strategy
    rival_stop_counts: Dict[int, int]
    rival_times: List[float]
    runs_with_sc: int
    runs_with_vsc: int
    runs_with_rain: int
    runs_clean: int
    seed: Optional[int]

    @property
    def wet_start(self) -> bool:
        return self.start_compound in WET_TIRES

    def best(self) -> StrategyStats:
        return max(self.stats, key=lambda s: (s.wins, -s.mean))

    def by_stops(self, stops: int) -> StrategyStats:
        return next(s for s in self.stats if s.strategy.stops == stops)

    def time_lost(self, stat: StrategyStats) -> List[float]:
        """Per race: seconds this strategy lost to whichever strategy was fastest that day."""
        fastest = [min(times) for times in zip(*(s.times for s in self.stats))]
        return [t - f for t, f in zip(stat.times, fastest)]

    def rival_gaps(self, stat: StrategyStats) -> List[float]:
        """Per race: seconds behind the rival (negative = finished ahead)."""
        return [t - r for t, r in zip(stat.times, self.rival_times)]


def validate_settings(start_compound: str, runs, rain_chance, rival_pace) -> tuple:
    """Check user settings, converting text to numbers. Raises ValueError with a clear message."""
    if start_compound not in STARTING_COMPOUNDS:
        raise ValueError(f"Starting tire must be one of {', '.join(STARTING_COMPOUNDS)} "
                         f"(got '{start_compound}')")
    try:
        runs = int(str(runs).replace(",", "").strip())
    except ValueError:
        raise ValueError("Number of simulations must be a whole number") from None
    if not 100 <= runs <= 20000:
        raise ValueError("Number of simulations must be between 100 and 20,000")
    try:
        rain_chance = float(rain_chance)
    except (TypeError, ValueError):
        raise ValueError("Rain chance must be a number") from None
    if rain_chance > 1:
        rain_chance /= 100  # accept 30 as well as 0.3
    if not 0 <= rain_chance <= 1:
        raise ValueError("Rain chance must be between 0% and 100%")
    try:
        rival_pace = float(rival_pace)
    except (TypeError, ValueError):
        raise ValueError("Rival pace must be a number of seconds per lap") from None
    if not -2 <= rival_pace <= 2:
        raise ValueError("Rival pace must be between -2.0 and +2.0 seconds per lap")
    return start_compound, runs, rain_chance, rival_pace


class MonteCarloSimulator:
    """Compares 1, 2 and 3-stop strategies over many randomised races."""

    def __init__(self, circuit: Circuit, compounds: Dict[str, Compound], start_compound: str,
                 runs: int = 3000, rain_chance: Optional[float] = None, rival_pace: float = 0.0,
                 seed: Optional[int] = None):
        rain = circuit.rain_chance if rain_chance is None else rain_chance
        self.start_compound, self.runs, self.rain_chance, self.rival_pace = validate_settings(
            start_compound, runs, rain, rival_pace)
        self.circuit = circuit
        self.compounds = compounds
        self.seed = seed
        self.strategies = [plan_strategy(circuit, compounds, k, start_compound)
                           for k in (1, 2, 3) if 5 * (k + 1) <= circuit.laps]
        # Rival plans are the optimal plans for each stop count. In the dry they pick their
        # own starting tire; in a wet race they start on the same wet-weather tire as you.
        rival_start = start_compound if start_compound in WET_TIRES else None
        self.rival_plans = {k: plan_strategy(circuit, compounds, k, rival_start)
                            for k in circuit.historical_strategies}
        self.rival_strategy = self.rival_plans[circuit.most_common_stops]

    def _sample_rival_stops(self, rng: random.Random) -> int:
        roll = rng.random()
        cumulative = 0.0
        for stops, share in sorted(self.circuit.historical_strategies.items()):
            cumulative += share
            if roll <= cumulative:
                return stops
        return self.circuit.most_common_stops

    def run(self, progress: Optional[Callable[[float], None]] = None,
            cancelled: Optional[Callable[[], bool]] = None) -> SimulationResult:
        rng = random.Random(self.seed)
        stats = [StrategyStats(s) for s in self.strategies]
        drivers = [Driver("You", s) for s in self.strategies]
        rival_times: List[float] = []
        rival_stop_counts: Dict[int, int] = {}
        counters = {"sc": 0, "vsc": 0, "rain": 0, "clean": 0}

        for stat, driver in zip(stats, drivers):
            stat.clean_race = simulate_driver(self.circuit, self.compounds, driver,
                                              no_events(self.circuit, self.start_compound), rng,
                                              noise=False)

        report_every = max(1, self.runs // 100)
        for run in range(self.runs):
            if cancelled and cancelled():
                break
            events = generate_events(self.circuit, rng, self.rain_chance, self.start_compound)
            noise_seed = rng.random()  # same lap-time noise for every strategy (fair test)
            counters["sc"] += events.had_sc
            counters["vsc"] += events.had_vsc
            counters["rain"] += events.had_rain
            clean = not (events.had_sc or events.had_vsc or events.had_rain)
            counters["clean"] += clean

            rival_stops = self._sample_rival_stops(rng)
            rival_stop_counts[rival_stops] = rival_stop_counts.get(rival_stops, 0) + 1
            rival = Driver("Rival", self.rival_plans[rival_stops], pace_offset=self.rival_pace)
            rival_time = simulate_driver(self.circuit, self.compounds, rival, events,
                                         random.Random(rng.random())).total_time
            rival_times.append(rival_time)

            results = []
            for stat, driver in zip(stats, drivers):
                res = simulate_driver(self.circuit, self.compounds, driver, events,
                                      random.Random(noise_seed))
                results.append(res)
                stat.times.append(res.total_time)
                stat.stops_made.append(res.stops_made)
                stat.early_stops += sum(1 for p in res.pit_stops if p.reason in ("SC", "VSC"))
                stat.beat_rival += res.total_time < rival_time
                for key in BREAKDOWN_KEYS:
                    stat.breakdown_totals[key] += res.breakdown[key]

            winner = stats[min(range(len(results)), key=lambda i: results[i].total_time)]
            winner.wins += 1
            winner.wins_with_sc += events.had_sc
            winner.wins_with_vsc += events.had_vsc
            winner.wins_with_rain += events.had_rain
            winner.wins_clean += clean

            if progress and (run + 1) % report_every == 0:
                progress((run + 1) / self.runs)

        return SimulationResult(
            circuit=self.circuit, start_compound=self.start_compound,
            runs=len(stats[0].times), rain_chance=self.rain_chance, rival_pace=self.rival_pace,
            stats=stats, rival_strategy=self.rival_strategy, rival_stop_counts=rival_stop_counts,
            rival_times=rival_times, runs_with_sc=counters["sc"], runs_with_vsc=counters["vsc"],
            runs_with_rain=counters["rain"], runs_clean=counters["clean"], seed=self.seed)
