#!/usr/bin/env python3
import subprocess,os,json
from pathlib import Path
root=Path(__file__).resolve().parents[1]
out=root/'results'/'A-20261117-correctness';out.mkdir(parents=True,exist_ok=True)
records=[]
for strategy in ['baseline','greedy','beam','anneal','multistart']:
 env=dict(os.environ,TTC_STRATEGY=strategy,TTC_REGIONS='16',TTC_SEARCH_MS='20')
 p=subprocess.run(['python3','tests/verify_solver.py','build/solver','--no-stats'],cwd=root,env=env,capture_output=True,text=True)
 (out/(strategy+'.log')).write_text(p.stdout+p.stderr)
 records.append({'strategy':strategy,'returncode':p.returncode,'output':p.stdout+p.stderr})
 print(strategy,p.returncode,p.stdout.strip(),flush=True)
 if p.returncode:break
(out/'summary.json').write_text(json.dumps(records,indent=2)+'\n')
raise SystemExit(any(r['returncode'] for r in records))
