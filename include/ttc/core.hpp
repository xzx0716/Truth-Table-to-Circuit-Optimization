#pragma once
// UFUG2106 Stage 1: reduced BDD synthesis with several gate mappings.
// Build: c++ -std=c++17 -O2 solver.cpp -o solver
// Run:   ./solver input_path output_path
#include <algorithm>
#include <array>
#include <cstdint>
#include <fstream>
#include <functional>
#include <iostream>
#include <limits>
#include <queue>
#include <stdexcept>
#include <string>
#include <tuple>
#include <unordered_map>
#include <utility>
#include <vector>


namespace ttc {

using Id = int;
using Score = long long;
enum GateType { AND2, OR2, NOT };
enum Mapping { Direct, ReplaceOr, ReplaceAnd, ProductMux };

struct Problem {
    int n, m;
    std::string table;
    std::array<int, 3> area, delay;
    int target;
    long long runtime_ms=0, ram_kb=0;
};

inline Problem read_problem(std::istream& in) {
    Problem p{};
    if (!(in >> p.n >> p.m) || p.n < 1 || p.m < 1 ||
        p.n >= std::numeric_limits<std::size_t>::digits) {
        throw std::runtime_error("invalid input or output count");
    }
    const std::size_t rows = std::size_t{1} << p.n;
    if (rows > p.table.max_size() / p.m)
        throw std::runtime_error("truth table too large");
    p.table.reserve(rows * p.m);
    std::string row;
    for (std::size_t i = 0; i < rows; ++i) {
        if (!(in >> row) || row.size() != static_cast<std::size_t>(p.m) ||
            row.find_first_not_of("01") != std::string::npos) {
            throw std::runtime_error("invalid truth table entry " + std::to_string(i));
        }
        p.table += row;
    }
    for (int i = 0; i < 3; ++i) {
        if (!(in >> p.area[i] >> p.delay[i]) || p.area[i] < 1 || p.delay[i] < 1)
            throw std::runtime_error("invalid gate cost");
    }
    if (!(in >> p.target) || p.target < 1)
        throw std::runtime_error("invalid target delay");
    for (int i = 0; i < 2; ++i) {
        in >> std::ws;
        if (in.eof()) return p;
        long long limit;
        if (!(in >> limit) || limit < 0)
            throw std::runtime_error("invalid runtime or RAM limit");
        (i == 0 ? p.runtime_ms : p.ram_kb) = limit;
    }
    in >> std::ws;
    if (!in.eof()) throw std::runtime_error("extra input after limits");
    return p;
}

struct Key {
    int type, a, b;
    bool operator==(const Key& other) const {
        return type == other.type && a == other.a && b == other.b;
    }
};

struct Hash {
    std::size_t operator()(const Key& key) const {
        std::uint64_t h = (std::uint64_t(key.type) + 11) * 0x9e3779b185ebca87ULL;
        h ^= (std::uint64_t(key.a) + 1) * 0xc2b2ae3d27d4eb4fULL;
        h ^= (std::uint64_t(key.b) + 1) * 0x165667b19e3779f9ULL;
        return static_cast<std::size_t>(h ^ (h >> 32));
    }
};

struct Gate {
    GateType type;
    Id a, b;
    Score arrival;
};
struct Netlist {
    std::vector<Gate> gates;  // compacted, ordered by the new ID
    std::vector<Id> outputs;
};

struct Candidate {
    Score area, delay;
    Netlist netlist;
};

// Feasible candidates are sorted by increasing area and strictly decreasing delay.
// Before the first feasible solution, keep the fallback with the shortest delay.
class Frontier {
public:
    explicit Frontier(Score target_delay) : target(target_delay) {}

    bool feasible() const { return !points.empty() && points.front().delay <= target; }
    const Candidate& smallest() const { return points.front(); }
    const Candidate& fastest() const { return points.back(); }

    bool may_improve(Score delay) const {
        return delay <= target || points.empty() || delay <= fastest().delay;
    }

