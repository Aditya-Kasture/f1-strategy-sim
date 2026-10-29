# Pit Strategy: F1 Pit Stop Strategy Simulator

A Formula 1 race strategy simulator written in pure Python. Pick a circuit from the 2026
calendar and a starting tire, and it plans the best 1-, 2- and 3-stop strategies, races
each one thousands of times through a lap-by-lap Monte Carlo engine, and recommends the
winner with a plain-English explanation of *why*.

![Python](https://img.shields.io/badge/python-3.8%2B-blue)
![Dependencies](https://img.shields.io/badge/dependencies-none-brightgreen)
![Tests](https://img.shields.io/badge/tests-42%20passing-brightgreen)

## Features

- **24 circuits, 5 compounds**: Soft, Medium, Hard, Intermediate and Wet, with
  per-circuit pit loss, degradation, temperature and rain odds.
- **Optimal planning**: a dynamic-programming planner tries every legal tire order
  (two different dry compounds required) and finds the best pit laps.
- **Lap-by-lap race engine**: tire wear with a performance cliff, fuel burn, pit stops,
  Safety Cars, Virtual Safety Cars, rain and a drying track, plus a rival car.
- **Monte Carlo**: 100 to 20,000 simulated races. Every strategy faces the *same*
  Safety Cars, weather and noise in each race, so the comparison is fair.
- **Explained recommendations**: time gained over each alternative, risk, and how
  incidents, weather and the rival change the picture.
- **Desktop GUI** (tkinter) with a frosted "liquid glass" design, an interactive circuit
  gallery with track maps, hover-to-inspect charts, keyboard navigation, WCAG AA
  contrast and Windows display scaling (125–200%).
- **Text mode** (`--cli`) for terminals without a screen. The app falls back to it
  automatically if no window can open.
- **No dependencies**: standard library only, no network access.

## Quick start

```bash
git clone https://github.com/Aditya-Kasture/f1-strategy-sim.git
cd f1-strategy-sim

python main.py          # open the desktop app
python main.py --cli    # text-only version
```

Requires **Python 3.8+**. Nothing to install.

> **macOS + Homebrew Python:** if you see `No module named '_tkinter'`, run
> `brew install python-tk`. The python.org installer already includes tkinter.

### Command-line options

| Option        | Description                                  |
|---------------|----------------------------------------------|
| `--cli`       | Use the text version instead of the app      |
| `--data PATH` | Load circuits from a different JSON file     |

In text mode you're asked for a circuit (number or name, e.g. `8` or `Monaco`), starting
tire (`S`, `M`, `H`, `I`, `W`), rain chance, rival pace and number of races. Press Enter
to accept the default shown in brackets.

## Using the app

**Settings (left panel)**

| Control         | What it does |
|-----------------|--------------|
| Circuit         | Pick a track from the gallery of all 24 circuits |
| Starting tire   | Soft / Medium / Hard for a dry race; Intermediate (damp) or Wet (heavy rain, Safety Car start). Wet tracks dry out during the race |
| Rain chance     | Defaults to the circuit's usual value. In a wet race, the chance of another shower |
| Rival pace      | Rival's pace difference in seconds per lap |
| Simulated races | 100–20,000 (3,000 races take about 2 s) |

**Results tabs**

| Tab        | Shows |
|------------|-------|
| Overview   | The three strategies side by side, with the recommendation highlighted |
| Why        | The written explanation and comparison with each alternative |
| Race trace | Gap between strategies lap by lap, with SC / VSC / rain shaded |
| Lap times  | Lap times climbing with wear and dropping after each stop |
| Scenarios  | Win probability with no incidents, a Safety Car, a VSC or rain |
| Rival      | How far ahead of or behind the predicted rival you finish |

## How the simulation works

```
lap time = base lap + fuel load + compound pace + tire wear + weather penalty + noise
```

| Factor             | Model |
|--------------------|-------|
| Tire wear          | Grows every lap and accelerates past each compound's cliff lap; hotter, high-deg tracks wear faster |
| Fuel               | ~0.055 s/lap slower for each lap of fuel on board |
| Pit stop           | The circuit's pit-lane time loss (18–29 s), with occasional slow stops |
| Virtual Safety Car | Laps ~30% slower; pitting under VSC saves 5–6 s |
| Safety Car         | Laps ~40% slower; a stop costs about half as much, so cars pit early if a stop is near |
| Rain               | Slicks lose 4.5–11 s/lap on a wet track; cars switch to Inters/Wets and back as it dries |
| Rival              | Number of stops drawn from what teams historically did at that circuit |

## Project structure

```
main.py                     entry point: GUI, or text mode with --cli
data/
  circuits.json             24 circuits and 5 tire compounds
  track_outlines.json       track layouts for the maps
simulator/
  models.py                 Compound, Tire, Circuit, Stint, Strategy, Driver, ...
  data_loader.py            loads and validates the JSON (raises DataError)
  strategy.py               dynamic-programming pit planner and rival prediction
  engine.py                 lap-by-lap race engine: SC, VSC, weather, pit stops
  montecarlo.py             runs thousands of races and aggregates statistics
  explain.py                turns the numbers into a written recommendation
gui/
  app.py                    main window
  widgets.py                canvas-drawn buttons, sliders, track maps and charts
  glass.py                  the frosted "liquid glass" panels
  theme.py                  design tokens: colours, type scale, spacing, DPI scaling
tests/
  test_simulator.py         simulation tests (seeded, repeatable)
  test_design.py            WCAG AA contrast checks for every text colour
tools/
  check_layout.py           opens the app and reports any clipped text
```

## Testing

```bash
python -m unittest discover tests
```

To check the GUI layout for clipped text (needs a screen, optionally at a simulated
Windows scaling):

```bash
python tools/check_layout.py
python tools/check_layout.py 150
```

## Limitations

- Figures in `circuits.json` are simplified approximations, not official F1 data.
- The model compares total race times. It doesn't simulate overtaking, traffic, or the
  field bunching up behind a Safety Car.

## Credits

Built by Aditya Kasture as a final project for COMP9001.

Track layouts are adapted from
[bacinger/f1-circuits](https://github.com/bacinger/f1-circuits) (MIT License,
© 2019–2025 Tomislav Bacinger). GPS coordinates were converted to normalised 0–1 points
and stored locally, so the app never needs the internet.
