#include "ttc/optimization_api.hpp"
#include <numeric>
#include <random>
#include <set>
#include <unordered_set>
#include <memory>
#include <fstream>
#include <sstream>

namespace ttc {
namespace {
struct Expr;
using E=std::shared_ptr<Expr>;
struct Expr { int op; Id leaf; E a,b; };
E ref(Id x) {return std::make_shared<Expr>(Expr{-1,x,{},{}});}
E gate(int op,E a,E b={}) {return std::make_shared<Expr>(Expr{op,0,std::move(a),std::move(b)});}
E inv(E a) {return gate(NOT,std::move(a));}
E bin(int op,E a,E b) {return gate(op,std::move(a),std::move(b));}
GateType dual(GateType t) {return t==AND2?OR2:AND2;}
const Gate& get(const Problem& p,const Netlist& n,Id i) {return n.gates.at(i-p.n-1);}
bool isgate(const Problem& p,const Netlist& n,Id i,int op) {
    return i>p.n && get(p,n,i).type==op;
}
void leaves(const E& e,std::set<Id>& out) {
    if(e->op<0) {if(e->leaf)out.insert(e->leaf);return;}
    leaves(e->a,out);if(e->b)leaves(e->b,out);
}
std::uint64_t fingerprint(const Netlist& n) {
    std::uint64_t h=1469598103934665603ULL;
    auto add=[&](std::uint64_t x){h=(h^x)*1099511628211ULL;};
    for(const auto& g:n.gates){add(g.type);add(g.a);add(g.b);}for(Id x:n.outputs)add(x);return h;
}
Netlist compact(const Problem& p,const Circuit& c,const std::vector<Id>& roots) {
    auto used=c.reachable(roots);std::vector<Id> ids(c.gates.size());
    std::iota(ids.begin(),ids.begin()+p.n+1,0);Netlist n;
    for(Id i=p.n+1;i<Id(c.gates.size());++i)if(used[i]){
        const auto& g=c.gates[i];ids[i]=p.n+1+Id(n.gates.size());
        n.gates.push_back({g.type,ids[g.a],g.type==NOT?0:ids[g.b],g.arrival});
    }
    for(Id x:roots)n.outputs.push_back(ids[x]);
    return n;
}
// A replacement may only depend on preceding signals, hence cannot introduce a cycle.
Netlist replace(const Problem& p,const Netlist& old,Id root,const E& expr,RuntimeBudget& budget) {
    Circuit c(p,Direct);std::vector<Id> ids(p.n+1+old.gates.size());
    std::iota(ids.begin(),ids.begin()+p.n+1,0);
    std::function<Id(const E&)> emit=[&](const E& e)->Id {
        if(e->op<0)return ids[e->leaf];
        Id a=emit(e->a);if(e->op==NOT)return c.invert(a);
        Id b=emit(e->b);return e->op==AND2?c.conj(a,b):c.disj(a,b);
    };
    for(Id i=p.n+1;i<Id(ids.size());++i){
        if((i&255)==0 && budget.should_stop())return {};
        if(i==root){ids[i]=emit(expr);continue;}
        const auto& g=get(p,old,i);
        ids[i]=g.type==NOT?c.invert(ids[g.a]):g.type==AND2?c.conj(ids[g.a],ids[g.b]):c.disj(ids[g.a],ids[g.b]);
    }
    std::vector<Id> roots;for(Id x:old.outputs)roots.push_back(ids[x]);return compact(p,c,roots);
}

bool memory_allowed(const RuntimeBudget& budget,std::size_t extra=0) {
    // Linux is the submission platform. Actual RSS includes the input table, core,
    // frontier and other modules; cap optional work before consuming the last 15%.
    if(budget.ram_kb()<=0)return true;
    std::ifstream in("/proc/self/status");std::string line;std::size_t rss=0;
    while(std::getline(in,line))if(line.compare(0,6,"VmRSS:")==0){std::istringstream(line.substr(6))>>rss;break;}
    return rss*1024.0+double(extra)<double(budget.ram_kb())*1024.0*0.85;
}
using Truth=std::vector<unsigned char>;
// All assignments to boundary signals are checked, even if some combinations are unreachable.
Truth truth(const Problem& p,const Netlist& n,Id root,const std::vector<Id>& boundary,RuntimeBudget& budget) {
    const std::size_t k=boundary.size();
    if(k>=std::numeric_limits<std::size_t>::digits)return {};
    const std::size_t count=std::size_t(1)<<k;
    if(!memory_allowed(budget,count*2+n.gates.size()+p.n+1))return {};
    std::unordered_map<Id,std::size_t> index;for(std::size_t j=0;j<k;++j)index[boundary[j]]=j;
    std::vector<Id> cone;std::unordered_set<Id> seen;bool valid=true;
    std::function<void(Id)> visit=[&](Id x){
        if(x==0||index.count(x)||!seen.insert(x).second)return;
        if(x<=p.n){valid=false;return;}const auto& g=get(p,n,x);visit(g.a);if(g.type!=NOT)visit(g.b);cone.push_back(x);
    };visit(root);if(!valid)return {};
    std::vector<unsigned char> v(p.n+1+n.gates.size());Truth out(count);
    for(std::size_t row=0;row<count;++row){
        if((row&255)==0&&budget.should_stop())return {};
        for(std::size_t j=0;j<k;++j)v[boundary[j]]=(row>>j)&1;
        for(Id x:cone){const auto& g=get(p,n,x);v[x]=g.type==NOT?!v[g.a]:g.type==AND2?(v[g.a]&v[g.b]):(v[g.a]|v[g.b]);}
        out[row]=v[root];
    }return out;
}
bool equivalent(const Problem& p,const Netlist& n,Id root,const E& e,RuntimeBudget& budget) {
    std::set<Id> ls;leaves(e,ls);for(Id x:ls)if(x>=root)return false;
    // Complete the small boundary for rules that remove an entire operand (absorption).
    // Three levels cover the algebraic templates; deeper signals are independent cut inputs.
    std::function<void(Id,int)> complete=[&](Id x,int depth){
        if(x==0||ls.count(x))return;
        if(x<=p.n||depth==0){ls.insert(x);return;}
        const auto& g=get(p,n,x);complete(g.a,depth-1);if(g.type!=NOT)complete(g.b,depth-1);
    };complete(root,3);
    std::vector<Id> boundary(ls.begin(),ls.end());auto target=truth(p,n,root,boundary,budget);if(target.empty())return false;
    std::unordered_map<Id,std::size_t> index;for(std::size_t j=0;j<boundary.size();++j)index[boundary[j]]=j;
    std::function<bool(const E&,std::size_t)> eval=[&](const E& x,std::size_t row)->bool {
        if(x->op<0)return x->leaf?((row>>index[x->leaf])&1):false;
        bool a=eval(x->a,row);if(x->op==NOT)return !a;
        bool b=eval(x->b,row);return x->op==AND2?a&&b:a||b;
    };
    for(std::size_t row=0;row<target.size();++row)if(eval(e,row)!=bool(target[row]))return false;
    return true;
}
struct Proposal {E expr;std::string name;};
std::vector<Proposal> algebraic(const Problem& p,const Netlist& n,Id root,bool expansion) {
    std::vector<Proposal> out;const auto& g=get(p,n,root);
    auto push=[&](E e,const char* name){out.push_back({std::move(e),name});};
    if(g.type==NOT){
        if(isgate(p,n,g.a,NOT))push(ref(get(p,n,g.a).a),"double-negation");
        if(g.a>p.n&&get(p,n,g.a).type!=NOT){auto q=get(p,n,g.a);push(bin(dual(q.type),inv(ref(q.a)),inv(ref(q.b))),"demorgan-push");}
        return out;
    }
    for(int swap=0;swap<2;++swap){Id a=swap?g.b:g.a,b=swap?g.a:g.b;
        if(isgate(p,n,b,dual(g.type))){auto q=get(p,n,b);
            if(q.a==a||q.b==a)push(ref(a),"absorption");
            if(expansion)push(bin(dual(g.type),bin(g.type,ref(a),ref(q.a)),bin(g.type,ref(a),ref(q.b))),"distribute");
        }
        if(isgate(p,n,b,g.type)){auto q=get(p,n,b);
            push(bin(g.type,bin(g.type,ref(a),ref(q.a)),ref(q.b)),"reassociate");
            push(bin(g.type,bin(g.type,ref(a),ref(q.b)),ref(q.a)),"reassociate");
        }
    }
    if(isgate(p,n,g.a,dual(g.type))&&isgate(p,n,g.b,dual(g.type))){
        auto a=get(p,n,g.a),b=get(p,n,g.b);Id aa[2]{a.a,a.b},bb[2]{b.a,b.b};
        for(int i=0;i<2;++i)for(int j=0;j<2;++j)if(aa[i]==bb[j])
            push(bin(dual(g.type),ref(aa[i]),bin(g.type,ref(aa[1-i]),ref(bb[1-j]))),"factor");
    }
    if(isgate(p,n,g.a,NOT)&&isgate(p,n,g.b,NOT))
        push(inv(bin(dual(g.type),ref(get(p,n,g.a).a),ref(get(p,n,g.b).a))),"demorgan-pull");
    return out;
}

E resynthesize(const Truth& tab,const std::vector<Id>& order,std::size_t level,int style,
               std::unordered_map<std::string,E>& memo,RuntimeBudget& budget) {
    if(budget.should_stop())return {};
    bool zero=std::all_of(tab.begin(),tab.end(),[](auto x){return x==0;});if(zero)return ref(0);
    bool one=std::all_of(tab.begin(),tab.end(),[](auto x){return x!=0;});if(one)return inv(ref(0));
    std::string key(reinterpret_cast<const char*>(tab.data()),tab.size());key+=char(level);
    auto found=memo.find(key);if(found!=memo.end())return found->second;
    if(level>=order.size())throw std::runtime_error("nonconstant terminal in resynthesis");
    Truth lo(tab.size()/2),hi(tab.size()/2);for(std::size_t i=0;i<lo.size();++i){lo[i]=tab[2*i];hi[i]=tab[2*i+1];}
    if(lo==hi)return memo[key]=resynthesize(lo,order,level+1,style,memo,budget);
    E a=resynthesize(lo,order,level+1,style,memo,budget),b=resynthesize(hi,order,level+1,style,memo,budget);
    if(!a||!b)return {};
    auto iszero=[](const E& e){return e->op<0&&e->leaf==0;};
    auto isone=[&](const E& e){return e->op==NOT&&iszero(e->a);};
    E x=ref(order[level]),nx=inv(x),r;
    if(iszero(a))r=isone(b)?x:bin(AND2,x,b);
    else if(iszero(b))r=isone(a)?nx:bin(AND2,nx,a);
    else if(isone(a))r=bin(OR2,nx,b);
    else if(isone(b))r=bin(OR2,x,a);
    else if(style==1)r=bin(AND2,bin(OR2,x,a),bin(OR2,nx,b));
    else r=bin(OR2,bin(AND2,nx,a),bin(AND2,x,b));
    memo.emplace(std::move(key),r);return r;
}
void cut_proposals(const Problem& p,const Netlist& n,Id root,int max_cut,RuntimeBudget& budget,
                   const std::function<void(const Proposal&)>& accept) {
    if(max_cut<2)return;
    std::set<std::vector<Id>> seen;std::vector<std::vector<Id>> cuts{{root}};
    // Enumerate successive frontiers; each expansion either descends or increases boundary size.
    for(std::size_t ci=0;ci<cuts.size()&&!budget.should_stop();++ci){
        if((ci&63)==0&&!memory_allowed(budget))break;
        auto cut=cuts[ci];
        for(std::size_t j=0;j<cut.size()&&!budget.should_stop();++j){
            if(cut[j]<=p.n)continue;
            auto q=get(p,n,cut[j]);std::vector<Id> next=cut;
            next.erase(next.begin()+j);if(q.a)next.push_back(q.a);if(q.type!=NOT&&q.b)next.push_back(q.b);
            std::sort(next.begin(),next.end());next.erase(std::unique(next.begin(),next.end()),next.end());
            if(next.size()>std::size_t(max_cut)||!seen.insert(next).second)continue;
            cuts.push_back(next);
            if(next.empty())continue;
            auto t=truth(p,n,root,next,budget);if(t.empty())continue;
            // Each ordering is an actual alternative Shannon decomposition; construction is memoized.
            for(int variant=0;variant<3&&!budget.should_stop();++variant){
                auto order=next;
                if(variant==1)std::reverse(order.begin(),order.end());
                if(variant==2)std::stable_sort(order.begin(),order.end(),[&](Id a,Id b){
                    auto arrival=[&](Id x){return x<=p.n?Score(0):get(p,n,x).arrival;};return arrival(a)>arrival(b);});
                Truth reordered(t.size());for(std::size_t row=0;row<t.size();++row){std::size_t oldrow=0;
                    for(std::size_t k=0;k<order.size();++k){auto pos=std::lower_bound(next.begin(),next.end(),order[k])-next.begin();oldrow|=((row>>k)&1)<<pos;}
                    reordered[row]=t[oldrow];}
                std::unordered_map<std::string,E> memo;
                E expr=resynthesize(reordered,order,0,variant==1?1:0,memo,budget);
                if(expr)accept({expr,"cut-shannon"});
            }
        }
    }
}
struct State {Netlist net;Metrics metrics;std::uint64_t hash;};
bool dominates(const Metrics& a,const Metrics& b) {return a.area<=b.area&&a.delay<=b.delay&&(a.area<b.area||a.delay<b.delay);}
double energy(const Metrics& m,const Metrics& base,double weight,Score target) {
    double a=double(m.area)/std::max<Score>(1,base.area),d=double(m.delay)/std::max<Score>(1,base.delay);
    return a+weight*d+std::max(0.0,double(m.delay-target)/std::max<Score>(1,target));
}
void neighbours(const Problem& p,const State& state,RuntimeBudget& budget,const SearchOptions& options,
                std::mt19937& rng,bool randomized,const std::function<void(Netlist,const std::string&)>& accept) {
    std::vector<Id> roots(state.net.gates.size());std::iota(roots.begin(),roots.end(),p.n+1);
    if(randomized)std::shuffle(roots.begin(),roots.end(),rng);
    else std::stable_sort(roots.begin(),roots.end(),[&](Id a,Id b){return get(p,state.net,a).arrival>get(p,state.net,b).arrival;});
    std::size_t regions=0;
    for(Id root:roots){
        if(budget.should_stop()||(options.max_regions&&regions>=options.max_regions))break;
        ++regions;
        const double units=state.net.gates.size()+1;
        if(!budget.can_start("rewrite-region",units))break;
        auto start=RuntimeBudget::Clock::now();double predicted=budget.predict("rewrite-region",units);
        auto proposals=algebraic(p,state.net,root,options.allow_expansion);
        std::unordered_set<std::uint64_t> local_seen;
        auto evaluate=[&](const Proposal& proposal){
            if(budget.should_stop()||!budget.can_start("candidate-rebuild",units)||
               !memory_allowed(budget,units*(sizeof(Gate)*3+sizeof(Id)*4)))return;
            auto cstart=RuntimeBudget::Clock::now();double cpred=budget.predict("candidate-rebuild",units);
            // Truth checking covers all boundary assignments, independent of the global public case.
            if(!equivalent(p,state.net,root,proposal.expr,budget))return;
            auto candidate=replace(p,state.net,root,proposal.expr,budget);
            if(candidate.outputs.empty())return;
            auto hash=fingerprint(candidate);
            if(hash!=state.hash&&local_seen.insert(hash).second)accept(std::move(candidate),proposal.name);
            double actual=std::chrono::duration<double,std::milli>(RuntimeBudget::Clock::now()-cstart).count();
            budget.observe("candidate-rebuild",units,cpred,actual);
        };
        for(const auto& proposal:proposals)evaluate(proposal);
        if(options.max_cut>=2&&!budget.should_stop())
            cut_proposals(p,state.net,root,options.max_cut,budget,evaluate);
        double actual=std::chrono::duration<double,std::milli>(RuntimeBudget::Clock::now()-start).count();
        budget.observe("rewrite-region",units,predicted,actual);
    }
}
}

void run_local_rewrite(const Problem& p,const Netlist& seed,RuntimeBudget& budget,const CandidateSink& sink,const SearchOptions& options) {
    if(seed.outputs.empty()||budget.should_stop()||options.rounds<=0||!memory_allowed(budget))return;
    State initial{normalize(p,seed),{},0};initial.metrics=measure(p,initial.net);initial.hash=fingerprint(initial.net);
    std::mt19937 rng(options.random_seed);std::unordered_set<std::uint64_t> emitted;
    const bool anneal=options.strategy=="anneal",beam=options.strategy=="beam",multi=options.strategy=="multistart";
    int restarts=multi?std::max(1,options.restarts):1;
    for(int restart=0;restart<restarts&&!budget.should_stop();++restart){
        // Each restart explores with its own weight/order; global deduplication
        // applies only to emitted snapshots, not to its internal transitions.
        std::unordered_set<std::uint64_t> visited{initial.hash};
        std::vector<State> states{initial};double weight=multi?(0.25+double(rng()%200)/100.0):1.0;
        for(int round=0;round<std::max(1,options.rounds)&&!budget.should_stop();++round){
            std::vector<State> next;bool changed=false;
            for(const auto& state:states){
                std::vector<State> candidates;
                neighbours(p,state,budget,options,rng,multi||anneal,[&](Netlist n,const std::string& tag){
                    auto h=fingerprint(n);if(!visited.insert(h).second)return;
                    auto m=measure(p,n);if(emitted.insert(h).second)sink(Netlist(n),options.strategy+":"+tag);
                    const double delta=energy(m,initial.metrics,weight,p.target)-energy(state.metrics,initial.metrics,weight,p.target);
                    bool use=dominates(m,state.metrics)||delta<-1e-12;
                    if(beam)use=true;
                    if(anneal){double temperature=0.20/(round+1);double u=(double(rng())+1)/(double(rng.max())+2);use=use||u<std::exp(-std::max(0.0,delta)/temperature);}
                    if(use){candidates.push_back({std::move(n),m,h});changed=true;}
                    // Bound temporary full-netlist storage by requested beam width; search itself still visits every region until budget.
                    std::size_t keep=std::size_t(beam?std::max(1,options.beam_width):1);
                    auto less=[&](const State& a,const State& b){return energy(a.metrics,initial.metrics,weight,p.target)<energy(b.metrics,initial.metrics,weight,p.target);};
                    if(candidates.size()>keep){if(anneal)candidates.erase(candidates.begin());else {auto worst=std::max_element(candidates.begin(),candidates.end(),less);candidates.erase(worst);}}
                });
                for(auto& c:candidates)next.push_back(std::move(c));
            }
            if(!changed||next.empty())break;
            std::sort(next.begin(),next.end(),[&](const State& a,const State& b){return energy(a.metrics,initial.metrics,weight,p.target)<energy(b.metrics,initial.metrics,weight,p.target);});
            std::size_t width=std::size_t(beam?std::max(1,options.beam_width):1);if(next.size()>width)next.resize(width);
            states=std::move(next);
        }
    }
}
}