    // Allocate storage for a candidate only if its metrics survive the comparison.
    Netlist* accept(Score area, Score delay, std::size_t gate_count) {
        if (!may_improve(delay)) return nullptr;
        if (!points.empty() && !feasible()) {
            const Candidate& fallback = points.front();
            if (std::make_tuple(delay, area, gate_count) >=
                std::make_tuple(fallback.delay, fallback.area, fallback.netlist.gates.size()))
                return nullptr;
            points.clear();
        }
        auto insertion = std::lower_bound(points.begin(), points.end(), area,
            [](const Candidate& c, Score a) { return c.area < a; });
        if (insertion != points.begin() && (insertion - 1)->delay <= delay) return nullptr;
        if (insertion != points.end() && insertion->area == area) {
            if (insertion->delay < delay ||
                (insertion->delay == delay && insertion->netlist.gates.size() <= gate_count))
                return nullptr;
        }
        // All points to the right already have at least this much area.
        auto end = insertion;
        while (end != points.end() && end->delay >= delay) ++end;
        insertion = points.erase(insertion, end);
        return &points.insert(insertion, Candidate{area, delay, {}})->netlist;
    }

    Netlist take_compromise() {
        if (points.size() == 1) return std::move(points.front().netlist);
        const Score ideal_area = smallest().area;
        const Score ideal_delay = fastest().delay;
        // Scale each loss by the best value seen for that metric. We minimize
        // the larger percentage loss. Zero-area or zero-delay optima are direct
        // connections in this positive-cost library and dominate every other point.
        auto penalty = [&](const Candidate& c) {
            long double a = static_cast<long double>(c.area - ideal_area) /
                            std::max<Score>(1, ideal_area);
            long double d = static_cast<long double>(c.delay - ideal_delay) /
                            std::max<Score>(1, ideal_delay);
            return std::make_tuple(std::max(a, d), a + d, c.area);
        };
        auto selected = std::min_element(points.begin(), points.end(),
            [&](const Candidate& a, const Candidate& b) { return penalty(a) < penalty(b); });
        return std::move(selected->netlist);
    }

private:
    Score target;
    std::vector<Candidate> points;
};

class Circuit {
public:
    const Problem& p;
    Mapping mapping;
    Id one = -1;
    std::vector<Gate> gates;

    Circuit(const Problem& problem, Mapping mode)
        : p(problem), mapping(mode), gates(p.n + 1, {NOT, 0, 0, 0}), neg(p.n + 1, -1) {}

    Id invert(Id a) {
        if (neg[a] >= 0) return neg[a];
        Id id = raw(NOT, a, 0);
        neg[a] = id;
        neg[id] = a;
        if (a == 0) one = id;
        return id;
    }
    Id conj(Id a, Id b) {
        if (a == 0 || b == 0 || neg[a] == b) return 0;
        if (a == one || a == b) return b;
        if (b == one) return a;
        if (mapping == ReplaceAnd) {
            Id na = invert(a), nb = invert(b);
            return invert(disj(na, nb));
        }
        return raw(AND2, a, b);
    }
    Id disj(Id a, Id b) {
        if (a == 0 || a == b) return b;
        if (b == 0) return a;
        if (a == one || b == one) return one;
        if (neg[a] == b) return invert(0);
        if (mapping == ReplaceOr) {
            Id na = invert(a), nb = invert(b);
            return invert(conj(na, nb));
        }
        return raw(OR2, a, b);
    }

    // Single pass in reverse topological order marks every gate that reaches an output.
    std::vector<char> reachable(const std::vector<Id>& roots) const {
        std::vector<char> used(gates.size());
        for (Id root : roots) used[root] = 1;
        for (Id i = static_cast<Id>(gates.size()) - 1; i > p.n; --i) {
            if (!used[i]) continue;
            const Gate& gate = gates[i];
            used[gate.a] = 1;
            if (gate.type != NOT) used[gate.b] = 1;
        }
        return used;
    }

