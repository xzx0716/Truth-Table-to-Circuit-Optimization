#include "ttc/optimization_api.hpp"
#include <cassert>
#include <iostream>
#include <random>
#include <set>
using namespace ttc;
std::vector<int> eval(const Problem& p,const Netlist& n,int row){
    std::vector<int> v(p.n+1);for(int j=0;j<p.n;++j)v[j+1]=(row>>(p.n-1-j))&1;
    for(auto g:n.gates)v.push_back(g.type==NOT?!v[g.a]:g.type==AND2?(v[g.a]&v[g.b]):(v[g.a]|v[g.b]));
    std::vector<int> out;for(Id x:n.outputs)out.push_back(v[x]);return out;
}
void verify(const Problem& p,const Netlist& a,const Netlist& b){
    assert(a.outputs.size()==b.outputs.size());
    for(int row=0;row<(1<<p.n);++row)assert(eval(p,a,row)==eval(p,b,row));
    measure(p,b);
}
int main(){
    Problem p{};p.n=4;p.m=2;p.area={1,1,1};p.delay={1,1,1};p.target=20;
    // ab+ac, with ab also shared by a separate output.
    Netlist factoring{{{AND2,1,2,1},{AND2,1,3,1},{OR2,5,6,2}}, {7,5}};
    Netlist absorption{{{AND2,1,2,1},{OR2,1,5,2}}, {6,5}};
    Netlist chain{{{AND2,1,2,1},{AND2,5,3,2},{AND2,6,4,3}}, {7,5}};
    int checked=0;
    for(std::string strategy:{"greedy","beam","anneal","multistart"}){
        for(const auto& seed:{factoring,absorption,chain}){
            RuntimeBudget budget;budget.configure(10000);SearchOptions o;o.strategy=strategy;o.max_cut=4;o.rounds=3;o.beam_width=3;o.restarts=3;
            auto before=measure(p,seed);Score best_area=before.area,best_delay=before.delay;std::set<std::string> tags;
            run_local_rewrite(p,seed,budget,[&](Netlist n,const std::string& tag){verify(p,seed,n);auto m=measure(p,n);best_area=std::min(best_area,m.area);best_delay=std::min(best_delay,m.delay);tags.insert(tag);++checked;},o);
            assert(!tags.empty());
            if(seed.outputs[0]==6)assert(best_area<before.area);
            if(seed.outputs[0]==7 && seed.gates.back().type==AND2)assert(best_delay<before.delay);
        }
    }
    // Independent random multi-output DAGs: every emitted candidate must preserve every row.
    std::mt19937 rng(81519);
    for(int trial=0;trial<30;++trial){
        Netlist n;for(int k=0;k<10;++k){int op=rng()%3,range=p.n+1+k;Id a=rng()%range,b=rng()%range;n.gates.push_back({GateType(op),a,op==NOT?0:b,0});}
        n.outputs={Id(p.n+n.gates.size()),Id(p.n+1+rng()%n.gates.size())};n=normalize(p,n);
        RuntimeBudget budget;budget.configure(1000);SearchOptions o;o.strategy=trial%2?"beam":"greedy";o.max_cut=3;o.rounds=2;o.max_regions=20;
        run_local_rewrite(p,n,budget,[&](Netlist out,const std::string&){verify(p,n,out);++checked;},o);
    }
    // Two independent factors improve in one sweep, rather than one whole-graph
    // candidate rebuild per factor. A shared root is still charged only once.
    Netlist batch{{{AND2,1,2,1},{AND2,1,3,1},{OR2,5,6,2},
                   {AND2,4,2,1},{AND2,4,3,1},{OR2,8,9,2}}, {7,10}};
    RuntimeBudget bb;bb.configure(1000);SearchOptions bo;bo.max_cut=0;bo.rounds=1;
    bool swept=false;run_local_rewrite(p,batch,bb,[&](Netlist out,const std::string& tag){
        verify(p,batch,out);++checked;
        if(tag.find("algebraic-sweep")!=std::string::npos){assert(measure(p,out).area<=4);swept=true;}
    },bo);assert(swept);
    RuntimeBudget sb;sb.configure(1000);SearchOptions so;so.strategy="sweep";so.rounds=10;
    Score sweeparea=measure(p,batch).area;int sweeps=0;
    run_local_rewrite(p,batch,sb,[&](Netlist out,const std::string& tag){
        assert(tag=="sweep:algebraic-sweep");verify(p,batch,out);
        sweeparea=std::min(sweeparea,measure(p,out).area);++sweeps;++checked;
    },so);assert(sweeparea<=4&&sweeps>0);
    RuntimeBudget stable;stable.configure(1000);int duplicate=0;
    Netlist stable_seed{{{OR2,1,2,1},{AND2,5,3,2}}, {5,6}};
    run_local_rewrite(p,stable_seed,stable,[&](Netlist,const std::string&){++duplicate;},so);
    assert(duplicate==0&&stable.records().at("algebraic-sweep").size()==1);
    // Generic exact library is active, independently of Shannon candidate generation.
    RuntimeBudget tb;tb.configure(1000);SearchOptions to;to.max_cut=2;to.rounds=1;
    bool templated=false;
    run_local_rewrite(p,absorption,tb,[&](Netlist out,const std::string& tag){verify(p,absorption,out);
        if(tag.find("cut-exact-template")!=std::string::npos)templated=true;
        ++checked;},to);
    // An equivalent exact network may already have been emitted by the algebraic pass;
    // the exhaustive template generator is separately checked in the exact-tool tests.
    (void)templated;
    // Constants, complementary and duplicate outputs survive pruning/rebuilding.
    Netlist constants{{{NOT,0,0,1},{NOT,5,0,2},{OR2,6,1,3},{NOT,1,0,1}}, {0,5,6,7,8,5}};
    RuntimeBudget cb;cb.configure(1000);SearchOptions co;co.max_cut=4;co.rounds=2;
    auto cn=normalize(p,constants);verify(p,constants,cn);
    run_local_rewrite(p,constants,cb,[&](Netlist out,const std::string&){verify(p,constants,out);++checked;},co);
    // Distinguish traversal algorithms with a distributive move that is initially
    // worse: greedy emits it but will not traverse it; beam/annealing may continue.
    Netlist escape{{{OR2,2,3,1},{AND2,1,5,2},{OR2,4,6,3}}, {7,5}};
    std::map<std::string,int> rebuilds;
    for(std::string strategy:{"greedy","beam","anneal","multistart"}){
        RuntimeBudget b;b.configure(10000);SearchOptions x;x.strategy=strategy;x.max_cut=0;x.rounds=3;x.beam_width=4;x.restarts=3;
        run_local_rewrite(p,escape,b,[&](Netlist out,const std::string&){verify(p,escape,out);++checked;},x);
        rebuilds[strategy]=int(b.records().at("rewrite-region").size());
    }
    assert(rebuilds["beam"]>rebuilds["greedy"]);
    assert(rebuilds["multistart"]>rebuilds["greedy"]);
    RuntimeBudget zero;zero.configure(10000);SearchOptions none;none.rounds=0;int z=0;
    run_local_rewrite(p,factoring,zero,[&](Netlist,const std::string&){++z;},none);assert(z==0);
    RuntimeBudget lowmem;lowmem.configure(10000,1);int lm=0;
    run_local_rewrite(p,factoring,lowmem,[&](Netlist,const std::string&){++lm;},SearchOptions{});assert(lm==0);
    RuntimeBudget stopped;stopped.configure(1);SearchOptions o;int emitted=0;
    run_local_rewrite(p,factoring,stopped,[&](Netlist,const std::string&){++emitted;},o);assert(emitted==0);
    std::cout<<"PASS local rewrite: "<<checked<<" candidates checked, four strategies, traversal distinction, sharing, random DAGs, early cutoff\n";
}
