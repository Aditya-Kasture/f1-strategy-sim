# Pit Strategy: F1 pit stop strategy simulator (COMP9001). To run the program: python main.py (see README.txt)
"""Turns raw Monte Carlo numbers into a recommendation a person can read."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

from .engine import SC_PIT_FRACTION, VSC_PIT_SAVING
from .strategy import expected_drying_lap
from .montecarlo import SimulationResult, StrategyStats


def format_race_time(seconds: float) -> str:
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{int(hours)}:{int(minutes):02d}:{secs:04.1f}"


def pct(value: float) -> str:
    return f"{value * 100:.0f}%"


def degradation_label(multiplier: float) -> str:
    if multiplier >= 1.2:
        return "high"
    if multiplier <= 0.7:
        return "low"
    return "medium"


@dataclass
class Comparison:
    """How the recommended strategy stacks up against one alternative."""

    other: StrategyStats
    mean_gap: float          # seconds the recommended strategy is faster on average
    head_to_head: float      # share of races where the recommended one finished ahead
    pit_diff: float          # other minus recommended
    tire_diff: float
    text: str


@dataclass
class Recommendation:
    best: StrategyStats
    headline: str
    summary: str
    comparisons: List[Comparison] = field(default_factory=list)
    reasons: List[Tuple[str, str]] = field(default_factory=list)

    def as_text(self) -> str:
        lines = [self.headline, "", self.summary, ""]
        for title, body in self.reasons:
            lines.append(f"• {title}: {body}")
        return "\n".join(lines)


def _tire_cost(stat: StrategyStats) -> float:
    return stat.breakdown_mean("wear") + stat.breakdown_mean("compound")


def _compare(best: StrategyStats, other: StrategyStats) -> Comparison:
    gap = other.mean - best.mean
    ahead = sum(1 for a, b in zip(best.times, other.times) if a < b) / max(1, best.runs)
    pit_diff = other.breakdown_mean("pit") - best.breakdown_mean("pit")
    tire_diff = _tire_cost(other) - _tire_cost(best)
    weather_diff = other.breakdown_mean("weather") - best.breakdown_mean("weather")

    o, b = other.strategy.name, best.strategy.name
    faster = f"{gap:.1f} s faster" if gap >= 0 else f"{-gap:.1f} s slower"
    text = (f"Against the {o} ({other.strategy.short_sequence}, pit lap "
            f"{', '.join(map(str, other.strategy.pit_laps))}), the {b} is {faster} on average "
            f"and finishes ahead in {pct(ahead)} of races. ")
    if pit_diff < 0 and tire_diff > 0:
        text += (f"The {o} spends {-pit_diff:.1f} s less in the pit lane, but its longer stints "
                 f"cost {tire_diff:.1f} s more in tire wear and slower compounds.")
    elif pit_diff > 0 and tire_diff < 0:
        text += (f"The {o} gains {-tire_diff:.1f} s from fresher, faster tires, but that "
                 f"doesn't cover the extra {pit_diff:.1f} s it spends in the pit lane.")
    else:
        text += (f"It loses {pit_diff:+.1f} s in the pits and {tire_diff:+.1f} s on tires "
                 f"compared with the {b}.")
    if abs(weather_diff) >= 1.0:
        text += (f" Rain costs it {weather_diff:+.1f} s more on average because it is on the "
                 f"wrong tire for longer when showers arrive.")
    return Comparison(other, gap, ahead, pit_diff, tire_diff, text)


def build_recommendation(result: SimulationResult) -> Recommendation:
    best = result.best()
    others = [s for s in result.stats if s is not best]
    comparisons = [_compare(best, o) for o in sorted(others, key=lambda s: s.mean)]
    circuit = result.circuit
    plan = best.strategy

    headline = f"Go with the {plan.name}: {plan.sequence}"
    pit_laps = ", ".join(str(l) for l in plan.pit_laps)
    summary = (f"Pit on lap {pit_laps}. It was the fastest strategy in {pct(best.win_probability)} "
               f"of {result.runs:,} simulated races at {circuit.country}, with an expected race "
               f"time of {format_race_time(best.mean)}.")

    reasons: List[Tuple[str, str]] = []

    # 1. The basic trade-off at this track
    reasons.append(("The trade-off here", (
        f"{circuit.country} has {degradation_label(circuit.deg_multiplier)} tire degradation "
        f"(x{circuit.deg_multiplier:.2f}, track {circuit.track_temp:.0f}°C) and a green-flag pit "
        f"stop costs about {circuit.pit_loss:.1f} s. Every extra stop must win back that time "
        f"through fresher tires, so the right number of stops depends on how fast tires fade here.")))

    # 2. The gain of choosing the best option
    if comparisons:
        nearest, worst = comparisons[0], comparisons[-1]
        if nearest.mean_gap >= 0:
            gain = (f"Choosing the {plan.name} saves {nearest.mean_gap:.1f} s on average over "
                    f"the next-best option ({nearest.other.strategy.name})")
        else:
            gain = (f"The {plan.name} is {-nearest.mean_gap:.1f} s slower on average than the "
                    f"{nearest.other.strategy.name} (a few bad races drag its average down), "
                    f"but it finishes ahead more often")
        if worst is not nearest:
            gain += f" and is {worst.mean_gap:.1f} s faster than the worst ({worst.other.strategy.name})"
        gain += ". "
        margin = best.win_probability - nearest.other.win_probability
        if margin < 0.10:
            gain += ("That's a close call, so the strategy should stay flexible and react to "
                     "Safety Cars.")
        else:
            gain += (f"It is the fastest choice in {pct(best.win_probability)} of races versus "
                     f"{pct(nearest.other.win_probability)} for the {nearest.other.strategy.name}, "
                     "a clear margin.")
        reasons.append(("What you gain", gain))

    # 3. Safety Cars and Virtual Safety Cars
    if result.runs_with_sc:
        green = circuit.pit_loss
        sc_cost = green * SC_PIT_FRACTION
        vsc_cost = green - sum(VSC_PIT_SAVING) / 2
        sc_rates = {s.strategy.name: s.wins_with_sc / result.runs_with_sc for s in result.stats}
        sc_best = max(sc_rates, key=sc_rates.get)
        text = (f"{pct(result.runs_with_sc / result.runs)} of races had a Safety Car. A stop "
                f"under the Safety Car costs only ~{sc_cost:.0f} s and under a VSC ~{vsc_cost:.0f} s, "
                f"versus {green:.0f} s normally, so strategies pit early when one comes out. ")
        if sc_best != plan.name:
            text += (f"In those races the {sc_best} wins {pct(sc_rates[sc_best])} of the time "
                     f"(the {plan.name} wins {pct(sc_rates[plan.name])}): more stops means more "
                     "chances to pit cheaply. If a Safety Car appears early, switching is worth "
                     "considering.")
        else:
            text += (f"The {plan.name} still wins {pct(sc_rates[plan.name])} of Safety Car races, "
                     "so the recommendation holds even when the race is neutralised.")
        reasons.append(("Safety Cars", text))

    # 4. Weather
    if result.wet_start:
        drying = expected_drying_lap(circuit, result.start_compound)
        if result.start_compound == "Wet":
            opening = ("The race starts in heavy rain on full Wet tires, behind the Safety Car. "
                       "As the rain eases, teams switch to Intermediates")
        else:
            opening = "The race starts on a damp track on Intermediates"
        avg_weather_stops = best.avg_stops - plan.stops
        reasons.append(("Wet start", (
            f"{opening}. The track is forecast to dry around lap {drying}, so the switch to "
            f"slicks is planned for lap {plan.pit_laps[0]}. The exact lap changes from race to race, so "
            f"every strategy waits for the track to dry before switching. "
            + (f"After that the {plan.name} runs to the flag on one set of slicks."
               if plan.stops == 1 else
               f"After that the {plan.name} makes {plan.stops - 1} more "
               f"stop{'s' if plan.stops > 2 else ''} on slicks.")
            + (f" On average it makes {avg_weather_stops:.1f} extra weather stops "
                          "on top of the plan." if avg_weather_stops >= 0.1 else ""))))
    if result.runs_with_rain:
        rain_rates = {s.strategy.name: s.wins_with_rain / result.runs_with_rain for s in result.stats}
        rain_best = max(rain_rates, key=rain_rates.get)
        text = (f"A rain shower hit {pct(result.runs_with_rain / result.runs)} of races "
                f"(forecast {pct(result.rain_chance)}). Everyone switches to Intermediates, or "
                f"full Wets in heavy rain, when a shower arrives, and that often replaces a "
                f"planned stop. In those races the {rain_best} wins "
                f"{pct(rain_rates[rain_best])} of the time.")
        reasons.append(("Weather", text))
    elif not result.wet_start:
        reasons.append(("Weather", "No rain in the forecast, so the race is decided by tire "
                                   "wear, pit stops and Safety Cars."))

    # 5. The rival
    history = circuit.historical_strategies
    share = history.get(result.rival_strategy.stops, 0)
    rival_text = (f"The rival is predicted to run a {result.rival_strategy.name} "
                  f"({result.rival_strategy.sequence}), the choice of {pct(share)} of the field here "
                  f"in past races. ")
    pace = result.rival_pace
    if abs(pace) > 0.001:
        rival_text += f"They are {abs(pace):.2f} s/lap {'faster' if pace < 0 else 'slower'} than you. "
    rival_text += f"With the {plan.name} you finish ahead of them in {pct(best.rival_probability)} of races"
    best_vs_rival = max(result.stats, key=lambda s: s.rival_probability)
    if best_vs_rival is not best and best_vs_rival.rival_probability - best.rival_probability > 0.02:
        rival_text += (f"; the {best_vs_rival.strategy.name} beats them slightly more often "
                       f"({pct(best_vs_rival.rival_probability)}) because it puts you on a "
                       "different strategy to theirs.")
    else:
        rival_text += "."
    reasons.append(("The rival", rival_text))

    # 6. Risk: how much time each strategy throws away on the days it is the wrong call
    regret = {s.strategy.name: sorted(result.time_lost(s)) for s in result.stats}

    def bad_day(name: str) -> float:
        values = regret[name]
        return values[int(0.9 * (len(values) - 1))]

    safest = min(regret, key=bad_day)
    risk = (f"Even on the days it isn't the fastest, the {plan.name} rarely costs much: in 9 out "
            f"of 10 races it is within {bad_day(plan.name):.1f} s of the best possible choice")
    others_risk = [f"{name} {bad_day(name):.1f} s" for name in regret if name != plan.name]
    if others_risk:
        risk += f" (compared with {', '.join(others_risk)})"
    risk += "."
    if safest != plan.name:
        risk += (f" The {safest} has the smallest worst case, so it is the safer pick if you "
                 "want to avoid a bad result rather than chase the best one.")
    reasons.append(("Risk", risk))

    for comparison in comparisons:
        reasons.append((f"vs {comparison.other.strategy.name}", comparison.text))

    return Recommendation(best=best, headline=headline, summary=summary,
                          comparisons=comparisons, reasons=reasons)
