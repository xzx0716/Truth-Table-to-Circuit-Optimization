#pragma once
#include "ttc/seed_constructors.hpp"
#include "ttc/optimization_api.hpp"

namespace ttc {
// Run the production algebraic sweep once on a normalized seed. An empty output
// list means the resource budget prevented a complete pass.
Netlist try_seed_sweep(const Problem&, const Netlist&, RuntimeBudget&);

struct SeedTrial {
    Metrics initial;
    Netlist selected;
    bool seed_complete = false;
    bool post_complete = false;
};

inline SeedTrial run_seed_trial(const Problem& p, const std::string& profile, RuntimeBudget& budget) {
    bool interrupted = false;
    auto stop = [&]() {
        interrupted = interrupted || budget.should_stop();
        return interrupted;
    };
    Netlist seed = profile == "github" ? synthesize(p, stop) : construct_seed(p, profile, budget);
    SeedTrial trial;
    if (seed.outputs.empty()) return trial;
    trial.initial = measure(p, seed);
    trial.seed_complete = !stop();
    if (!trial.seed_complete) return trial;

    seed = normalize(p, seed);
    Netlist rewritten = try_seed_sweep(p, seed, budget);
    if (rewritten.outputs.empty()) return trial;

    // Use the same feasible-first compromise as the course solver for both
    // the incoming circuit and the candidate produced by this complete pass.
    Frontier frontier(p.target);
    for (Netlist* candidate : {&seed, &rewritten}) {
        auto cost = measure(p, *candidate);
        if (Netlist* kept = frontier.accept(cost.area, cost.delay, candidate->gates.size()))
            *kept = std::move(*candidate);
    }
    trial.selected = frontier.take_compromise();
    trial.post_complete = true;
    return trial;
}
} // namespace ttc
