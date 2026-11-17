# A/B integration contract

Development base: dev-base-v1. A implementation: feature/a-search-runtime.
Public API is include/ttc/optimization_api.hpp.

Every optimizer receives Problem, an independent Netlist seed, RuntimeBudget&, and CandidateSink.
The deadline is shared and includes baseline construction/read/write. Calls must be interruptible.
CandidateSink receives a complete independent netlist by value; never keep Frontier references.
A owns runtime, local rewrite, main, tooling and integration.
B adds mapping/sharing/decomposition modules and tests, without replacing A's main.
The A delivery does not claim that B's planned algorithms have been implemented.

Official inputs/evaluator remain in data/local. Full diagnostics in artifacts.
Experimental profiles are recorded in configs/strategies.json; use explicit TTC_* environment
settings only for reproducible research; final default is selected after validation.