    std::vector<Id> balance(Circuit& destination, const std::vector<Id>& roots) const {
        auto used = reachable(roots);
        std::vector<int> refs(gates.size()), memo(gates.size(), -1);
        for (Id id : roots) ++refs[id];
        for (Id i = p.n + 1; i < static_cast<Id>(gates.size()); ++i) {
            if (!used[i]) continue;
            ++refs[gates[i].a];
            if (gates[i].type != NOT) ++refs[gates[i].b];
        }

        std::function<Id(Id)> rewrite;
        // Flatten only private gates so shared subcircuits retain their fanout.
        std::function<void(Id, GateType, std::vector<Id>&)> flatten =
            [&](Id id, GateType type, std::vector<Id>& leaves) {
                if (id > p.n && gates[id].type == type && refs[id] == 1) {
                    flatten(gates[id].a, type, leaves);
                    flatten(gates[id].b, type, leaves);
                } else {
                    leaves.push_back(rewrite(id));
                }
            };
        rewrite = [&](Id id) -> Id {
            if (id <= p.n) return id;
            if (memo[id] >= 0) return memo[id];
            const auto& gate = gates[id];
            if (gate.type == NOT)
                return memo[id] = destination.invert(rewrite(gate.a));
            std::vector<Id> leaves;
            flatten(gate.a, gate.type, leaves);
            flatten(gate.b, gate.type, leaves);
            if (leaves.size() == 2) {
                return memo[id] = gate.type == AND2 ? destination.conj(leaves[0], leaves[1])
                                                    : destination.disj(leaves[0], leaves[1]);
            }
            using Entry = std::pair<Score, Id>;
            std::priority_queue<Entry, std::vector<Entry>, std::greater<Entry>> queue;
            for (Id x : leaves) queue.emplace(destination.gates[x].arrival, x);
            while (queue.size() > 1) {
                Id a = queue.top().second;
                queue.pop();
                Id b = queue.top().second;
                queue.pop();
                Id merged = gate.type == AND2 ? destination.conj(a, b) : destination.disj(a, b);
                queue.emplace(destination.gates[merged].arrival, merged);
            }
            return memo[id] = queue.top().second;
        };
        std::vector<Id> outputs;
        for (Id id : roots) outputs.push_back(rewrite(id));
        return outputs;
    }

    void consider(const std::vector<Id>& roots, Frontier& frontier) const {
        Score area = 0, delay = 0;
        std::size_t count = 0;
        for (Id id : roots) delay = std::max(delay, gates[id].arrival);
        if (!frontier.may_improve(delay)) return;
        auto used = reachable(roots);
        for (Id i = p.n + 1; i < static_cast<Id>(gates.size()); ++i) {
            if (used[i]) {
                area += p.area[gates[i].type];
                ++count;
            }
        }
        Netlist* accepted = frontier.accept(area, delay, count);
        if (!accepted) return;
        Netlist& best = *accepted;
        best.gates.reserve(count);
        std::vector<Id> new_id(gates.size());
        for (int i = 0; i <= p.n; ++i) new_id[i] = i;
        for (Id old = p.n + 1; old < static_cast<Id>(gates.size()); ++old) {
            if (!used[old]) continue;
            new_id[old] = p.n + 1 + static_cast<Id>(best.gates.size());
            const auto& g = gates[old];
            best.gates.push_back({g.type, new_id[g.a], new_id[g.b], g.arrival});
        }
        for (Id id : roots) best.outputs.push_back(new_id[id]);
    }

private:
    std::vector<Id> neg;
    std::unordered_map<Key, Id, Hash> cache;

    Id raw(GateType type, Id a, Id b) {
        if (type != NOT && b < a) std::swap(a, b);
        Key key{type, a, b};
        auto found = cache.find(key);
        if (found != cache.end()) return found->second;
        Id id = static_cast<Id>(gates.size());
        Score arrival = gates[a].arrival;
        if (type != NOT) arrival = std::max(arrival, gates[b].arrival);
        gates.push_back({type, a, b, arrival + p.delay[type]});
        neg.push_back(-1);
        cache.emplace(key, id);
        return id;
    }
};

struct BNode {
    int var;
    Id lo, hi;
};
class BDD {
public:
    std::vector<BNode> nodes{{-1, 0, 0}, {-1, 1, 1}};
    BDD(const Problem& problem, bool backwards) : p(problem), reverse(backwards) {
        three_input_roots.fill(-1);
    }

