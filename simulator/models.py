# Pit Strategy: F1 pit stop strategy simulator (COMP9001). To run the program: python main.py (see README.txt)
"""Core data classes: tire compounds, tires, circuits, strategies and drivers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

SLICKS = ("Soft", "Medium", "Hard")
WET_TIRES = ("Intermediate", "Wet")
STARTING_COMPOUNDS = SLICKS + WET_TIRES
DRY, DAMP, WET = "dry", "damp", "wet"

# Extra seconds per lap when the tire does not suit the track surface.
# Slicks are hopeless in the wet. Intermediates and full Wets are slow in the dry
# (their dry penalty is already in their pace_offset) but quick when it rains:
# Intermediates are best on a damp track, full Wets in heavy rain.
WEATHER_PENALTY = {
    "slick": {DRY: 0.0, DAMP: 4.5, WET: 11.0},
    "Intermediate": {DRY: 0.0, DAMP: -2.7, WET: -1.5},  # net +0.8 s damp, +2.0 s wet
    "Wet": {DRY: 0.0, DAMP: -4.0, WET: -5.2},           # net +2.0 s damp, +0.8 s wet
}


@dataclass(frozen=True)
class Compound:
    """A tire compound and how it behaves (loaded from circuits.json)."""

    name: str
    pace_offset: float   # seconds per lap slower than a new Soft
    wear_rate: float     # seconds lost per lap of tire age (average track)
    cliff_lap: int       # age at which the tire falls off a cliff (average track)
    cliff_rate: float    # extra loss per (lap past the cliff)^2
    colour: str = "#8E8E93"

    @property
    def short(self) -> str:
        return self.name[0]

    @property
    def is_slick(self) -> bool:
        return self.name in SLICKS


@dataclass(frozen=True)
class Circuit:
    """A race track and the parameters that drive the simulation."""

    name: str
    country: str
    laps: int
    length_km: float
    base_lap_time: float
    pit_loss: float
    deg_multiplier: float
    track_temp: float
    sc_rate: float
    vsc_rate: float
    rain_chance: float
    historical_strategies: Dict[int, float]
    grand_prix: str = ""
    round: int = 0

    @property
    def title(self) -> str:
        return self.grand_prix or f"{self.name} Grand Prix"

    @property
    def temp_factor(self) -> float:
        """Hotter tracks chew through tires faster (1.5% per degree above 35C)."""
        return max(0.7, 1.0 + 0.015 * (self.track_temp - 35))

    @property
    def most_common_stops(self) -> int:
        return max(self.historical_strategies, key=self.historical_strategies.get)


class Tire:
    """One set of tires fitted to a car. Tracks its age and computes lap time loss."""

    def __init__(self, compound: Compound, circuit: Circuit, age: float = 0.0):
        self.compound = compound
        self.circuit = circuit
        self.age = age

    @property
    def effective_wear_rate(self) -> float:
        return self.compound.wear_rate * self.circuit.deg_multiplier * self.circuit.temp_factor

    @property
    def effective_cliff_lap(self) -> float:
        return self.compound.cliff_lap / self.circuit.deg_multiplier

    def wear_loss(self) -> float:
        """Seconds lost this lap because the tire is worn."""
        loss = self.effective_wear_rate * self.age
        past_cliff = self.age - self.effective_cliff_lap
        if past_cliff > 0:
            loss += self.compound.cliff_rate * past_cliff ** 2
        return loss

    def weather_penalty(self, track_state: str) -> float:
        key = "slick" if self.compound.is_slick else self.compound.name
        return WEATHER_PENALTY[key][track_state]

    def run_lap(self, neutralised: bool = False) -> None:
        """Age the tire by one lap. Tires barely wear behind the Safety Car."""
        self.age += 0.3 if neutralised else 1.0

    def __repr__(self) -> str:
        return f"Tire({self.compound.name}, age={self.age:.1f})"


@dataclass
class Stint:
    """A continuous run on one set of tires."""

    compound: Compound
    start_lap: int  # first lap on these tires (1-based)
    end_lap: int    # last lap on these tires (inclusive)

    @property
    def length(self) -> int:
        return self.end_lap - self.start_lap + 1


@dataclass
class Strategy:
    """A planned race strategy: compounds in order and the laps you pit on."""

    stops: int
    compounds: List[Compound]
    pit_laps: List[int]  # pit at the END of these laps
    total_laps: int
    expected_time: float = 0.0  # clean-race time from the planner

    @property
    def name(self) -> str:
        return f"{self.stops}-stop"

    @property
    def sequence(self) -> str:
        return " → ".join(c.name for c in self.compounds)

    @property
    def short_sequence(self) -> str:
        return "-".join(c.short for c in self.compounds)

    @property
    def stints(self) -> List[Stint]:
        bounds = [0] + list(self.pit_laps) + [self.total_laps]
        return [Stint(c, bounds[i] + 1, bounds[i + 1]) for i, c in enumerate(self.compounds)]

    def describe(self) -> str:
        laps = ", ".join(str(l) for l in self.pit_laps)
        return f"{self.name}: {self.sequence} (pit on lap {laps})"


@dataclass
class Driver:
    """A car in the simulation: who is driving and which strategy they follow."""

    name: str
    strategy: Strategy
    pace_offset: float = 0.0   # seconds per lap relative to our car (negative = faster)
    consistency: float = 0.25  # standard deviation of lap-time noise in seconds


@dataclass
class PitStop:
    lap: int
    reason: str      # "plan", "SC", "VSC", "rain", "drying"
    time_lost: float
    new_compound: str


@dataclass
class RaceResult:
    """Everything that happened to one driver in one simulated race."""

    driver: str
    total_time: float = 0.0
    lap_times: List[float] = field(default_factory=list)
    compounds_by_lap: List[str] = field(default_factory=list)
    pit_stops: List[PitStop] = field(default_factory=list)
    breakdown: Dict[str, float] = field(default_factory=lambda: {
        "pit": 0.0, "wear": 0.0, "compound": 0.0, "weather": 0.0, "neutralised": 0.0})

    @property
    def stops_made(self) -> int:
        return len(self.pit_stops)


@dataclass
class RaceEvents:
    """The random things that happen to everybody in one race."""

    neutralisation: List[Optional[str]]  # per lap (index 0 = lap 1): None, "SC" or "VSC"
    weather: List[str]                    # per lap: "dry", "damp" or "wet"
    wet_start_laps: int = 0               # laps before a wet track dries out (0 = dry start)
    start_sc_laps: int = 0                # laps behind the Safety Car at a full-wet start

    @property
    def had_sc(self) -> bool:
        """A Safety Car during the race (the one leading a full-wet start doesn't count)."""
        return "SC" in self.neutralisation[self.start_sc_laps:]

    @property
    def had_vsc(self) -> bool:
        return "VSC" in self.neutralisation

    @property
    def had_rain(self) -> bool:
        """A rain shower after the start (a wet start on its own doesn't count)."""
        return any(w != DRY for w in self.weather[self.wet_start_laps:])
