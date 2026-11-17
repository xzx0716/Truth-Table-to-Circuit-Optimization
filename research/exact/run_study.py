#!/usr/bin/env python3
"""Reproducible bounded-exact scaling and public-circuit local-cut study."""
import argparse
import hashlib
import json
import platform
import sys
import time
from pathlib import Path
from synthesize import Case, synthesize, evaluate, netlist_text
ROOT=Path(__file__).resolve().parents[2]

def local_case(path,casepath,depth=2):
    words=casepath.read_text().split(); n,m=map(int,words[:2]); costs=list(map(int,words[2+(1<<n):2+(1<<n)+6])); costs=list(zip(costs[::2],costs[1::2]))
    lines=path.read_text().splitlines(); gates={}
    for line in lines[:-1]:
        w=line.split(); gates[int(w[0])]=(w[1],list(map(int,w[2:])))
    outputs=list(map(int,lines[-1].split()))
    root=next((x for x in reversed(outputs) if x>n),None)
    if root is None: return None,None
    interior=set(); leaves=set()
    def collect(x,d):
        if x==0: return
        if x<=n or d==0: leaves.add(x); return
        if x in interior:return
        interior.add(x)
        for c in gates[x][1]:collect(c,d-1)
    collect(root,depth)
    leaves-=interior; leaves=sorted(leaves)
    if not leaves: return None,None
    ids={x:i for i,x in enumerate(leaves)}
    truth=[]
    for row in range(1<<len(leaves)):
        memo={0:0,**{x:(row>>(len(leaves)-1-i))&1 for x,i in ids.items()}}
        def value(x):
            if x in memo:return memo[x]
            op,ch=gates[x]; a=value(ch[0]); b=value(ch[1]) if len(ch)>1 else 0
            memo[x]=a&b if op=='AND2' else a|b if op=='OR2' else 1-a
            return memo[x]
        truth.append(value(root))
    return Case(len(leaves),truth,costs,1000),{'source_output':root,'boundary_signals':leaves,'interior_gates':len(interior)}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,default=ROOT/'research/exact/results');ap.add_argument('--seconds',type=float,default=1.0); args=ap.parse_args()
    out=args.output;out.mkdir(parents=True,exist_ok=True)
    records=[]
    # True resource curve: increasingly difficult parity functions with limited gates.
    for n in (2,3,4,5):
        case=Case(n,[i.bit_count()%2 for i in range(1<<n)],[(1,1)]*3,30)
        for k in (2,4,6):
            for backend in ('sat','milp'):
                report,net=synthesize(case,backend,k,args.seconds,30)
                report.update(experiment='parity-scale',function=f'parity{n}',gate_limit=k)
                if net is not None:(out/f'parity{n}-{k}-{backend}.net').write_text(netlist_text(case,net))
                records.append(report);(out/'study.json').write_text(json.dumps(records,indent=2)+'\n')
                print('scale',n,k,backend,report['status'],round(report['elapsed_ms'],1),flush=True)
    for path in sorted((ROOT/'artifacts/baseline/circuits').glob('case_*.output.txt')):
        casepath=ROOT/'data/local/stage1'/path.name.replace('.output.txt','.txt')
        case,cut=local_case(path,casepath)
        if case is None:continue
        # All public cases contribute a genuine local function; no public answer table is used.
        for backend in ('sat','milp'):
            report,net=synthesize(case,backend,cut['interior_gates'],args.seconds,None)
            report.update(experiment='public-local-cut',case=casepath.name,cut=cut,input_sha256=hashlib.sha256(casepath.read_bytes()).hexdigest(),source_netlist_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            if net is not None:(out/f'{casepath.stem}-{backend}.net').write_text(netlist_text(case,net))
            records.append(report);(out/'study.json').write_text(json.dumps(records,indent=2)+'\n')
            print('cut',casepath.stem,case.n,backend,report['status'],round(report['elapsed_ms'],1),flush=True)
    import pysat,scipy,numpy
    manifest={'python':sys.version,'platform':platform.platform(),'versions':{'python-sat':pysat.__version__,'scipy':scipy.__version__,'numpy':numpy.__version__},'source_sha256':hashlib.sha256((ROOT/'research/exact/synthesize.py').read_bytes()).hexdigest(),'run_study_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'command':'OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 research/exact/run_study.py --seconds '+str(args.seconds),'record_count':len(records)}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
if __name__=='__main__':main()
