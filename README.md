# Truth Table to Circuit Optimization

C++17, single-thread truth-table circuit synthesis using AND2, OR2 and NOT.

## Build and run

Ubuntu 22.04 / WSL Ubuntu, GCC 11+ and Make:

```sh
make
./build/solver INPUT_PATH OUTPUT_PATH
make test
```

The solver has no Python/SAT/MILP runtime dependencies. Python is only needed for tests, research and packaging.

## Versions

- `stage1-pareto-v1`: verbatim supplied teammate Pareto baseline.
- `dev-base-v1`: behavior-preserving split and public integration API.
- `feature/a-search-runtime`: person A implementation and experiments.

See `docs/collaboration.md` for person B integration. Person B algorithms are not claimed as completed here.

## Official tests

Place original evaluator at `data/local/evaluator` and cases in `data/local/stage1`.
They are not bundled. Original hashes are recorded in result manifests.

```sh
chmod +x data/local/evaluator
python3 tools/run_experiments.py --solver final=build/solver --out results/MY-RUN --rounds 5 --warmup 1
python3 tools/analyze_results.py results/MY-RUN/runs.csv
```

## Research profiles

The public command line remains exactly two paths. Optional environment settings:
`TTC_STRATEGY=baseline|sweep|greedy|beam|anneal|multistart|portfolio`,
`TTC_CUT`, `TTC_ROUNDS`, `TTC_BEAM`, `TTC_RESTARTS`, `TTC_REGIONS`,
`TTC_SEED`, `TTC_SEARCH_MS`. Profile parameters are recorded under `configs/`.
`TTC_RESEARCH_MS` overrides the course input time limit for offline research only;
never treat those over-limit results as a compliant submission.
`TTC_COST_LOG`/`TTC_FRONTIER_LOG` enable diagnostics and affect runtime.

## Single-file source

```sh
python3 tools/export_submission.py --output dist/solver.cpp
g++ -O2 -std=c++17 dist/solver.cpp -o dist/solver
./dist/solver INPUT_PATH OUTPUT_PATH
```

Do not edit generated `dist/solver.cpp`; edit `src/` and `include/`.
The default is `sweep`: baseline synthesis plus convergent batched algebraic rewriting.
Final calibrated validation: all25 cases pass in all5 measured rounds (125/125),
all meet target delay, area/delay stable. Compared with the supplied Pareto baseline,
9 cases have smaller area and every case keeps the same delay; area sum drops
728930 to728872 (0.00796%, descriptive only). Runtime increases.

See [Stage1 report](docs/stage1-report.md), [handoff](docs/Stage1-Handoff.md),
[local method](docs/local-search.md), [runtime model](docs/runtime-model.md),
and [experiment register](docs/experiment-register.md).
The full research includes greedy, beam, annealing, multistart, growing cuts and
real bounded SAT/MILP; costly/failed runs are preserved. Person B's new algorithms
remain separate work. No global-optimal or hidden-case score claim is made.

## Download the complete delivery

[Person A Stage 1 release](https://github.com/xzx0716/Truth-Table-to-Circuit-Optimization/releases/tag/person-a-stage1-v2) contains the standalone source, compile README, report, handoff and checksums. Full research evidence is attached to the v1 release linked there. Both releases contain identical algorithm source. This does not submit to the course platform.
