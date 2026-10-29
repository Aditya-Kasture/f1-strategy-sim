# Pit Strategy: F1 pit stop strategy simulator (COMP9001). To run the program: python main.py (see README.txt)
"""Strategy planner: finds the best compounds and pit laps for a given number of stops."""

from __future__ import annotations

import dataclasses
import itertools
import random
from typing import Dict, List, Optional

from .models import SLICKS, STARTING_COMPOUNDS, WET_TIRES, Circuit, Compound, Driver, Strategy, Tire

MIN_STINT = 5        # nobody pits for slicks again within 5 laps
FUEL_EFFECT = 0.055  # seconds per lap of fuel still on board


def fuel_penalty(circuit: Circuit, lap: int) -> float:
    """A heavier car is slower. lap is 1-based; the car burns fuel every lap."""
    return FUEL_EFFECT * (circuit.laps - lap)


def expected_drying_lap(circuit: Circuit, start_compound: str) -> int:
    """Forecast lap when a wet track becomes dry enough for slicks."""
    share = 0.32 if start_compound == "Wet" else 0.22
    return max(6, round(circuit.laps * share))


def stint_cost_table(circuit: Circuit, compound: Compound) -> List[float]:
    """cost[n] = time lost to compound pace + wear over a stint of n laps on fresh tires."""
    tire = Tire(compound, circuit)
    costs = [0.0]
    running = 0.0
    for _ in range(circuit.laps):
        running += compound.pace_offset + tire.wear_loss()
        costs.append(running)
        tire.run_lap()
    return costs


def clean_race_time(circuit: Circuit, total_stint_cost: float, stops: int) -> float:
    base = circuit.laps * circuit.base_lap_time
    fuel = sum(fuel_penalty(circuit, lap) for lap in range(1, circuit.laps + 1))
    return base + fuel + total_stint_cost + stops * circuit.pit_loss


def _best_split(circuit: Circuit, sequence, tables) -> Optional[tuple]:
    """Dynamic programming: best stint lengths for a fixed compound sequence."""
    laps = circuit.laps
    inf = float("inf")
    # best[i][end] = cheapest cost of stints 0..i where stint i finishes on lap `end`
    best = [[inf] * (laps + 1) for _ in sequence]
    came_from = [[0] * (laps + 1) for _ in sequence]
    first = tables[sequence[0].name]
    for end in range(MIN_STINT, laps + 1):
        best[0][end] = first[end]
    for i in range(1, len(sequence)):
        table = tables[sequence[i].name]
        for end in range(MIN_STINT * (i + 1), laps + 1):
            for prev in range(MIN_STINT * i, end - MIN_STINT + 1):
                if best[i - 1][prev] == inf:
                    continue
                cost = best[i - 1][prev] + table[end - prev]
                if cost < best[i][end]:
                    best[i][end] = cost
                    came_from[i][end] = prev
    total = best[-1][laps]
    if total == inf:
        return None
    pit_laps = []
    end = laps
    for i in range(len(sequence) - 1, 0, -1):
        end = came_from[i][end]
        pit_laps.append(end)
    return total, sorted(pit_laps)


def plan_strategy(circuit: Circuit, compounds: Dict[str, Compound], stops: int,
                  start_compound: Optional[str] = None) -> Strategy:
    """Return the fastest clean-race plan with exactly `stops` pit stops.

    Dry races follow the F1 rule that at least two different dry compounds must be used.
    If start_compound is None the planner also chooses the starting tire. Starting on
    Intermediates or Wets means a wet start: the first stop is the switch to slicks.
    """
    if stops < 1:
        raise ValueError("A race needs at least one pit stop")
    if MIN_STINT * (stops + 1) > circuit.laps:
        raise ValueError(f"{circuit.name} is too short for a {stops}-stop strategy")
    if start_compound is not None and start_compound not in STARTING_COMPOUNDS:
        raise ValueError(f"Starting tire must be one of {', '.join(STARTING_COMPOUNDS)}")
    if start_compound in WET_TIRES:
        return _plan_wet_start(circuit, compounds, stops, start_compound)

    slicks = [compounds[name] for name in SLICKS]
    tables = {c.name: stint_cost_table(circuit, c) for c in slicks}
    best = None
    for sequence in itertools.product(slicks, repeat=stops + 1):
        if start_compound and sequence[0].name != start_compound:
            continue
        if len({c.name for c in sequence}) < 2:
            continue  # two-compound rule
        found = _best_split(circuit, sequence, tables)
        if found and (best is None or found[0] < best[0]):
            best = (found[0], list(sequence), found[1])

    cost, sequence, pit_laps = best
    return Strategy(stops=stops, compounds=sequence, pit_laps=pit_laps, total_laps=circuit.laps,
                    expected_time=clean_race_time(circuit, cost, stops))


def _plan_wet_start(circuit: Circuit, compounds: Dict[str, Compound], stops: int,
                    start_compound: str) -> Strategy:
    """Start on wet-weather tires, switch to slicks when it dries, then plan the dry part.

    The two-compound rule doesn't apply in a wet race, so any slicks can be used.
    """
    from .engine import no_events, simulate_driver  # imported here to avoid a cycle

    # Teams see the first dry lap, then pit at the end of it
    switch_lap = expected_drying_lap(circuit, start_compound) + 1
    dry_part = dataclasses.replace(circuit, laps=circuit.laps - switch_lap)
    if MIN_STINT * stops > dry_part.laps:
        raise ValueError(f"{circuit.name} is too short for a {stops}-stop wet race")
    slicks = [compounds[name] for name in SLICKS]
    tables = {c.name: stint_cost_table(dry_part, c) for c in slicks}
    best = None
    for sequence in itertools.product(slicks, repeat=stops):
        found = _best_split(dry_part, sequence, tables)
        if found and (best is None or found[0] < best[0]):
            best = (found[0], list(sequence), found[1])

    _, sequence, dry_pits = best
    strategy = Strategy(stops=stops, compounds=[compounds[start_compound]] + sequence,
                        pit_laps=[switch_lap] + [switch_lap + p for p in dry_pits],
                        total_laps=circuit.laps)
    clean = simulate_driver(circuit, compounds, Driver("plan", strategy),
                            no_events(circuit, start_compound), random.Random(0), noise=False)
    strategy.expected_time = clean.total_time
    return strategy


def predict_rival_strategy(circuit: Circuit, compounds: Dict[str, Compound],
                           start_compound: Optional[str] = None) -> Strategy:
    """The rival's most likely plan: the stop count most of the field used here historically.

    In a wet race the rival has to start on the same wet-weather tire as everyone else.
    """
    start = start_compound if start_compound in WET_TIRES else None
    return plan_strategy(circuit, compounds, circuit.most_common_stops, start)
