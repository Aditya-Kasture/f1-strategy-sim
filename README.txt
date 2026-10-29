PIT STRATEGY: F1 PIT STOP STRATEGY SIMULATOR
COMP9001 final project by Aditya Kasture

=====================================================================================
HOW TO RUN (please read first)
=====================================================================================

The file to run is main.py. Keep the folder structure as it is: main.py needs the
simulator/, gui/ and data/ folders next to it.

  python main.py            Opens the app (a graphical window).
  python main.py --cli      Text-only version. Works in Ed's terminal.

  python -m unittest discover tests     Runs the 42 automated tests (works in Ed).

Requirements:
  - Python 3.8 or newer.
  - Only Python's built-in (standard) libraries. Nothing to install.

-------------------------------------------------------------------------------------
NOTES FOR THE TUTOR
-------------------------------------------------------------------------------------

* GUI application: the main version is a GUI made with tkinter, Python's built-in GUI
  library. It needs a screen, so it will not open inside Ed. Please run
  `python main.py` on your own computer to see it.

* Inside Ed: use the text version, `python main.py --cli`. If you run plain
  `python main.py` somewhere without a screen, the program notices that the window
  can't open and starts the text version by itself, so it never crashes.

* No other libraries: no libraries outside the standard library, no audio or video, and
  no web or networking. The modules used are:
    tkinter, argparse, dataclasses, json, math, os, queue, random, statistics, sys,
    threading, typing, itertools, unittest, tempfile

* Data files: the circuit data is read from data/circuits.json and the track maps from
  data/track_outlines.json. If the track map file is missing, the app still runs, just
  without maps.

* tkinter on a Mac: the python.org installer includes tkinter. With Homebrew Python, if
  you see "No module named '_tkinter'", run `brew install python-tk`.

* Using the text version: it asks for a circuit (a number or a name, e.g. 8 or
  Monaco), a starting tire (S, M, H, I or W), the rain chance, the rival's pace and the
  number of races. Press Enter to accept the default shown in brackets. Bad input is
  explained and asked again.

=====================================================================================
WHAT IT DOES
=====================================================================================

Pick one of the 24 circuits on the 2026 calendar and a starting tire (Soft, Medium,
Hard, Intermediate or Wet). The program:
  1. Plans the best 1-stop, 2-stop and 3-stop strategy for that circuit.
  2. Simulates the race lap by lap: tire wear, fuel, pit stops, Safety Cars, Virtual
     Safety Cars, rain, and a rival car.
  3. Repeats this thousands of times (Monte Carlo) and counts how often each strategy is
     fastest, which gives a win probability for each one.
  4. Recommends the best strategy and explains WHY, compared with the alternatives,
     including how much time it gains over each one.

-------------------------------------------------------------------------------------
USING THE APP
-------------------------------------------------------------------------------------

Left panel:
  Circuit           Click a track in the gallery of all 24 circuits.
  Starting tire     Soft / Medium / Hard for a dry race. Intermediate (damp start) or
                    Wet (heavy rain, starts behind the Safety Car) for a wet race. A wet
                    track dries out partway through.
  Rain chance       Starts at the circuit's usual value. In a wet race it is the chance
                    of another shower later on.
  Rival pace        How much faster or slower the rival is, in seconds per lap.
  Simulated races   100 to 20,000. Bad input turns the box red and explains why.
  Button / Enter    Runs the simulation. 3,000 races take about 2 seconds.

Results tabs:
  Overview     A table comparing the three strategies side by side. The recommended
               one is highlighted.
  Why          The written explanation: the trade-off at this track, the time gained,
               Safety Cars, weather, the rival, risk, and a comparison with each
               alternative.
  Race trace   The gap between the strategies lap by lap, in a typical race or a random
               one, with Safety Cars, VSCs and rain shaded.
  Lap times    Lap times rising as tires wear, then dropping after each pit stop.
  Scenarios    Win probability in races with no incidents, a Safety Car, a VSC or rain.
  Rival        How far ahead of or behind the predicted rival you finish.