    Id build(int output, int level, std::size_t row) {
        if (level == p.n) return p.table[row * p.m + output] - '0';
        if (reverse || p.n - level != 3) return build_node(output, level, row);
        // A three-input subfunction has only eight bits. Reuse its BDD root
        // across every row block and output that contains the same pattern.
        unsigned pattern = 0;
        for (unsigned i = 0; i < 8; ++i)
            pattern |= static_cast<unsigned>(p.table[(row + i) * p.m + output] - '0') << i;
        Id& cached = three_input_roots[pattern];
        if (cached < 0) cached = build_node(output, level, row);
        return cached;
    }
    // Merge the two signals that arrive earliest so late signals travel through fewer gates.
    Id combine(const std::vector<Id>& inputs, Circuit& circuit, bool use_and) const {
        if (inputs.empty()) return use_and ? circuit.invert(0) : 0;
        if (inputs.size() == 1) return inputs.front();
        using Entry = std::pair<Score, Id>;
        std::priority_queue<Entry, std::vector<Entry>, std::greater<Entry>> ready;
        for (Id id : inputs) ready.emplace(circuit.gates[id].arrival, id);
        while (ready.size() > 1) {
            Id a = ready.top().second;
            ready.pop();
            Id b = ready.top().second;
            ready.pop();
            Id merged = use_and ? circuit.conj(a, b) : circuit.disj(a, b);
            ready.emplace(circuit.gates[merged].arrival, merged);
        }
        return ready.top().second;
    }

    Id map_top_block(Id root, Circuit& circuit, std::vector<Id>& memo, int width,
                     std::unordered_map<unsigned, Id>& selector_cache) const {
        if (root < 2) return map(root, circuit, memo);
        width = std::min(width, p.n);
        if (width == 0) return map(root, circuit, memo);

        // For each assignment to the first few variables, collect the selector
        // identifying it under the BDD node that remains. Skipped BDD levels
        // do not need a literal in the selector.
        std::unordered_map<Id, std::vector<Id>> selectors;
        std::vector<Id> literals;
        literals.reserve(width);
        for (int assignment = 0; assignment < (1 << width); ++assignment) {
            Id node = root;
            unsigned signature = 0;
            literals.clear();
            for (int level = 0; level < width && node >= 2; ++level) {
                int variable = reverse ? p.n - 1 - level : level;
                if (nodes[node].var != variable) continue;
                bool high = ((assignment >> level) & 1) != 0;
                Id x = variable + 1;
                // Two bits per level distinguish absent, low and high literals.
                signature |= (high ? 2u : 1u) << (2 * level);
                literals.push_back(high ? x : circuit.invert(x));
                node = high ? nodes[node].hi : nodes[node].lo;
            }
            if (node == 0) continue;
            auto [where, fresh] = selector_cache.try_emplace(signature, 0);
            if (fresh) where->second = combine(literals, circuit, true);
            selectors[node].push_back(where->second);
        }

        std::vector<Id> terms;
        for (auto& entry : selectors) {
            auto& group = entry.second;
            std::sort(group.begin(), group.end());
            group.erase(std::unique(group.begin(), group.end()), group.end());
            Id select = combine(group, circuit, false);
            Id residual = map(entry.first, circuit, memo);
            terms.push_back(circuit.conj(select, residual));
        }
        std::sort(terms.begin(), terms.end());
        terms.erase(std::unique(terms.begin(), terms.end()), terms.end());
        return combine(terms, circuit, false);
    }
    Id map(Id id, Circuit& c, std::vector<Id>& memo) const {
        if (memo[id] >= 0) return memo[id];
        if (id == 0) return memo[id] = 0;
        if (id == 1) return memo[id] = c.invert(0);
        const auto& node = nodes[id];
        Id x = node.var + 1;
        if (node.lo == 0 && node.hi == 1) return memo[id] = x;
        if (node.lo == 1 && node.hi == 0) return memo[id] = c.invert(x);
        if (node.lo == 0) return memo[id] = c.conj(x, map(node.hi, c, memo));
        if (node.hi == 0) {
            Id nx = c.invert(x);
            return memo[id] = c.conj(nx, map(node.lo, c, memo));
        }
        if (node.lo == 1) {
            Id nx = c.invert(x);
            return memo[id] = c.disj(nx, map(node.hi, c, memo));
        }
        if (node.hi == 1) return memo[id] = c.disj(x, map(node.lo, c, memo));
        Id a = map(node.lo, c, memo), b = map(node.hi, c, memo);
        if (c.mapping == ProductMux) {
            Id lo = c.disj(x, a), hi = c.disj(c.invert(x), b);
            return memo[id] = c.conj(lo, hi);
        }
        Id lo = c.conj(c.invert(x), a), hi = c.conj(x, b);
        return memo[id] = c.disj(lo, hi);
    }

private:
    Id build_node(int output, int level, std::size_t row) {
        int var = reverse ? p.n - level - 1 : level;
        Id lo = build(output, level + 1, row);
        Id hi = build(output, level + 1, row | (std::size_t{1} << (p.n - 1 - var)));
        if (lo == hi) return lo;
        Key key{var, lo, hi};
        auto found = unique.find(key);
        if (found != unique.end()) return found->second;
        Id id = static_cast<Id>(nodes.size());
        nodes.push_back({var, lo, hi});
        unique.emplace(key, id);
        return id;
    }

