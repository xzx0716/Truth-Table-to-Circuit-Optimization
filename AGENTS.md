# Collaboration

Production code lives in src/ and include/ttc/. Never edit generated dist sources.
Do not overwrite baseline tags or alter old experiment results.
Keep the solver single threaded and its two-path command line unchanged.
Do not use case names or cached public answers.
A owns budget, local rewriting, research exact tools, experiments and integration.
B owns mapping, sharing and decomposition; integrate through optimization_api.hpp.
Official inputs/evaluator stay in data/local (ignored); record hashes.
All experiment reports must bind source hash/commit and configuration.
