#!/usr/bin/env python3
"""Bounded exact AND2/OR2/NOT synthesis: real CNF-SAT and MILP backends.

Single output, arbitrary positive gate costs, all truth-table rows. Connections
only reference primary inputs, constant zero, or previous gate positions.
Optimality claims always include max_gates, area/delay bounds and timeout.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import threading
import time
from dataclasses import dataclass
from pathlib import Path

OPS = ("AND2", "OR2", "NOT")

@dataclass
class Case:
    n: int
    truth: list[int]
    costs: list[tuple[int, int]]
    target: int

    @classmethod
    def read(cls, path):
        words = Path(path).read_text().split()
        n, m = map(int, words[:2])
        if m != 1:
            raise ValueError("exact research prototype requires one output")
        rows = 1 << n
        truth = list(map(int, words[2:2+rows]))
        cost_words = list(map(int, words[2+rows:2+rows+6]))
        costs = list(zip(cost_words[::2], cost_words[1::2]))
        if any(x not in (0, 1) for x in truth) or any(min(c) <= 0 for c in costs):
            raise ValueError("invalid table or costs")
        return cls(n, truth, costs, int(words[2+rows+6]))

class CNF:
    def __init__(self):
        self.nv = 0
        self.clauses = []
    def var(self):
        self.nv += 1
        return self.nv
    def add(self, *clause):
        self.clauses.append(list(clause))
    def one(self, variables):
        self.clauses.append(list(variables))
        for i, a in enumerate(variables):
            for b in variables[i+1:]:
                self.add(-a, -b)

class Encoding:
    def __init__(self, case, gates, delay_bound=None):
        self.case, self.gates = case, gates
        self.cnf = c = CNF()
        self.options = []
        self.types = []
        self.values = [[c.var() for _ in case.truth] for _ in range(case.n+1+gates)]
        for row in range(len(case.truth)):
            c.add(-self.values[0][row])
            for j in range(case.n):
                value = (row >> (case.n-1-j)) & 1
                c.add(self.values[j+1][row] if value else -self.values[j+1][row])
        for i in range(gates):
            dest = case.n+1+i
            options = []
            types = [c.var() for _ in OPS]
            for op in range(3):
                op_vars = []
                for a in range(dest):
                    bs = [0] if op == 2 else range(a, dest)
                    for b in bs:
                        v = c.var()
                        options.append((v, op, a, b))
                        op_vars.append(v)
                        c.add(-v, types[op])
                        for row in range(len(case.truth)):
                            x, y, z = self.values[a][row], self.values[b][row], self.values[dest][row]
                            if op == 0:
                                c.add(-v, -z, x); c.add(-v, -z, y); c.add(-v, z, -x, -y)
                            elif op == 1:
                                c.add(-v, z, -x); c.add(-v, z, -y); c.add(-v, -z, x, y)
                            else:
                                c.add(-v, z, x); c.add(-v, -z, -x)
                c.add(-types[op], *op_vars)
            c.one([x[0] for x in options])
            self.options.append(options)
            self.types.append(types)
        self.outputs = [c.var() for _ in self.values]
        c.one(self.outputs)
        for source, selected in enumerate(self.outputs):
            for row, expected in enumerate(case.truth):
                c.add(-selected, self.values[source][row] if expected else -self.values[source][row])
        if delay_bound is not None:
            self.add_timing(delay_bound)

    def add_timing(self, bound):
        # within[s][t] means that signal s is required to arrive no later than t.
        # Only the implication direction is needed: an output requirement recursively
        # propagates down its selected gates, reaching impossible negative budgets.
        c, case = self.cnf, self.case
        within = [[c.var() for _ in range(bound+1)] for _ in self.values]
        for s in range(case.n+1):
            for t in range(bound+1): c.add(within[s][t])
        for i, options in enumerate(self.options):
            s = case.n+1+i
            for selected, op, a, b in options:
                d = case.costs[op][1]
                for t in range(bound+1):
                    if t < d:
                        c.add(-selected, -within[s][t])
                    else:
                        c.add(-selected, -within[s][t], within[a][t-d])
                        if op != 2: c.add(-selected, -within[s][t], within[b][t-d])
        for source, selected in enumerate(self.outputs):
            c.add(-selected, within[source][bound])

    def area_constraint(self, bound):
        c, start = self.cnf, len(self.cnf.clauses)
        # Reachable-budget automaton. The selected type advances the unique
        # reachable state; no weighted-cardinality plugin is necessary.
        states = {(0, bound): c.var()}
        c.add(states[0, bound])
        for i in range(self.gates):
            for (stage, budget), state in list(states.items()):
                if stage != i: continue
                for op, selected in enumerate(self.types[i]):
                    left = budget-self.case.costs[op][0]
                    if left < 0: c.add(-state, -selected)
                    else:
                        key = (i+1, left)
                        if key not in states: states[key] = c.var()
                        c.add(-state, -selected, states[key])
        return c.clauses[start:]

    def decode(self, selected):
        gates = []
        for options in self.options:
            v, op, a, b = next(x for x in options if x[0] in selected)
            gates.append((op, a, b))
        output = next(i for i, v in enumerate(self.outputs) if v in selected)
        return compact(self.case, gates, output)

def compact(case, gates, output):
    used = set()
    def visit(i):
        if i <= case.n or i in used: return
        used.add(i)
        op, a, b = gates[i-case.n-1]
        visit(a)
        if op != 2: visit(b)
    visit(output)
    ids = {i:i for i in range(case.n+1)}
    result = []
    for old, (op,a,b) in enumerate(gates, case.n+1):
        if old in used:
            ids[old] = case.n+1+len(result)
            result.append((op, ids[a], ids[b] if op != 2 else 0))
    return result, ids[output]

def evaluate(case, netlist):
    gates, output = netlist
    arrival = [0]*(case.n+1)
    for op,a,b in gates:
        arrival.append(max(arrival[a], arrival[b] if op != 2 else 0)+case.costs[op][1])
    for row, expected in enumerate(case.truth):
        values = [0]+[(row >> (case.n-1-j)) & 1 for j in range(case.n)]
        for op,a,b in gates:
            values.append((values[a]&values[b]) if op == 0 else (values[a]|values[b]) if op == 1 else 1-values[a])
        if values[output] != expected: raise AssertionError("decoded circuit is incorrect")
    return {"area":sum(case.costs[op][0] for op,_,_ in gates), "delay":arrival[output], "gates":len(gates)}

def netlist_text(case, netlist):
    gates, output = netlist
    lines = []
    for i,(op,a,b) in enumerate(gates,case.n+1):
        lines.append(f"{i} {OPS[op]} {a}"+(f" {b}" if op != 2 else ""))
    return "\n".join(lines+[str(output)])+"\n"

def sat_once(case, gates, bound, delay, seconds):
    from pysat.solvers import Solver
    enc = Encoding(case, gates, delay)
    enc.area_constraint(bound)
    start = time.perf_counter()
    with Solver(name="g3", bootstrap_with=enc.cnf.clauses) as solver:
        # Native interrupt is raised by a timer thread, not a deferred Python
        # signal handler. This thread does no solving; the solver stays single-threaded.
        timer = threading.Timer(max(.001, seconds), solver.interrupt)
        timer.daemon = True
        timer.start()
        try:
            feasible = solver.solve_limited(expect_interrupt=True)
            model = solver.get_model() if feasible else None
        finally:
            timer.cancel()
            timer.join()
    status = "SAT" if feasible else "UNSAT" if feasible is False else "TIMEOUT"
    result = {"status":status,"gates_bound":gates,"area_bound":bound,
              "delay_bound":delay,"variables":enc.cnf.nv,"clauses":len(enc.cnf.clauses),
              "solve_ms":(time.perf_counter()-start)*1000}
    return result, enc.decode({x for x in model if x > 0}) if model else None

def milp_once(case, gates, delay, seconds, area_bound=None):
    import numpy as np
    from scipy.optimize import Bounds, LinearConstraint, milp
    from scipy.sparse import coo_matrix
    # CNF truth constraints become exact 0/1 linear inequalities. Arrival-time
    # constraints are continuous: positive gate delays plus DAG ensure correctness.
    enc = Encoding(case, gates)
    binary_n = enc.cnf.nv
    nvars = binary_n+len(enc.values)
    rr,cc,vv,lower,upper = [],[],[],[],[]
    def constraint(coeff, lo, hi):
        row = len(lower)
        for j,v in coeff.items():
            if v: rr.append(row); cc.append(j); vv.append(v)
        lower.append(lo); upper.append(hi)
    for clause in enc.cnf.clauses:
        coeff = {}
        neg = 0
        for lit in clause:
            j = abs(lit)-1
            coeff[j] = coeff.get(j,0)+(1 if lit>0 else -1)
            neg += lit<0
        constraint(coeff,1-neg,np.inf)
    objective = np.zeros(nvars)
    max_arrival = gates*max(d for _,d in case.costs)
    big = max_arrival+max(d for _,d in case.costs)+1
    for i, options in enumerate(enc.options):
        dest = case.n+1+i
        for selected, op,a,b in options:
            objective[selected-1] = case.costs[op][0]
            for src in [a] if op == 2 else [a,b]:
                constraint({binary_n+dest:1,binary_n+src:-1,selected-1:-big},case.costs[op][1]-big,np.inf)
    if delay is not None:
        for src,selected in enumerate(enc.outputs):
            constraint({binary_n+src:1,selected-1:big},-np.inf,delay+big)
    if area_bound is not None:
        constraint({i:float(v) for i,v in enumerate(objective) if v},-np.inf,area_bound)
    lb = np.zeros(nvars); ub = np.ones(nvars)
    ub[binary_n:] = max_arrival
    ub[binary_n:binary_n+case.n+1] = 0
    matrix = coo_matrix((vv,(rr,cc)),shape=(len(lower),nvars)).tocsc()
    matrix.indices = matrix.indices.astype(np.int32); matrix.indptr = matrix.indptr.astype(np.int32)
    start = time.perf_counter()
    result = milp(objective, integrality=np.r_[np.ones(binary_n),np.zeros(len(enc.values))],
                  bounds=Bounds(lb,ub),constraints=LinearConstraint(matrix,lower,upper),
                  options={"time_limit":max(.001,seconds),"mip_rel_gap":0.0,"threads":1})
    status = {0:"OPTIMAL",1:"TIMEOUT",2:"UNSAT",3:"UNBOUNDED"}.get(result.status,"ERROR")
    netlist = enc.decode({i+1 for i,x in enumerate(result.x[:binary_n]) if x>.5}) if result.x is not None else None
    record = {"status":status,"gates_bound":gates,"delay_bound":delay,"area_bound":area_bound,
              "variables":nvars,"constraints":len(lower),"solve_ms":(time.perf_counter()-start)*1000,
              "message":result.message,"mip_gap":float(result.mip_gap) if getattr(result,"mip_gap",None) is not None else None}
    return record, netlist

def synthesize(case, backend, max_gates, seconds=10, delay=None):
    started = time.perf_counter()
    deadline = started+seconds
    best, best_metrics, attempts = None, None, []
    complete = True
    for gates in range(max_gates+1):
        if time.perf_counter()>=deadline:
            complete = False; break
        if backend == "milp":
            record, candidate = milp_once(case,gates,delay,deadline-time.perf_counter())
            attempts.append(record)
            if candidate is not None:
                metrics = evaluate(case,candidate)
                if best is None or (metrics["area"],metrics["delay"])<(best_metrics["area"],best_metrics["delay"]):
                    best,best_metrics = candidate,metrics
            if record["status"] not in ("OPTIMAL","UNSAT"): complete = False; break
        else:
            # Tighten area bound until UNSAT for each exact slot count. Positive
            # gate costs make any better circuit have a representation in 0..K.
            bound = gates*max(a for a,_ in case.costs)
            if best_metrics is not None: bound = min(bound,best_metrics["area"]-1)
            while bound>=0 and time.perf_counter()<deadline:
                record,candidate = sat_once(case,gates,bound,delay,deadline-time.perf_counter())
                attempts.append(record)
                if candidate is None:
                    if record["status"] != "UNSAT": complete = False
                    break
                metrics = evaluate(case,candidate)
                if best is None or (metrics["area"],metrics["delay"])<(best_metrics["area"],best_metrics["delay"]):
                    best,best_metrics = candidate,metrics
                bound = metrics["area"]-1
            if time.perf_counter()>=deadline: complete = False; break
        if best_metrics is not None and best_metrics["area"] == 0: break
    report = {"backend":backend,"n":case.n,"max_gates":max_gates,"delay_bound":delay,
              "elapsed_ms":(time.perf_counter()-started)*1000,"complete":complete,
              "status":("BOUNDED_OPTIMAL" if complete else "FEASIBLE_NOT_PROVEN") if best is not None else ("BOUNDED_UNSAT" if complete else "TIMEOUT_UNKNOWN"),
              "metrics":best_metrics,"attempts":attempts,
              "scope":"minimum area among circuits with at most max_gates slots and specified delay bound; no global claim beyond that space"}
    return report,best

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("backend",choices=["sat","milp"]); ap.add_argument("input",type=Path)
    ap.add_argument("--max-gates",type=int,default=4); ap.add_argument("--seconds",type=float,default=10)
    ap.add_argument("--delay",type=int); ap.add_argument("--output",type=Path); ap.add_argument("--report",type=Path)
    args = ap.parse_args()
    if args.max_gates < 0 or args.seconds <= 0 or (args.delay is not None and args.delay < 0):
        ap.error("gate/delay bounds must be nonnegative; seconds must be positive")
    case = Case.read(args.input)
    report,netlist = synthesize(case,args.backend,args.max_gates,args.seconds,args.delay)
    report["source_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    report["input_sha256"] = hashlib.sha256(args.input.read_bytes()).hexdigest()
    if netlist is not None and args.output: args.output.write_text(netlist_text(case,netlist))
    text = json.dumps(report,indent=2,allow_nan=True)
    if args.report: args.report.write_text(text+"\n")
    print(text)
if __name__ == "__main__": main()