    std::array<Id, 256> three_input_roots;
    const Problem& p;
    bool reverse;
    std::unordered_map<Key, Id, Hash> unique;
};

// Try implementing each wire in either polarity. De Morgan's law lets a gate
// switch type when both inputs and its output are complemented.
inline void remap_area(const Problem& p, const Netlist& best, Frontier& frontier, Score timing_budget) {
    const Id first = p.n + 1;
    const Id size = first + static_cast<Id>(best.gates.size());
    if (size == first) return;
    const Score infinity = std::numeric_limits<Score>::max() / 4;
    std::vector<Score> required(size, infinity);
    std::vector<int> references(size);
    for (Id output : best.outputs) {
        required[output] = timing_budget;
        ++references[output];
    }
    for (Id i = size - 1; i >= first; --i) {
        const Gate& gate = best.gates[i - first];
        const Score input_time = required[i] - p.delay[gate.type];
        required[gate.a] = std::min(required[gate.a], input_time);
        ++references[gate.a];
        if (gate.type != NOT) {
            required[gate.b] = std::min(required[gate.b], input_time);
            ++references[gate.b];
        }
    }

    // Estimate how much of a shared gate's cost belongs to each consumer.
    // The finished candidate is always ranked again using its exact gate area.
    struct Option {
        double area;
        Score delay;
        bool invert;
    };
    struct Plan {
        std::array<Option, 2> direct, selected;
    };
    std::vector<Plan> plans(size);
    for (Id i = 0; i < first; ++i) {
        plans[i].selected[0] = {0, 0, false};
        plans[i].selected[1] = {static_cast<double>(p.area[NOT]), p.delay[NOT], true};
    }
    for (Id i = first; i < size; ++i) {
        const Gate& gate = best.gates[i - first];
        if (gate.type == NOT) {
            plans[i].selected[0] = plans[gate.a].selected[1];
            plans[i].selected[1] = plans[gate.a].selected[0];
            continue;
        }
        for (int phase = 0; phase < 2; ++phase) {
            const GateType type = phase ? (gate.type == AND2 ? OR2 : AND2) : gate.type;
            const Option& a = plans[gate.a].selected[phase];
            const Option& b = plans[gate.b].selected[phase];
            plans[i].direct[phase] = {
                p.area[type] + a.area / references[gate.a] + b.area / references[gate.b],
                std::max(a.delay, b.delay) + p.delay[type], false
            };
        }
        for (int phase = 0; phase < 2; ++phase) {
            const Option direct = plans[i].direct[phase];
            const Option opposite = plans[i].direct[1 - phase];
            const Option inverted{opposite.area + p.area[NOT],
                                  opposite.delay + p.delay[NOT], true};
            const Score budget = required[i] + (phase ? p.delay[NOT] : 0);
            auto quality = [budget](const Option& option) {
                return std::make_tuple(std::max<Score>(0, option.delay - budget),
                                       option.area, option.delay);
            };
            plans[i].selected[phase] = quality(inverted) < quality(direct) ? inverted : direct;
        }
    }

    Circuit circuit(p, Direct);
    std::vector<std::array<Id, 2>> memo(size, {-1, -1}), direct_ids(size, {-1, -1});
    std::function<Id(Id, int)> emit = [&](Id i, int phase) -> Id {
        Id& result = memo[i][phase];
        if (result >= 0) return result;
        if (i < first) return result = phase ? circuit.invert(i) : i;
        const Gate& gate = best.gates[i - first];
        if (gate.type == NOT) return result = emit(gate.a, 1 - phase);
        bool invert = plans[i].selected[phase].invert;
        int child_phase = invert ? 1 - phase : phase;
        Id& direct = direct_ids[i][child_phase];
        if (direct < 0) {
            Id a = emit(gate.a, child_phase);
            Id b = emit(gate.b, child_phase);
            bool use_and = (gate.type == AND2) != (child_phase != 0);
            direct = use_and ? circuit.conj(a, b) : circuit.disj(a, b);
        }
        return result = invert ? circuit.invert(direct) : direct;
    };
    std::vector<Id> outputs;
    for (Id output : best.outputs) outputs.push_back(emit(output, 0));
    circuit.consider(outputs, frontier);
}

inline Netlist synthesize(const Problem& p, const std::function<bool()>& stop = {},
    const std::function<void(Netlist,const std::string&)>& collect = {}) {
    Frontier frontier(p.target);
    BDD bdd(p, false);
    std::vector<Id> roots;
    for (int j = 0; j < p.m; ++j) roots.push_back(bdd.build(j, 0, 0));

    bool has_seed=false;
    auto record=[&](const Circuit& circuit,const std::vector<Id>& outputs,const std::string& label){
        if(collect){Frontier temporary(std::numeric_limits<Score>::max());
            circuit.consider(outputs,temporary);collect(temporary.take_compromise(),label);}
    };
    auto consider_widths = [&](Mapping mapping, const std::vector<int>& widths) {
        Circuit circuit(p, mapping);
        std::vector<Id> memo(bdd.nodes.size(), -1);
        // Every output in this circuit can reuse identical selection conditions.
        std::unordered_map<unsigned, Id> selector_cache;
        for (int width : widths) {
            if (has_seed && stop && stop()) break;
            std::vector<Id> outputs;
            for (Id root : roots) outputs.push_back(bdd.map_top_block(root, circuit, memo, width, selector_cache));
            record(circuit,outputs,"base-raw");
            circuit.consider(outputs, frontier);
            has_seed=true;
            if (stop && stop()) break;
            Circuit balanced(p, Direct);
            auto balanced_outputs = circuit.balance(balanced, outputs);
            record(balanced,balanced_outputs,"base-balanced");
            balanced.consider(balanced_outputs, frontier);
        }
    };

    // The first pass preserves the timing-oriented incumbent.
    bool replace_or_first = p.delay[AND2] + 2LL * p.delay[NOT] < p.delay[OR2];
    Mapping first = replace_or_first ? ReplaceOr : Direct;
    consider_widths(first, {4});
    if (stop && stop()) return frontier.take_compromise();
    if (!frontier.feasible()) consider_widths(replace_or_first ? Direct : ReplaceOr, {4});

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
    if (wide > 2 && frontier.smallest().netlist.gates.size() < 1000) widths.push_back(2);
    consider_widths(area_mapping, widths);
    if (stop && stop()) return frontier.take_compromise();
    // Keep the fastest seed alive as new entries can replace it in the frontier.
    Candidate fast_seed = frontier.fastest();
    remap_area(p, frontier.smallest().netlist, frontier, p.target);
    if ((!stop || !stop()) && frontier.feasible() && frontier.smallest().delay > fast_seed.delay) {
        // Try recovering area at the current speed and halfway to the area endpoint.
        const Score midpoint = fast_seed.delay + (frontier.smallest().delay - fast_seed.delay) / 2;
        remap_area(p, fast_seed.netlist, frontier, fast_seed.delay);
        if ((!stop || !stop()) && midpoint > fast_seed.delay) remap_area(p, fast_seed.netlist, frontier, midpoint);
    }
    return frontier.take_compromise();
}

inline void write_netlist(std::ostream& out, int n, const Netlist& netlist) {
    const char* names[]{"AND2", "OR2", "NOT"};
    Id id = n + 1;
    for (const auto& g : netlist.gates) {
        out << id++ << ' ' << names[g.type] << ' ' << g.a;
        if (g.type != NOT) out << ' ' << g.b;
        out << '\n';
    }
    for (std::size_t j = 0; j < netlist.outputs.size(); ++j) {
        if (j) out << ' ';
        out << netlist.outputs[j];
    }
    out << '\n';
}

}
