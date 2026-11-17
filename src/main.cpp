#include "ttc/optimization_api.hpp"
#include <cstdlib>
#include <sstream>
using namespace ttc;
#ifndef TTC_DEFAULT_STRATEGY
#define TTC_DEFAULT_STRATEGY "baseline"
#endif
namespace {
std::string envs(const char* key,const std::string& def){const char* v=std::getenv(key);return v?v:def;}
int envi(const char* key,int def){const char* v=std::getenv(key);return v?std::stoi(v):def;}
// Research archive keeps over-target points too. Selection remains the published
// handoff policy: feasible first, then normalized minimax A/D loss.
struct Archive {
    struct Point {Metrics m;Netlist net;std::string source;};
    const Problem& p;std::vector<Point> points;
    bool accept(Netlist net,const std::string& source){
        net=normalize(p,net);auto m=measure(p,net);
        for(const auto& q:points)if(q.m.area<=m.area && q.m.delay<=m.delay &&
            (q.m.area<m.area || q.m.delay<m.delay || q.m.gates<=m.gates))return false;
        points.erase(std::remove_if(points.begin(),points.end(),[&](const Point& q){
            return m.area<=q.m.area && m.delay<=q.m.delay;
        }),points.end());
        points.push_back({m,std::move(net),source});return true;
    }
    Netlist choose()const{
        Frontier f(p.target);
        for(const auto& q:points)if(auto n=f.accept(q.m.area,q.m.delay,q.net.gates.size()))*n=q.net;
        return f.take_compromise();
    }
};
}
int main(int argc,char** argv){
    RuntimeBudget budget;
    if(argc!=3){std::cerr<<"usage: solver INPUT_PATH OUTPUT_PATH\n";return 2;}
    try{
        std::ifstream input(argv[1]);if(!input)throw std::runtime_error("cannot open input");
        Problem p=read_problem(input);
        budget.configure(p.runtime_ms,p.ram_kb,envi("TTC_RESEARCH_MS",0));
        const std::string strategy=envs("TTC_STRATEGY",TTC_DEFAULT_STRATEGY);
        const double before=budget.elapsed_ms();
        Netlist result=synthesize(p,[&](){return budget.should_stop();});
        budget.observe("base",p.table.size(),0,budget.elapsed_ms()-before);
        Archive archive{p,{}};archive.accept(result,"base");
        CandidateSink sink=[&](Netlist n,const std::string& label){archive.accept(std::move(n),label);};
        budget.cap_work(envi("TTC_SEARCH_MS",100));
        if(strategy!="baseline" && !budget.should_stop()){
            SearchOptions opt;opt.strategy=strategy;
            opt.max_cut=envi("TTC_CUT",4);opt.rounds=envi("TTC_ROUNDS",2);
            opt.beam_width=envi("TTC_BEAM",4);opt.restarts=envi("TTC_RESTARTS",3);
            opt.max_regions=std::max(0,envi("TTC_REGIONS",0));
            opt.random_seed=static_cast<unsigned>(envi("TTC_SEED",2106));
            std::vector<std::string> methods=strategy=="portfolio"?
                std::vector<std::string>{"greedy","beam","anneal","multistart"}:
                std::vector<std::string>{strategy};
            for(const auto& method:methods){
                if(budget.should_stop())break;
                opt.strategy=method;auto seed=archive.choose();
                run_local_rewrite(p,seed,budget,sink,opt);
            }
            result=archive.choose();
        }
        std::ofstream output(argv[2]);if(!output)throw std::runtime_error("cannot open output");
        write_netlist(output,p.n,result);output.close();if(!output)throw std::runtime_error("write failed");
        const auto m=measure(p,result);
        std::cerr<<"area="<<m.area<<" delay="<<m.delay<<" elapsed_ms="<<budget.elapsed_ms()
                 <<" strategy="<<strategy<<" frontier="<<archive.points.size()<<'\n';
        const std::string costs=envs("TTC_COST_LOG","");
        if(!costs.empty()){
            std::ofstream log(costs,std::ios::app);
            for(const auto& op:budget.records())for(const auto& r:op.second)
                log<<argv[1]<<','<<strategy<<','<<op.first<<','<<r.units<<','<<r.predicted_ms
                   <<','<<r.actual_ms<<','<<r.underestimated<<'\n';
        }
        const std::string frontier=envs("TTC_FRONTIER_LOG","");
        if(!frontier.empty()){
            std::ofstream log(frontier,std::ios::app);
            for(const auto& q:archive.points)log<<argv[1]<<','<<strategy<<','<<q.source<<','
                <<q.m.area<<','<<q.m.delay<<','<<(q.m.delay<=p.target)<<'\n';
        }
    }catch(const std::exception& e){std::cerr<<"solver: "<<e.what()<<'\n';return 1;}
    return 0;
}
