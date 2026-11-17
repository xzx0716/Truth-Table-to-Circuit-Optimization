#pragma once
#include "ttc/optimization_api.hpp"
#include "ttc/historical_order_seed.hpp"
#include <numeric>
#include <random>


namespace ttc {
namespace seed_detail {

// Adapted from the earlier grouping experiment. Graph node levels belong to
// a particular permutation: never reuse its pattern cache in another order.
enum class Grouping { single, top, recursive, adaptive };


class Poll {
public:
    explicit Poll(RuntimeBudget& budget) : budget_(budget) { check(); }
    void tick() { if ((++steps_ & 1023u) == 0) check(); }
    void check() const { if (budget_.should_stop()) throw SeedBudgetExpired("seed construction exceeded budget"); }
private:
    RuntimeBudget& budget_;
    unsigned steps_ = 0;
};

// IDs 0 and 1 are terminal functions; each nonterminal is canonical in one order.
class OrderedGraph {
public:
    OrderedGraph(const Problem& problem, const std::vector<int>& order, Poll& poll)
        : p(problem), variables(order), clock(poll) {
        for (int var : order) masks.push_back(std::size_t{1} << (p.n - 1 - var));
        if (p.n >= 3) {
            for (unsigned i=0; i<8; ++i)
                for (int k=0; k<3; ++k)
                    if (i & (4u >> k)) tail_offset[i] |= masks[p.n - 3 + k];
        }
        patterns.fill(-1);
        nodes = {{p.n,0,0}, {p.n,1,1}};
    }

    Id root(int output) { return build(0, 0, output); }
    const Problem& p;
    const std::vector<int>& variables;
    Poll& clock;
    std::vector<BNode> nodes; // var is the order level, not the primary input ID

private:
    std::vector<std::size_t> masks;
    std::array<std::size_t,8> tail_offset{};
    std::array<Id,256> patterns;
    std::unordered_map<Key,Id,Hash> unique;

    Id node(int level, Id lo, Id hi) {
        if (lo == hi) return lo;
        Key k{level,lo,hi};
        auto added = unique.emplace(k,static_cast<Id>(nodes.size()));
        if (added.second) nodes.push_back({level,lo,hi});
        return added.first->second;
    }

    Id build(int level, std::size_t row, int output) {
        clock.tick();
        if (level == p.n) return p.table[row * p.m + output] - '0';
        if (level + 3 == p.n) {
            unsigned bits = 0;
            for (int i=0; i<8; ++i)
                bits |= unsigned(p.table[(row | tail_offset[i])*p.m + output] - '0') << i;
            Id& id = patterns[bits];
            if (id >= 0) return id;
            std::array<Id,8> partial{};
            for (int i=0; i<8; ++i) partial[i]=(bits >> i)&1;
            for (int count=4, depth=level+2; count; count/=2, --depth)
                for (int i=0; i<count; ++i)
                    partial[i] = node(depth,partial[2*i],partial[2*i+1]);
            return id=partial[0];
        }
        Id lo=build(level+1,row,output);
        Id hi=build(level+1,row|masks[level],output);
        return node(level,lo,hi);
    }
};

class GroupMapper {
public:
    GroupMapper(OrderedGraph& graph, Grouping grouping, int width, bool pos)
        : g(graph), mode(grouping), product_of_sums(pos), max_width(std::clamp(width,1,g.p.n)),
          unary(g.nodes.size(),-1), blocked(g.nodes.size(),-1), circuit(g.p,Direct) {}
    Netlist construct(const std::vector<Id>& roots) {
        std::vector<Id> outputs;
        for (Id root : roots) outputs.push_back(map(root,true));
        g.clock.check();
        Frontier first(std::numeric_limits<Score>::max());
        circuit.consider(outputs,first);
        g.clock.check();
        return first.take_compromise();
    }

private:
    OrderedGraph& g;
    Grouping mode;
    bool product_of_sums;
    int max_width;
    std::vector<Id> unary, blocked;
    Circuit circuit;

