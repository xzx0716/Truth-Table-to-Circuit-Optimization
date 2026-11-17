# Bounded exact synthesis research

These are working SAT and MILP experiments, not a final whole-case synthesis backend. Both implement the permitted AND2/OR2/NOT gate library, arbitrary positive area/delay costs, a zero constant, previous-position connections, all input rows, and one output.

## Reproduce

Use Python 3.10+ on Linux/WSL:

```sh
python3 -m pip install -r research/exact/requirements.txt
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 tests/test_exact.py
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 research/exact/run_study.py --seconds 1.0
python3 research/exact/generate_templates.py
python3 tools/generate_template_header.py
python3 research/exact/synthesize.py sat INPUT --max-gates 6 --seconds 10 --delay 20 --output local.net --report sat.json
python3 research/exact/synthesize.py milp INPUT --max-gates 6 --seconds 10 --delay 20 --output local.net --report milp.json
```

`INPUT` has the assignment format but exactly one output. A missing `--delay` leaves delay unconstrained. Reproduction of the public local-cut study also needs baseline netlists under `artifacts/baseline/circuits` and official cases under `data/local/stage1`. Those materials are not embedded in the library.

The WSL machine initially had SciPy 1.8 without MILP and could not reach PyPI. Linux wheels were downloaded through Windows Python, then installed offline in WSL: python-sat 1.8.dev19, SciPy 1.15.3, NumPy 2.2.6. Dependencies are research-only. The final C++ solver does not require them.

## Models and proof scope

SAT: one-hot choices of gate operation and fanins; Tseitin truth constraints for every input row; one-hot output choice. A reachable-area-budget automaton enforces the weighted area limit. Boolean required-time implications recursively propagate the selected output delay bound. The solver tightens area until UNSAT and visits every slot count from zero through max_gates. A native interruption timer distinguishes timeout from UNSAT.

MILP: the same truth/choice CNF is translated to exact binary linear inequalities. Conditional arrival constraints use a big-M derived from the acyclic slot bound, not an arbitrary large constant. The objective is selected gate area. SciPy/HiGHS is requested to use one solver thread; SciPy passes this option through and may print an informational warning.

Every decoded circuit is independently simulated and its live area/delay recomputed. Unused positions are pruned. All exact claims concern **minimum area**, with delay as a feasibility constraint; delay tie-breaking is not proven optimal. `BOUNDED_OPTIMAL` means proven among all circuits with at most the stated slot bound and the stated delay bound. It is not a whole-project global optimum. `BOUNDED_UNSAT` means no circuit in that bounded space. `FEASIBLE_NOT_PROVEN` retains an incumbent on timeout. `TIMEOUT_UNKNOWN` is not an infeasibility proof. Model construction and imports contribute to reported total elapsed time, so a nominal solver timeout is not a hard wall-time limit on the script. The research implementation is single-output; multi-output exact synthesis is not implemented.

## Executed results

`tests/test_exact.py` passed for both backends: constants, wires, AND, direct OR, cheaper De Morgan OR, factored three-input function, infeasible delay, and all sixteen two-input functions under asymmetric costs. The independent backends agree on minimum bounded area.

`results/study.json` contains 74 retained runs:

| Study | SAT | MILP |
|---|---|---|
| Parity n=2..5; max slots=2,4,6 | 2 bounded optima; 10 bounded UNSAT | 4 bounded UNSAT; 7 timeout/unknown; 1 incumbent without proof |
| One depth-two local function from each of 25 public baseline netlists | 25 bounded optima | 20 bounded optima; 5 incumbents without proof |

The public-cut study treats all boundary signals as independent inputs and uses unit zero arrival at the boundary. It proves correctness for all boundary assignments. It does not account for real boundary arrival times, sharing outside the cut, or demonstrate a full-case A/D improvement. It is evidence that exact local replacement is feasible, not a final evaluator result.

`generic_templates.json` is a public-case-independent library: all 16 two-input functions, four delay budgets, unit gate costs, at most four gate positions (64 queries: 54 bounded optima and 10 bounded UNSAT). These are candidate structures for later cost-aware mapping, not a universally complete library for arbitrary costs.

## Conclusions and next steps

SAT completed more bounded proofs than this MILP model under the one-second budget. MILP timeout results are preserved rather than discarded. Enlarge difficult n/gate bounds, try incremental SAT, improve MILP symmetry breaking and warm starts, and compare under repeated isolated timing. For production, integrate generic templates or a strict-budget local backend; do not call an external solver service or cache public-case answers. Current exact tools remain offline research; the generic library is exported to `include/ttc/generated_templates.hpp` by `tools/generate_template_header.py` and integrated by the local-rewrite module. The header contains 33 distinct candidate networks covering all 16 functions (18 exact-library structures plus De Morgan variants), with LSB boundary-variable signatures verified independently. Runtime lookup needs no Python or solver dependency.

All recorded source/input hashes and versions are in `results/manifest.json` and each study record. Historical timing was taken while other development work could be active and is an exploratory curve, not a stable solver speed ranking.
