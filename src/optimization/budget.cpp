#include "ttc/optimization_api.hpp"
#include <stdexcept>
#ifdef __linux__
#include <unistd.h>
#endif

namespace ttc {
bool RuntimeBudget::should_stop() const {
    if(remaining_ms()<=0)return true;
#ifdef __linux__
    if(ram_kb_>0){
        // Linux virtual resident pages, not evaluator/checker memory.
        std::ifstream stat("/proc/self/statm");long long pages=0,resident=0;
        if(stat>>pages>>resident){const long long kb=resident*sysconf(_SC_PAGESIZE)/1024;
            if(kb>ram_kb_*0.85)return true;
        }
    }
#endif
    return false;
}
double RuntimeBudget::predict(const std::string& operation,double units) const {
    auto it=rates_.find(operation);
    // Uncalibrated estimates only admit a small probe. Actual records calibrate
    // later calls; this is a conservative scheduler, not a deadline proof.
    const double rate=it==rates_.end()?0.00002:it->second;
    return std::max(0.02,rate*std::max(1.0,units)*1.5);
}
bool RuntimeBudget::can_start(const std::string& operation,double units) const {
    return !should_stop() && predict(operation,units)<remaining_ms();
}
void RuntimeBudget::observe(const std::string& operation,double units,double predicted,double actual) {
    // Keep an online diagnostic sample bounded; calibration below uses every observation.
    auto& sample=records_[operation];
    if(sample.size()<4096)sample.push_back({predicted,actual,units,actual>predicted});
    const double rate=actual/std::max(1.0,units);
    auto it=rates_.find(operation);
    if(it==rates_.end()) rates_[operation]=rate;
    else it->second=std::max(rate,0.75*it->second+0.25*rate);
}
Metrics measure(const Problem& p,const Netlist& net) {
    const auto first=static_cast<std::size_t>(p.n+1);
    std::vector<Score> t(first+net.gates.size(),0);
    std::vector<char> used(t.size(),0);
    Metrics out;
    for(std::size_t k=0;k<net.gates.size();++k) {
        const auto& g=net.gates[k]; const auto id=first+k;
        if(g.a<0 || static_cast<std::size_t>(g.a)>=id ||
           (g.type!=NOT && (g.b<0 || static_cast<std::size_t>(g.b)>=id)))
            throw std::runtime_error("non-topological candidate");
        t[id]=t[g.a]+p.delay[g.type];
        if(g.type!=NOT)t[id]=std::max(t[g.a],t[g.b])+p.delay[g.type];
    }
    for(Id id:net.outputs) {
        if(id<0 || static_cast<std::size_t>(id)>=t.size())throw std::runtime_error("bad output");
        used[id]=1;out.delay=std::max(out.delay,t[id]);
    }
    for(std::size_t id=t.size();id-->first;)if(used[id]) {
        const auto& g=net.gates[id-first];used[g.a]=1;if(g.type!=NOT)used[g.b]=1;
        out.area+=p.area[g.type];++out.gates;
    }
    return out;
}
Netlist normalize(const Problem& p,const Netlist& net) {
    Circuit c(p,Direct);std::vector<Id> ids(p.n+1+net.gates.size());
    for(int i=0;i<=p.n;++i)ids[i]=i;
    for(std::size_t k=0;k<net.gates.size();++k){
        const auto& g=net.gates[k];
        ids[p.n+1+k]=g.type==NOT?c.invert(ids[g.a]):
            g.type==AND2?c.conj(ids[g.a],ids[g.b]):c.disj(ids[g.a],ids[g.b]);
    }
    std::vector<Id> roots;for(Id id:net.outputs)roots.push_back(ids[id]);
    Frontier f(std::numeric_limits<Score>::max());c.consider(roots,f);
    return f.take_compromise();
}
}