    Id mux(Id x, Id lo, Id hi) {
        if (lo==hi) return lo;
        if (lo==0) return circuit.conj(x,hi);
        if (hi==0) return circuit.conj(circuit.invert(x),lo);
        if (lo==circuit.one) return circuit.disj(circuit.invert(x),hi);
        if (hi==circuit.one) return circuit.disj(x,lo);
        if (product_of_sums) {
            Id left=circuit.disj(x,lo), right=circuit.disj(circuit.invert(x),hi);
            return circuit.conj(left,right);
        }
        Id left=circuit.conj(circuit.invert(x),lo), right=circuit.conj(x,hi);
        return circuit.disj(left,right);
    }

    Id join(const std::vector<Id>& terms, bool conjunction) {
        if (terms.empty()) return conjunction ? circuit.invert(0) : 0;
        using Item=std::pair<Score,Id>;
        std::priority_queue<Item,std::vector<Item>,std::greater<Item>> ready;
        for (Id t : terms) { g.clock.tick(); ready.emplace(circuit.gates[t].arrival,t); }
        while (ready.size()>1) {
            g.clock.tick();
            Id a=ready.top().second; ready.pop();
            Id b=ready.top().second; ready.pop();
            Id c=conjunction?circuit.conj(a,b):circuit.disj(a,b);
            ready.emplace(circuit.gates[c].arrival,c);
        }
        return ready.top().second;
    }

    // Each root-to-boundary path defines a disjoint cube; skipped variables
    // never enter the cube. Combine selectors reaching the same residual.
    void cubes(Id id, int end, std::vector<Id>& path, std::map<Id,std::vector<Id>>& groups) {
        g.clock.tick();
        if (!id) return;
        const BNode& b=g.nodes[id];
        if (id==1 || b.var>=end) { groups[id].push_back(join(path,true)); return; }
        Id x=g.variables[b.var]+1;
        path.push_back(circuit.invert(x));
        cubes(b.lo,end,path,groups);
        path.back()=x;
        cubes(b.hi,end,path,groups);
        path.pop_back();
    }

    // Compare real residual multiplicities before constructing any selectors.
    // The estimate charges select/combine gates and the longest selector
    // arrival (including complemented literals), per consumed BDD level.
    int select_width(Id root, int cap) {
        std::map<Id,double> frontier{{root,1.0}};
        int best=1;
        double best_score=std::numeric_limits<double>::infinity();
        for (int w=1; w<=cap; ++w) {
            std::map<Id,double> next;
            int level=g.nodes[root].var+w-1;
            for (auto [id,paths]:frontier) {
                g.clock.tick();
                if (!id) continue;
                const auto& bn=g.nodes[id];
                if (id==1 || bn.var>level) next[id]+=paths;
                else { if (bn.lo) next[bn.lo]+=paths; if (bn.hi) next[bn.hi]+=paths; }
            }
            double occurrences=0,max_group=1;
            for (auto [id,count]:next) {
                (void)id; occurrences+=count; max_group=std::max(max_group,count);
            }
            // The same residual is evaluated once per group. Larger fan-in is
            // combined by the arrival-ordered tree used by join().
            const double area=occurrences*g.p.area[AND2]+next.size()*g.p.area[OR2];
            const double delay=g.p.delay[NOT]+std::ceil(std::log2(w))*g.p.delay[AND2]+
                               std::ceil(std::log2(max_group))*g.p.delay[OR2];
            const double score=(area+delay)/w;
            if (score<best_score) {best_score=score;best=w;}
            frontier.swap(next);
            if (frontier.size()==1 && frontier.begin()->first==1) break;
        }
        return best;
    }

