#!/usr/bin/env python3
import os,subprocess,csv,json,statistics
from pathlib import Path
r=Path(__file__).resolve().parents[1]
out=r/'results/A-20261117-cost-model-calibrated';out.mkdir(parents=True,exist_ok=True)
a=r/'artifacts/A-20261117-cost-model-calibrated';a.mkdir(parents=True,exist_ok=True)
log=a/'costs.csv';front=a/'frontier.csv'
records=[]
for case in sorted((r/'data/local/stage1').glob('*.txt')):
 env={k:v for k,v in os.environ.items() if not k.startswith('TTC_')}
 env.update(TTC_STRATEGY='portfolio',TTC_SEARCH_MS='100',TTC_CUT='4',
 TTC_COST_LOG=str(log),TTC_FRONTIER_LOG=str(front))
 with (a/(case.stem+'.stderr')).open('w') as err:
  p=subprocess.run([str(r/'build/solver'),str(case),str(a/(case.stem+'.net'))],env=env,stderr=err,timeout=15)
 records.append({'case':case.name,'returncode':p.returncode})
raw=list(csv.reader(log.open()))
summary=[]
for op in sorted(set(x[2] for x in raw)):
 rows=[x for x in raw if x[2]==op and float(x[4])>0]
 ratios=[float(x[5])/float(x[4]) for x in rows]
 errors=[abs(float(x[5])-float(x[4])) for x in rows]
 summary.append({'operation':op,'observations':len(rows),'underestimated':sum(x[6]=='1' for x in rows),
 'median_actual_over_predicted':statistics.median(ratios) if ratios else None,
 'max_actual_over_predicted':max(ratios) if ratios else None,
 'mean_absolute_error_ms':statistics.mean(errors) if errors else None})
(out/'summary.json').write_text(json.dumps({'runs':records,'model':summary},indent=2)+'\n')
# Keep small numerical evidence in git, and raw per-case stderr/netlists in artifacts.
(out/'costs.csv').write_text(log.read_text());(out/'frontier.csv').write_text(front.read_text())
print(json.dumps(summary,indent=2))
