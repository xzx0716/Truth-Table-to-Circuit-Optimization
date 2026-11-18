#include "ttc/optimization_api.hpp"
#include "ttc/seed_pipeline.hpp"
#include <cstdlib>
#include <sstream>
using namespace ttc;
#ifndef TTC_DEFAULT_STRATEGY
#define TTC_DEFAULT_STRATEGY "sweep"
#endif
#ifndef TTC_DEFAULT_INITIAL_SEEDS
#define TTC_DEFAULT_INITIAL_SEEDS "github,influence-sop,forward-pos,forward-demorgan,forward-top3,reverse-top3,forward-rec3,forward-adaptive3,historical-adaptive"
#endif
namespace {
std::string envs(const char* key,const std::string& def){const char* v=std::getenv(key);return v?v:def;}
int envi(const char* key,int def){const char* v=std::getenv(key);return v?std::stoi(v):def;}
void write_result(const char* path, int input_count, const Netlist& result) {
    std::ofstream out(path);
    if (!out) throw std::runtime_error("cannot open output");
    write_netlist(out, input_count, result);
    out.close();
    if (!out) throw std::runtime_error("write failed");
}
// Research archive keeps over-target points too. Selection remains the published
// handoff policy: feasible first, then normalized minimax A/D loss.
struct Archive {
    struct Point {Metrics m;Netlist net;std::string source;};
    const Problem& p;std::vector<Point> points;
    bool accept(Netlist net,const std::string& source){
        return accept_measured(normalize(p,net),source);
    }
    bool accept_measured(Netlist net,const std::string& source){
        auto m=measure(p,net);
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
    void log_frontier(const char* input, const std::string& strategy) const {
        const std::string path=envs("TTC_FRONTIER_LOG","");
        if (path.empty()) return;
        std::ofstream log(path,std::ios::app);
        for (const auto& q:points) log<<input<<','<<strategy<<','<<q.source<<','
            <<q.m.area<<','<<q.m.delay<<','<<(q.m.delay<=p.target)<<'\n';
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
        const std::string seed_profile = envs("TTC_INITIAL_SEED", "");
        // The course invocation needs only two paths. Explicit research settings
        // retain their old meaning, including TTC_STRATEGY=sweep as the control.
        const bool use_default_portfolio = !std::getenv("TTC_INITIAL_SEED") &&
            !std::getenv("TTC_INITIAL_SEEDS") && !std::getenv("TTC_STRATEGY");
        const std::string seed_profiles=envs("TTC_INITIAL_SEEDS",
            use_default_portfolio ? TTC_DEFAULT_INITIAL_SEEDS : "");
        if (!seed_profiles.empty()) {
            if (!seed_profile.empty())
                throw std::invalid_argument("specify either TTC_INITIAL_SEEDS or TTC_INITIAL_SEED");
            const auto profiles=portfolio_profiles(seed_profiles);
            Archive archive{p,{}};
            const auto completed=run_seed_portfolio(p,profiles,budget,[&](Netlist n,const std::string& label){
                archive.accept_measured(std::move(n),label);
            });
            auto result=archive.choose();
            write_result(argv[2],p.n,result);
            const auto metrics=measure(p,result);
            std::cerr<<"strategy=seed-portfolio completed="<<completed<<'/'<<profiles.size()
                     <<" frontier="<<archive.points.size()<<" area="<<metrics.area<<" delay="<<metrics.delay<<'\n';
            archive.log_frontier(argv[1],"seed-portfolio");
            return 0;
        }
        if (!seed_profile.empty()) {
            auto trial = run_seed_trial(p, seed_profile, budget);
            Metrics final;
            if (trial.post_complete) {
                final = measure(p, trial.selected);
                write_result(argv[2], p.n, trial.selected);
            }
            std::cerr << "seed=" << seed_profile
                      << " seed_area=" << trial.initial.area << " seed_delay=" << trial.initial.delay
                      << " area=" << final.area << " delay=" << final.delay
                      << " post_complete=" << int(trial.post_complete)
                      << " seed_complete=" << int(trial.seed_complete) << '\n';
            return trial.post_complete ? 0 : 3;
        }
        const std::string strategy=envs("TTC_STRATEGY",TTC_DEFAULT_STRATEGY);
        const double before=budget.elapsed_ms();
        Archive archive{p,{}};
        CandidateSink sink=[&](Netlist n,const std::string& label){archive.accept(std::move(n),label);};
        Netlist result=synthesize(p,[&](){return budget.should_stop();},
            strategy=="baseline"?CandidateSink{}:sink);
        budget.observe("base",p.table.size(),0,budget.elapsed_ms()-before);
        archive.accept(result,"base");
        budget.cap_work(envi("TTC_SEARCH_MS",100));
        if(strategy!="baseline" && !budget.should_stop()){
            SearchOptions opt;opt.strategy=strategy;
            opt.max_cut=envi("TTC_CUT",4);opt.rounds=envi("TTC_ROUNDS",strategy=="sweep"?16:2);
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
        write_result(argv[2], p.n, result);
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
        archive.log_frontier(argv[1],strategy);
    }catch(const std::exception& e){std::cerr<<"solver: "<<e.what()<<'\n';return 1;}
    return 0;
}
