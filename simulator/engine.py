# Pit Strategy: F1 pit stop strategy simulator (COMP9001). To run the program: python main.py (see README.txt)
"""Lap-by-lap race engine: random race events, pit decisions and lap times."""

from __future__ import annotations

import random
from typing import Dict, List, Optional

from .models import (DAMP, DRY, WET, WET_TIRES, Circuit, Compound, Driver, PitStop,
                     RaceEvents, RaceResult, Tire)
from .strategy import MIN_STINT, expected_drying_lap, fuel_penalty

SC_LAP_FACTOR = 1.40       # laps behind the Safety Car are ~40% slower
VSC_LAP_FACTOR = 1.30      # Virtual Safety Car laps are ~30% slower
VSC_PIT_SAVING = (5.0, 6.0)  # a VSC pit stop saves 5-6 s over a green-flag stop
SC_PIT_FRACTION = 0.50     # under a full Safety Car a stop costs about half the usual time
SC_PIT_WINDOW = 8          # pit early under SC if the planned stop is this close
VSC_PIT_WINDOW = 5
WEATHER_SC_BOOST = 3.0     # crashes are three times as likely on a wet track
SLOW_STOP_CHANCE = 0.03    # sometimes the wheel gun jams
WET_START_SC_LAPS = 3      # a full-wet race starts behind the Safety Car
TIRE_CHANGE_DELAY = 2      # laps of Inter-vs-Wet conditions before a team swaps between them


def _wet_start(circuit: Circuit, start_compound: Optional[str], drying_lap: int,
               weather: List[str], neutralisation: List[Optional[str]]) -> int:
    """Fill in the opening laps of a wet race. Returns how many laps start behind the SC."""
    if start_compound == "Wet":
        heavy_laps = max(1, round(drying_lap * 0.6))  # heavy rain first, then it eases
        for lap in range(drying_lap):
            weather[lap] = WET if lap < heavy_laps else DAMP
        sc_laps = min(WET_START_SC_LAPS, drying_lap)
        for lap in range(sc_laps):
            neutralisation[lap] = "SC"
        return sc_laps
    for lap in range(drying_lap):
        weather[lap] = DAMP
    return 0


def generate_events(circuit: Circuit, rng: random.Random, rain_chance: Optional[float] = None,
                    start_compound: Optional[str] = None) -> RaceEvents:
    """Roll the dice for one race: a wet start, rain showers, Safety Cars and VSCs.

    Starting on Intermediates means the track starts damp; starting on Wets means heavy
    rain. Either way the track dries at a random lap around the forecast.
    """
    laps = circuit.laps
    rain_chance = circuit.rain_chance if rain_chance is None else rain_chance
    weather = [DRY] * laps
    neutralisation: List[Optional[str]] = [None] * laps

    wet_start_laps = start_sc_laps = 0
    if start_compound in WET_TIRES:
        mean = expected_drying_lap(circuit, start_compound)
        wet_start_laps = int(round(rng.gauss(mean, laps * 0.07)))
        wet_start_laps = max(6, min(int(laps * 0.7), wet_start_laps))
        start_sc_laps = _wet_start(circuit, start_compound, wet_start_laps, weather,
                                   neutralisation)

    first_shower_lap = max(int(laps * 0.15), wet_start_laps + 5)
    if rng.random() < rain_chance and first_shower_lap < int(laps * 0.85):
        start = rng.randint(first_shower_lap, int(laps * 0.85))
        duration = rng.randint(6, 18)
        heavy = rng.random() < 0.4
        for lap in range(start, min(laps, start + duration)):
            first_lap = lap == start
            weather[lap] = WET if heavy and not first_lap else DAMP
        for lap in range(start + duration, min(laps, start + duration + 2)):
            weather[lap] = DAMP  # the track takes a couple of laps to dry

    lap = 0
    while lap < laps - 2:  # nothing new is deployed in the final two laps
        if neutralisation[lap]:
            lap += 1
            continue
        boost = WEATHER_SC_BOOST if weather[lap] != DRY else 1.0
        if rng.random() < circuit.sc_rate * boost / laps:
            length = rng.randint(3, 5)
            kind = "SC"
        elif rng.random() < circuit.vsc_rate * boost / laps:
            length = rng.randint(1, 3)
            kind = "VSC"
        else:
            lap += 1
            continue
        for i in range(lap, min(laps, lap + length)):
            neutralisation[i] = kind
        lap += length + 1
    return RaceEvents(neutralisation=neutralisation, weather=weather,
                      wet_start_laps=wet_start_laps, start_sc_laps=start_sc_laps)


def no_events(circuit: Circuit, start_compound: Optional[str] = None) -> RaceEvents:
    """A race with nothing random in it. A wet start dries exactly on the forecast lap."""
    weather = [DRY] * circuit.laps
    neutralisation: List[Optional[str]] = [None] * circuit.laps
    wet_start_laps = start_sc_laps = 0
    if start_compound in WET_TIRES:
        wet_start_laps = expected_drying_lap(circuit, start_compound)
        start_sc_laps = _wet_start(circuit, start_compound, wet_start_laps, weather,
                                   neutralisation)
    return RaceEvents(neutralisation=neutralisation, weather=weather,
                      wet_start_laps=wet_start_laps, start_sc_laps=start_sc_laps)