    Id map(Id id, bool allow_group) {
        g.clock.tick();
        if (id==0) return 0;
        if (id==1) return circuit.invert(0);
        Id& memo=allow_group?blocked[id]:unary[id];
        if (memo>=0) return memo;
        const BNode& bn=g.nodes[id];
        const bool recurse=allow_group && mode!=Grouping::top;
        int width=allow_group?std::min(max_width,g.p.n-bn.var):1;
        if (allow_group && mode==Grouping::adaptive) width=select_width(id,width);
        if (width==1) {
            Id lo=map(bn.lo,recurse), hi=map(bn.hi,recurse);
            return memo=mux(g.variables[bn.var]+1,lo,hi);
        }
        std::map<Id,std::vector<Id>> groups;
        std::vector<Id> path, terms;
        cubes(id,bn.var+width,path,groups);
        for (const auto& entry:groups) {
            Id cond=join(entry.second,false);
            if (entry.first!=1) cond=circuit.conj(cond,map(entry.first,recurse));
            terms.push_back(cond);
        }
        return memo=join(terms,false);
    }
};

inline std::vector<int> influence_order(const Problem& p, std::vector<int> order, Poll& clock,
                                        unsigned seed) {
    const std::size_t rows=p.table.size()/p.m;
    const std::size_t samples=std::min<std::size_t>(rows,512);
    std::vector<std::uint64_t> changes(p.n,0);
    std::mt19937_64 random(seed);
    for (std::size_t i=0;i<samples;++i) {
        const auto row=rows==samples?i:random()&(rows-1);
        for (int v=0;v<p.n;++v) {
            const auto paired=row^(std::size_t{1}<<(p.n-1-v));
            for(int j=0;j<p.m;++j) {
                clock.tick();
                changes[v]+=p.table[row*p.m+j]!=p.table[paired*p.m+j];
            }
        }
    }
    std::stable_sort(order.begin(),order.end(),[&](int a,int b){return changes[a]>changes[b];});
    return order;
}

enum class Order { forward, reverse, influence };
struct Descriptor {
    const char* name;
    Order order;
    Grouping group;
    bool pos;
    bool remap;
};
inline constexpr Descriptor seeds[] = {
    {"forward-sop",       Order::forward,   Grouping::single,    false, false},
    {"reverse-sop",       Order::reverse,   Grouping::single,    false, false},
    {"influence-sop",     Order::influence, Grouping::single,    false, false},
    {"forward-pos",       Order::forward,   Grouping::single,    true,  false},
    {"forward-demorgan",  Order::forward,   Grouping::single,    false, true},
    {"forward-top3",      Order::forward,   Grouping::top,       false, false},
    {"reverse-top3",      Order::reverse,   Grouping::top,       false, false},
    {"forward-rec3",      Order::forward,   Grouping::recursive, false, false},
    {"forward-adaptive3", Order::forward,   Grouping::adaptive,  false, false},
};

inline const Descriptor* find_seed(const std::string& profile) {
    return std::find_if(std::begin(seeds),std::end(seeds),
                        [&](const Descriptor& s){return s.name==profile;});
}
} // namespace seed_detail

// Each named constructor returns one owned, reachable seed. The four atomic
// decisions are variable order, grouping, Shannon expansion and gate mapping.
inline Netlist construct_seed(const Problem& p, const std::string& profile, RuntimeBudget& budget) {
    if (profile=="historical-adaptive") return historical_order::construct(p,budget);
    using namespace seed_detail;
    const auto* chosen=find_seed(profile);
    if (chosen==std::end(seeds)) throw std::invalid_argument("unknown seed profile: "+profile);
    Poll clock(budget);
    std::vector<int> permutation(p.n);
    std::iota(permutation.begin(),permutation.end(),0);
    if (chosen->order==Order::reverse) std::reverse(permutation.begin(),permutation.end());
    if (chosen->order==Order::influence)
        permutation=influence_order(p,std::move(permutation),clock,2106);
    OrderedGraph graph(p,permutation,clock);
    std::vector<Id> roots;
    for (int output=0;output<p.m;++output) roots.push_back(graph.root(output));
    GroupMapper mapper(graph,chosen->group,chosen->group==Grouping::single?1:3,chosen->pos);
    Netlist result=mapper.construct(roots);
    if (chosen->remap && !result.gates.empty()) {
        // Use the historical cost-aware, dual-polarity mapper on this seed
        // alone, allowing both AND and OR. No other seed takes part.
        Frontier mapped(std::numeric_limits<Score>::max());
        remap_area(p,result,mapped,p.target);
        clock.check();
        result=mapped.take_compromise();
    }
    return result;
}
} // namespace ttc
