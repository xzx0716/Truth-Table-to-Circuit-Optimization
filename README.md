# Truth Table to Circuit Optimization

UFUG2106 Stage 1: C++17, sequential single-thread synthesis using AND2, OR2 and NOT.
The final default is the budgeted nine-seed portfolio, integrated from both teammates.

## Build and run

Ubuntu 22.04 / WSL, GCC 11+ and Make:

```sh
make
./build/solver INPUT_PATH OUTPUT_PATH
```

No environment settings are required. The executable needs no Python, SAT/MILP solver,
or external library. Python is used only for tests, research and packaging.
The command line is always exactly an input path and an output path.

## Stage 1 submission

- [Final report: Method and all 25 case results](docs/stage1-report.md)
- [Submission PDF](output/pdf/stage1-report.pdf)
- [Chinese integration handoff](docs/Stage1-Handoff.md)
- [Final measured evidence](results/stage1-final-20261118)
- [Final release and standalone submission package](https://github.com/xzx0716/Truth-Table-to-Circuit-Optimization/releases/tag/stage1-final-v1)

The final configuration and original fast control both pass all 25 cases in five
measured official rounds and meet every target delay. The selected final circuits
improve both area/delay in 8 cases, match in 7, and trade area for delay in 10.
The portfolio increases runtime. See the report for measured times and limitations;
we do not know the official numerical score weights or claim global optimality.
GitHub publication does not submit to the course platform.

## Standalone source

```sh
python3 tools/export_submission.py --output dist/solver.cpp
g++ -O2 -std=c++17 dist/solver.cpp -o dist/solver
./dist/solver INPUT_PATH OUTPUT_PATH
```

Edit production code in src/ and include/ttc/, never the generated dist source.
The release zip includes solver.cpp, a brief compile README, REPORT.md, REPORT.pdf,
a handoff, file checksums and compact official result evidence.

## Reproduce validation

```sh
make test
make unit
python3 tests/test_seed_study.py build/solver
```

Place the original evaluator at data/local/evaluator and the original cases in
data/local/stage1 (both ignored and not redistributed), then run:

```sh
chmod +x data/local/evaluator
python3 tools/run_experiments.py --solver final=build/solver --solver fast=build/solver --profile fast=sweep --out results/MY-RUN --rounds 5 --warmup 1 --save-outputs --rss-probe --build-command make
python3 tools/analyze_results.py results/MY-RUN/runs.csv
```

Never overwrite old experiments. Manifests bind sources, binary, evaluator, inputs,
commands and environment. Timings depend on the machine and load.

## Optional research settings

Any explicit TTC_STRATEGY selects the previous pipeline: baseline, sweep, greedy,
beam, anneal, multistart or portfolio (the latter combines local searches and is
**different** from the final seed portfolio). Use TTC_STRATEGY=sweep for the fast control.
An explicit TTC_INITIAL_SEED selects one of the 11 experimental seeds;
TTC_INITIAL_SEEDS accepts an explicit comma-separated seed list, always starting
with github. The default nine-seed list is compiled in src/main.cpp.
Do not set conflicting single-seed and multiple-seed settings.

Other research options: TTC_CUT, TTC_ROUNDS, TTC_BEAM, TTC_RESTARTS, TTC_REGIONS,
TTC_SEED and TTC_SEARCH_MS. TTC_RESEARCH_MS overrides the course runtime limit
for offline research only: over-limit results are not compliant submission results.
TTC_COST_LOG / TTC_FRONTIER_LOG enable diagnostics and can affect runtime.
Clear inherited TTC_* settings when measuring the submission default.

## Version and experiment history

- stage1-pareto-v1: frozen supplied teammate Pareto baseline.
- dev-base-v1: modular split and integration API.
- person-a-stage1-v1 / v2: A's completed search/runtime research and previous fast default.
- experiment/b-historical-seeds: B's eleven-constructor study and shared-budget portfolio.
- stage1-final-v1: combined final Stage 1 delivery, with the portfolio as default.

Older A-only documents remain under docs/history/ and prior immutable releases.
The [seed study](docs/seed-study.md), [local methods](docs/local-search.md),
[runtime model](docs/runtime-model.md) and [experiment register](docs/experiment-register.md)
retain exploratory work, including costly and failed alternatives.
