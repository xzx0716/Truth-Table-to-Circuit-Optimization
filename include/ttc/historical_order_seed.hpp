#pragma once
#include "ttc/optimization_api.hpp"

namespace ttc {
// The portfolio catches deadline exhaustion only. Other construction errors
// must propagate rather than silently dropping a candidate.
class SeedBudgetExpired : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};
namespace historical_order {

// The GitHub BDD has a three-input cache on its forward path. For a reverse
// order the three remaining row bits have a stride of 2^level. Keep a cache
// for those patterns while reusing BDD's existing leaf builder and mapper.
// Only this outer table inserts nodes above the last three levels.
class ReverseBuilder {
public:
    ReverseBuilder(const Problem& p, BDD& graph, RuntimeBudget& budget)
        : p(p), graph(graph), budget(budget) { patterns.fill(-1); }

    Id build(int output, int level, std::size_t row) {
        if ((++calls & 1023u)==0 && budget.should_stop())
            throw SeedBudgetExpired("historical seed exceeded budget");
        if (p.n - level < 3) return graph.build(output,level,row);
        const auto stride=std::size_t{1}<<level;
        if (p.n - level == 3) {
            unsigned pattern=0;
            for (unsigned i=0; i<8; ++i)
                pattern |= unsigned(p.table[(row+i*stride)*p.m+output]-'0')<<i;
            auto& id=patterns[pattern];
            if (id<0) id=graph.build(output,level,row);
            return id;
        }
        const Id lo=build(output,level+1,row);
        const Id hi=build(output,level+1,row+stride);
        if (lo==hi) return lo;
        const int var=p.n-1-level;
        const auto found=upper.emplace(Key{var,lo,hi},static_cast<Id>(graph.nodes.size()));
        if (found.second) graph.nodes.push_back({var,lo,hi});
        return found.first->second;
    }
private:
    const Problem& p;
    BDD& graph;
    RuntimeBudget& budget;
    unsigned calls=0;
    std::array<Id,256> patterns;
    std::unordered_map<Key,Id,Hash> upper;
};

// Build and discard one order at a time. Both passes share only the frontier.
inline std::size_t consider_order(const Problem& p, Frontier& frontier, RuntimeBudget& budget, bool reverse,
                           std::size_t node_limit = std::numeric_limits<std::size_t>::max()) {
    BDD bdd(p, reverse);
    ReverseBuilder reversed(p,bdd,budget);
    auto check=[&] {
        if (budget.should_stop()) throw SeedBudgetExpired("historical seed exceeded budget");
    };
    std::vector<Id> roots;
    for (int j = 0; j < p.m; ++j) {
        check();
        roots.push_back(reverse ? reversed.build(j,0,0) : bdd.build(j,0,0));
        // The graph can only grow as outputs are added. Skip mapping when the
        // competing order has already exhausted its node allowance.
        if (bdd.nodes.size() > node_limit) return bdd.nodes.size();
    }

    auto consider_widths = [&](Mapping mapping, const std::vector<int>& widths) {
        Circuit circuit(p, mapping);
        std::vector<Id> memo(bdd.nodes.size(), -1);
        // Every output in this circuit can reuse identical selection conditions.
        std::unordered_map<unsigned, Id> selector_cache;
        for (int width : widths) {
            std::vector<Id> outputs;
            for (Id root : roots) {
                check();
                outputs.push_back(bdd.map_top_block(root,circuit,memo,width,selector_cache));
            }
            circuit.consider(outputs, frontier);
            check();
            Circuit balanced(p, Direct);
            auto balanced_outputs = circuit.balance(balanced, outputs);
            balanced.consider(balanced_outputs, frontier);
        }
    };

    // The first pass preserves the timing-oriented incumbent.
    bool replace_or_first = p.delay[AND2] + 2LL * p.delay[NOT] < p.delay[OR2];
    Mapping first = replace_or_first ? ReplaceOr : Direct;
    consider_widths(first, {4});
    if (!reverse && !frontier.feasible()) consider_widths(replace_or_first ? Direct : ReplaceOr, {4});

    // De Morgan replacement is a promising area candidate when its individual
    // gate implementation is cheaper, before any sharing of inverted wires.
    Mapping area_mapping = Direct;
    if (p.area[OR2] > p.area[AND2] + 3LL * p.area[NOT]) area_mapping = ReplaceOr;
    else if (p.area[AND2] > p.area[OR2] + 3LL * p.area[NOT]) area_mapping = ReplaceAnd;
    else if (p.area[AND2] == p.area[OR2]) area_mapping = ProductMux;

    // A width-k selector has up to 2^k terms per output. Limit selector
    // expansion in relation to the size of the current gate graph.
    int wide = std::min(8, p.n);
    while (wide > 2 && (std::size_t{1} << wide) * roots.size() > frontier.smallest().netlist.gates.size())
        --wide;
    std::vector<int> widths{wide};
    // Small circuits can often share more gates with just two selector inputs.
    if (!reverse && wide > 2 && frontier.smallest().netlist.gates.size() < 1000)
        widths.push_back(2);
    if (!reverse || wide != 4 || first != area_mapping)
        consider_widths(area_mapping, widths);
    return bdd.nodes.size();
}

// Decision thresholds and the reverse-order node allowance are frozen at
// the published variable-order version, policy 2.
inline bool try_reverse(const Problem& p, const Frontier& front, std::size_t forward_nodes) {
    if (p.n<2 || front.smallest().netlist.gates.empty()) return false;
    const std::size_t cells=p.table.size();
    auto ceil_div=[](std::size_t n,std::size_t d){return n/d+(n%d!=0);};
    if (p.runtime_ms>0 && ceil_div(cells,8192)>static_cast<unsigned long long>(p.runtime_ms))
        return false;
    if (p.ram_kb>0 && ceil_div(cells,1024)>static_cast<unsigned long long>(p.ram_kb)/4)
        return false;
    return !(front.feasible() && cells>65536 && forward_nodes<ceil_div(cells,256));
}
inline Netlist construct(const Problem& p, RuntimeBudget& budget) {
    Frontier frontier(p.target);
    const auto count=consider_order(p,frontier,budget,false);
    if (try_reverse(p,frontier,count)) {
        const auto limit=frontier.feasible() ? count+std::max<std::size_t>(16,count/8)
                                             : std::numeric_limits<std::size_t>::max();
        consider_order(p,frontier,budget,true,limit);
    }
    if (budget.should_stop()) throw SeedBudgetExpired("historical seed exceeded budget");
    Candidate fastest=frontier.fastest();
    remap_area(p,frontier.smallest().netlist,frontier,p.target);
    if (frontier.feasible() && frontier.smallest().delay>fastest.delay) {
        const auto middle=fastest.delay+(frontier.smallest().delay-fastest.delay)/2;
        remap_area(p,fastest.netlist,frontier,fastest.delay);
        if (middle>fastest.delay) remap_area(p,fastest.netlist,frontier,middle);
    }
    if (budget.should_stop()) throw SeedBudgetExpired("historical seed exceeded budget");
    return frontier.take_compromise();
}
} // namespace historical_order
} // namespace ttc
