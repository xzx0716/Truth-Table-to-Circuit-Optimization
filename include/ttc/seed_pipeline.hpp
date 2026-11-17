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

// An interrupted GitHub baseline still provides a complete incumbent once
// synthesize has emitted its first valid circuit. Keep it only if the common
// post-pass does not finish; independent single-seed trials still fail there.
inline SeedTrial run_seed_trial(const Problem& p, const std::string& profile, RuntimeBudget& budget,
                                Netlist* fallback = nullptr) {
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
    if (!trial.seed_complete) {
        if (fallback) *fallback=std::move(seed);
        return trial;
    }

    seed = normalize(p, seed);
    Netlist rewritten = try_seed_sweep(p, seed, budget);
    if (rewritten.outputs.empty()) {
        if (fallback) *fallback=std::move(seed);
        return trial;
    }

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

inline std::vector<std::string> portfolio_profiles(const std::string& csv) {
    std::vector<std::string> profiles{"github"};
    std::size_t begin=0;
    // Explicitly visit the empty last field of a trailing comma.
    for (;;) {
        const auto end=csv.find(',',begin);
        const auto item=csv.substr(begin,end==std::string::npos ? end : end-begin);
        if (item!="github" && item!="historical-adaptive" &&
            seed_detail::find_seed(item)==std::end(seed_detail::seeds))
            throw std::invalid_argument("unknown portfolio seed: '"+item+"'");
        if (std::find(profiles.begin(),profiles.end(),item)==profiles.end()) profiles.push_back(item);
        if (end==std::string::npos) return profiles;
        begin=end+1;
    }
}

// Each successful profile emits the same selected result as its independent
// run. The caller keeps the pure area-delay archive and chooses its compromise.
inline std::size_t run_seed_portfolio(const Problem& p, const std::vector<std::string>& profiles,
                                      RuntimeBudget& budget, const CandidateSink& sink) {
    std::size_t completed=0;
    for (const auto& profile:profiles) {
        if (profile!="github" && budget.should_stop()) break;
        Netlist fallback;
        SeedTrial trial;
        try {
            trial=run_seed_trial(p,profile,budget,profile=="github" ? &fallback : nullptr);
        } catch (const SeedBudgetExpired&) {
            if (profile=="github") throw;
            break;
        }
        if (!trial.post_complete) {
            if (profile=="github") {
                if (fallback.outputs.empty()) throw std::logic_error("GitHub baseline emitted no circuit");
                sink(std::move(fallback),"github-fallback");
            }
            break;
        }
        sink(std::move(trial.selected),profile);
        ++completed;
    }
    return completed;
}
} // namespace ttc