def pit_time_loss(circuit: Circuit, neutralisation: Optional[str], rng: random.Random,
                  noise: bool = True) -> float:
    """How long a pit stop costs, depending on whether the race is neutralised."""
    loss = circuit.pit_loss
    if neutralisation == "VSC":
        loss -= rng.uniform(*VSC_PIT_SAVING) if noise else sum(VSC_PIT_SAVING) / 2
    elif neutralisation == "SC":
        loss *= SC_PIT_FRACTION
    if noise:
        loss += rng.gauss(0, 0.4)
        if rng.random() < SLOW_STOP_CHANCE:
            loss += rng.uniform(3.0, 6.0)
    return max(loss, 5.0)


def _slick_for_remaining(compounds: Dict[str, Compound], laps_left: int) -> Compound:
    if laps_left <= 18:
        return compounds["Soft"]
    if laps_left <= 30:
        return compounds["Medium"]
    return compounds["Hard"]


def simulate_driver(circuit: Circuit, compounds: Dict[str, Compound], driver: Driver,
                    events: RaceEvents, rng: random.Random, noise: bool = True) -> RaceResult:
    """Run one driver through the race lap by lap and return what happened."""
    plan = driver.strategy
    planned_laps = list(plan.pit_laps)
    planned_compounds = list(plan.compounds[1:])
    tire = Tire(plan.compounds[0], circuit)
    result = RaceResult(driver=driver.name)
    laps = circuit.laps
    mismatch = 0  # consecutive laps where the other wet-weather tire would be better

    def take_planned_stop(lap: int) -> Compound:
        """Use the next planned stop now and push later stops back if it came late."""
        nonlocal planned_laps
        due = planned_laps.pop(0)
        compound = planned_compounds.pop(0)
        if lap > due:
            planned_laps = [p + (lap - due) for p in planned_laps]
        if planned_laps and planned_laps[0] - lap < MIN_STINT:
            shift = MIN_STINT - (planned_laps[0] - lap)
            planned_laps = [p + shift for p in planned_laps]
        while planned_laps and planned_laps[-1] > laps - 4:  # no room left for this stop
            planned_laps.pop()
            planned_compounds.pop()
        return compound

    for lap in range(1, laps + 1):
        idx = lap - 1
        state = events.weather[idx]
        flag = events.neutralisation[idx]

        # --- lap time -------------------------------------------------------------
        wear = tire.wear_loss()
        pace = tire.compound.pace_offset
        weather_loss = tire.weather_penalty(state)
        green_lap = (circuit.base_lap_time + fuel_penalty(circuit, lap) + pace + wear
                     + weather_loss + driver.pace_offset)
        if noise:
            green_lap += rng.gauss(0, driver.consistency)

        if flag:
            factor = SC_LAP_FACTOR if flag == "SC" else VSC_LAP_FACTOR
            lap_time = circuit.base_lap_time * factor
            result.breakdown["neutralised"] += lap_time - circuit.base_lap_time
        else:
            lap_time = green_lap
            result.breakdown["wear"] += wear
            result.breakdown["compound"] += pace
            result.breakdown["weather"] += weather_loss

        # --- pit decision at the end of the lap ------------------------------------
        new_compound = None
        reason = None
        laps_left = laps - lap
        name = tire.compound.name
        if (name == "Intermediate" and state == WET) or (name == "Wet" and state == DAMP):
            mismatch += 1
        else:
            mismatch = 0
        if laps_left > 0:
            if tire.compound.is_slick and state in (DAMP, WET):
                new_compound = compounds["Wet" if state == WET else "Intermediate"]
                reason = "rain"
            elif not tire.compound.is_slick and state == DRY:
                if planned_laps:
                    new_compound = take_planned_stop(lap)
                else:
                    new_compound = _slick_for_remaining(compounds, laps_left)
                reason = "drying"
            elif mismatch >= TIRE_CHANGE_DELAY and laps_left > 3:
                new_compound = compounds["Wet" if state == WET else "Intermediate"]
                reason = "rain" if state == WET else "drying"
                mismatch = 0
            elif planned_laps and tire.compound.is_slick:
                due_in = planned_laps[0] - lap
                window = SC_PIT_WINDOW if flag == "SC" else VSC_PIT_WINDOW
                if due_in <= 0:
                    reason = "plan"
                elif flag and due_in <= window and laps_left > 3:
                    reason = flag
                if reason:
                    new_compound = take_planned_stop(lap)

        if new_compound is not None:
            loss = pit_time_loss(circuit, flag, rng, noise)
            lap_time += loss
            result.breakdown["pit"] += loss
            result.pit_stops.append(PitStop(lap, reason, loss, new_compound.name))
            result.compounds_by_lap.append(tire.compound.name)
            tire = Tire(new_compound, circuit)
        else:
            result.compounds_by_lap.append(tire.compound.name)
            tire.run_lap(neutralised=flag is not None)

        result.lap_times.append(lap_time)
        result.total_time += lap_time

    return result


def simulate_race(circuit: Circuit, compounds: Dict[str, Compound], drivers: List[Driver],
                  seed: Optional[int] = None, rain_chance: Optional[float] = None,
                  start_compound: Optional[str] = None) -> Dict[str, RaceResult]:
    """Simulate a single race for several drivers who all face the same events."""
    rng = random.Random(seed)
    events = generate_events(circuit, rng, rain_chance, start_compound)
    noise_seed = rng.random()
    return {d.name: simulate_driver(circuit, compounds, d, events, random.Random(noise_seed))
            for d in drivers}
