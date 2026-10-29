# Pit Strategy: F1 pit stop strategy simulator (COMP9001). To run the program: python main.py (see README.txt)
"""Loading circuit and compound data from JSON, with friendly error messages."""

from __future__ import annotations

import json
import os
from typing import Dict, List, Tuple

from .models import Circuit, Compound

DEFAULT_DATA_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                 "data", "circuits.json")

CIRCUIT_FIELDS = {
    "name": str, "country": str, "laps": int, "length_km": float, "base_lap_time": float,
    "pit_loss": float, "deg_multiplier": float, "track_temp": float, "sc_rate": float,
    "vsc_rate": float, "rain_chance": float,
}
COMPOUND_FIELDS = {"pace_offset": float, "wear_rate": float, "cliff_lap": int, "cliff_rate": float}
REQUIRED_COMPOUNDS = ("Soft", "Medium", "Hard", "Intermediate", "Wet")


class DataError(Exception):
    """Raised when the circuit data file is missing or malformed."""


def _number(value, kind, where: str):
    # bool is a subclass of int, so reject it explicitly
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DataError(f"{where} should be a number, got {value!r}")
    return int(value) if kind is int else float(value)


def _parse_compound(name: str, raw: dict) -> Compound:
    if not isinstance(raw, dict):
        raise DataError(f"Compound '{name}' should be an object")
    values = {}
    for key, kind in COMPOUND_FIELDS.items():
        if key not in raw:
            raise DataError(f"Compound '{name}' is missing '{key}'")
        values[key] = _number(raw[key], kind, f"Compound '{name}' field '{key}'")
    return Compound(name=name, colour=str(raw.get("colour", "#8E8E93")), **values)


def _parse_circuit(raw: dict, index: int) -> Circuit:
    if not isinstance(raw, dict):
        raise DataError(f"Circuit #{index + 1} should be an object")
    label = raw.get("name", f"#{index + 1}")
    values = {}
    for key, kind in CIRCUIT_FIELDS.items():
        if key not in raw:
            raise DataError(f"Circuit '{label}' is missing '{key}'")
        if kind is str:
            values[key] = str(raw[key])
        else:
            values[key] = _number(raw[key], kind, f"Circuit '{label}' field '{key}'")

    if not 10 <= values["laps"] <= 120:
        raise DataError(f"Circuit '{label}' has an unrealistic lap count ({values['laps']})")
    if values["base_lap_time"] <= 0 or values["pit_loss"] <= 0 or values["deg_multiplier"] <= 0:
        raise DataError(f"Circuit '{label}' needs positive lap time, pit loss and degradation")
    if not 0 <= values["rain_chance"] <= 1:
        raise DataError(f"Circuit '{label}' rain_chance must be between 0 and 1")

    history_raw = raw.get("historical_strategies", {"1": 0.5, "2": 0.5})
    try:
        history = {int(k): float(v) for k, v in history_raw.items() if float(v) > 0}
    except (AttributeError, TypeError, ValueError):
        raise DataError(f"Circuit '{label}' has invalid historical_strategies") from None
    if not history or any(k not in (1, 2, 3) for k in history):
        raise DataError(f"Circuit '{label}' historical_strategies must use keys 1, 2 or 3")
    total = sum(history.values())
    history = {k: v / total for k, v in history.items()}

    try:
        race_round = int(raw.get("round", index + 1))
    except (TypeError, ValueError):
        raise DataError(f"Circuit '{label}' has an invalid round number") from None
    return Circuit(historical_strategies=history, grand_prix=str(raw.get("grand_prix", "")),
                   round=race_round, **values)


def load_data(path: str = DEFAULT_DATA_FILE) -> Tuple[List[Circuit], Dict[str, Compound]]:
    """Read the JSON file and return (circuits, compounds). Raises DataError on any problem."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except FileNotFoundError:
        raise DataError(f"Could not find the data file: {path}") from None
    except json.JSONDecodeError as exc:
        raise DataError(f"The data file is not valid JSON (line {exc.lineno}): {exc.msg}") from None
    except OSError as exc:
        raise DataError(f"Could not read the data file: {exc}") from None

    if not isinstance(raw, dict) or "circuits" not in raw or "compounds" not in raw:
        raise DataError("The data file needs a 'compounds' object and a 'circuits' list")

    compounds = {name: _parse_compound(name, value) for name, value in raw["compounds"].items()}
    missing = [c for c in REQUIRED_COMPOUNDS if c not in compounds]
    if missing:
        raise DataError(f"The data file is missing compounds: {', '.join(missing)}")

    if not isinstance(raw["circuits"], list) or not raw["circuits"]:
        raise DataError("The data file has no circuits")
    circuits = [_parse_circuit(c, i) for i, c in enumerate(raw["circuits"])]
    return circuits, compounds


DEFAULT_OUTLINE_FILE = os.path.join(os.path.dirname(DEFAULT_DATA_FILE), "track_outlines.json")


def load_outlines(path: str = DEFAULT_OUTLINE_FILE) -> Dict[str, List[Tuple[float, float]]]:
    """Track map outlines (points scaled to 0..1). Missing or broken files give no maps."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            raw = json.load(handle)["outlines"]
        return {name: [(float(x), float(y)) for x, y in points] for name, points in raw.items()}
    except (OSError, ValueError, KeyError, TypeError):
        return {}


def find_circuit(circuits: List[Circuit], name: str) -> Circuit:
    """Find a circuit by name or country, ignoring case. Raises ValueError if not found."""
    wanted = name.strip().lower()
    for circuit in circuits:
        if wanted in (circuit.name.lower(), circuit.country.lower()):
            return circuit
    raise ValueError(f"Unknown circuit '{name}'. Choose from: "
                     + ", ".join(c.name for c in circuits))
