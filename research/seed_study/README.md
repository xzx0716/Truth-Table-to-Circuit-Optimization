# Reproduce the initial-circuit comparison

From the repository root, build the solver and supply a course-format case directory and an independent checker. The checker accepts an input path and a netlist path and writes JSON containing `correct`, `area`, and `delay`. On mismatch it writes a `reason`. Reports from a previous run are kept by requiring a fresh output directory.

```sh
make
python3 research/seed_study/run.py --solver build/solver \
  --checker /path/to/checker --cases /path/to/stage1 \
  --out results/new-seed-comparison
```

Each profile uses a separate, single-threaded solver process. The experiment strips inherited TTC environment settings and selects the constructor with `TTC_INITIAL_SEED`. The reference `github` runs the current repository's synthesis method to obtain the initial circuit. Every profile then normalizes its circuit, runs one complete production algebraic sweep, and uses the same circuit selection rule on the incoming and rewritten circuits. An interrupted sweep cannot contribute.

The runner executes a full warm-up followed by three rounds. It shuffles the cases and the order of profiles within each case in each round, using the random seed in the manifest. Elapsed time includes process launch, parsing, construction, optimization and writing the final netlist, through process exit. Outside that timer it verifies the emitted netlist against the complete truth table. Verification can be reused for a byte-identical netlist on the same case. The input's time and memory limits apply to each measured process.

`runs.csv` keeps every trial, including warm-up round 0. `comparison.csv` records the seed area and delay, final area and delay, and minimum, median and maximum measured total time per case and profile. Eligibility requires three completed correct timed runs with identical output hashes. The comparison includes valid circuits that exceed target delay, with target attainment reported separately.

For each case, the area/delay frontier contains distinct points that no other compared circuit improves in either metric without worsening the other. A new point differs from the reference and remains on the combined frontier. Equal area/delay pairs count once, with reproducible tie-breaking. Three-dimensional frontier membership uses median runtime. Timing-dependent retention additionally requires every alternative with equal or better area and delay to be slower across the entire observed range, with a margin equal to the larger of 0.2 ms and 5% of the candidate's median. These thresholds are experimental choices. Three samples characterize the observed machine only. No total-time claim for an online portfolio is inferred by combining winners from different runs.

`retained.json` contains the reference plus profiles adding at least one new area/delay point or meeting the timing-dependent retention rule. `summary.csv` gives counts by profile. Refer to `manifest.json` for tested sources, binary, input hashes and platform.

The first native screening run, `results/seed-study-20261117`, used ten profiles. The expanded comparison also includes `historical-adaptive`, which ports the variable-order selection from the earlier solver. The official Linux screen uses five timed rounds and supplies an additional `deployed` measurement outside the controlled set. To summarize an official combined log, execute `python3 research/seed_study/summarize_official.py /path/to/official-results`. When the official evaluator omits output hashes, a pair is admitted only if every round passes and its A/D pair repeats. A/D equality then establishes metric stability only.
