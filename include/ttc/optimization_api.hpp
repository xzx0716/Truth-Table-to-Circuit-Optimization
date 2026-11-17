#pragma once
#include "ttc/core.hpp"
#include <chrono>
#include <cmath>
#include <functional>
#include <map>
#include <string>

namespace ttc {
struct CostRecord { double predicted_ms=0, actual_ms=0, units=0; bool underestimated=false; };
class RuntimeBudget {
public:
    using Clock=std::chrono::steady_clock;
    explicit RuntimeBudget(Clock::time_point start=Clock::now()):start_(start){}
    void configure(long long limit_ms, long long ram_kb=0, double research_ms=0) {
        limit_=research_ms>0?research_ms:double(limit_ms); ram_kb_=ram_kb;
        reserve_=limit_>0?std::max(5.0,limit_*0.10):0;
    }
    double elapsed_ms() const {return std::chrono::duration<double,std::milli>(Clock::now()-start_).count();}
    double remaining_ms() const {double r=limit_>0?limit_-reserve_-elapsed_ms():1e100; if(work_deadline_>0)r=std::min(r,work_deadline_-elapsed_ms());return std::max(0.0,r);}
    bool should_stop() const;
    void cap_work(double ms) {if(ms>0) work_deadline_=elapsed_ms()+ms;}
    bool can_start(const std::string& operation,double units) const;
    double predict(const std::string& operation,double units) const;
    void observe(const std::string& operation,double units,double predicted,double actual);
    const std::map<std::string,std::vector<CostRecord>>& records() const {return records_;}
    void reserve_for_output(double ms) {reserve_=std::max(reserve_,ms);}
    long long ram_kb() const {return ram_kb_;}
private:
    Clock::time_point start_; double limit_=0,reserve_=0,work_deadline_=0; long long ram_kb_=0;
    std::map<std::string,double> rates_;
    std::map<std::string,std::vector<CostRecord>> records_;
};
struct Metrics {Score area=0,delay=0; std::size_t gates=0;};
Metrics measure(const Problem&,const Netlist&);
Netlist normalize(const Problem&,const Netlist&);
using CandidateSink=std::function<void(Netlist,const std::string&)>;
struct SearchOptions {
    std::string strategy="greedy";
    int max_cut=4,beam_width=4,rounds=2,restarts=1;
    unsigned random_seed=2106;
    std::size_t max_regions=0; // zero: bounded by graph, rounds, and common runtime budget
    bool allow_expansion=true;
};
void run_local_rewrite(const Problem&,const Netlist&,RuntimeBudget&,const CandidateSink&,const SearchOptions&);
// B integration hooks: B supplies these optional modules in its own branch.
// run_mapping_search(problem,seed_snapshot,budget,candidate_sink)
// run_structural_search(problem,budget,candidate_sink)
}