Every chart is interactive: hover over it to see the exact values. The app also works
from the keyboard (Tab, the arrow keys, Space/Enter) and adjusts to Windows display
scaling (125%, 150%, 200%).

=====================================================================================
HOW THE SIMULATION WORKS
=====================================================================================

Lap time = base lap time + fuel load + tire compound pace + tire wear + weather
penalty + random noise.

  - Tire wear grows every lap and gets much worse after a compound's "cliff" lap. Hot
    tracks and high-degradation circuits wear tires faster.
  - Fuel: about 0.055 s per lap slower for each lap of fuel still on board.
  - Pit stop: costs the circuit's pit-lane time loss (18 to 29 s).
  - Virtual Safety Car: laps are about 30% slower. A stop under VSC saves 5 to 6 s.
  - Safety Car: laps are about 40% slower and a stop costs about half as much. Cars pit
    early to take advantage if a planned stop is close.
  - Rain: slicks lose 4.5 to 11 s per lap on a wet track, so cars switch to
    Intermediates or Wets, and back to slicks when it dries.
  - Rival: the rival's number of stops is drawn from what teams historically did at that
    circuit.

Planning: for each number of stops, a dynamic-programming planner tries every legal tire
order (the rules require two different dry compounds) and finds the best pit laps.

Fair comparison: in each simulated race all three strategies face exactly the same
Safety Cars, weather and random noise, so the only difference is the strategy.

=====================================================================================
COURSE REQUIREMENTS
=====================================================================================

  Classes             Tire, Stint, Strategy, Driver, Circuit, Compound, RaceEvents,
                      MonteCarloSimulator, StrategyStats, Recommendation, and the GUI
                      widget classes.
  File I/O            Circuit and tire data are read from data/circuits.json, and track
                      maps from data/track_outlines.json. You can use a different file
                      with `python main.py --data path/to/file.json`.
  Exception handling  A custom DataError for missing or invalid data files. ValueError
                      checks on every user input, and the text version asks again until
                      the input is valid. Unexpected errors in the app are shown in a
                      dialog box, and a missing screen falls back to the text version.
  random module       Safety Cars, VSCs, rain, lap-time noise, slow pit stops and the
                      rival's strategy are all random. random.Random can be seeded, so
                      the tests are repeatable.

=====================================================================================
FILES
=====================================================================================

  main.py                     RUN THIS. Starts the app, or the text version with --cli
  data/circuits.json          the 24 circuits and 5 tire compounds
  data/track_outlines.json    track layouts for the maps
  simulator/models.py         classes: Compound, Tire, Circuit, Stint, Strategy, Driver...
  simulator/data_loader.py    reads and checks the JSON files (DataError)
  simulator/strategy.py       best pit-lap planner and rival prediction
  simulator/engine.py         lap-by-lap race engine: Safety Cars, VSC, weather, pit stops
  simulator/montecarlo.py     runs thousands of races and collects statistics
  simulator/explain.py        turns the numbers into the written recommendation
  gui/app.py                  the main window
  gui/widgets.py              buttons, selectors, sliders, track maps and charts
  gui/glass.py                the frosted "liquid glass" panels
  gui/theme.py                colours, fonts, spacing and display scaling
  tests/test_simulator.py     tests for the simulation
  tests/test_design.py        checks that all text colours are readable (contrast)
  tools/check_layout.py       optional: checks no text is cut off in the app

=====================================================================================
CREDITS AND LIMITATIONS
=====================================================================================

Track layouts in data/track_outlines.json come from github.com/bacinger/f1-circuits
(MIT License, (c) 2019-2025 Tomislav Bacinger). I converted the GPS coordinates to flat
0-1 points. They are stored in the file, so the program never uses the internet.

The figures in circuits.json are simplified approximations for teaching, not official
Formula 1 data. The model compares total race times and doesn't simulate overtaking,
traffic, or the field bunching up behind a Safety Car.
