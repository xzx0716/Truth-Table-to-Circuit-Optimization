#!/usr/bin/env python3
import argparse,hashlib,json,subprocess,zipfile
from pathlib import Path
ap=argparse.ArgumentParser();ap.add_argument('--name',default='stage1-final');args=ap.parse_args()
r=Path(__file__).resolve().parents[1];dist=r/'dist';dist.mkdir(exist_ok=True)
subprocess.run(['python3','tools/export_submission.py','--output','dist/solver.cpp'],cwd=r,check=True)
standalone=dist/'README.md'
standalone.write_text("""# Stage 1: compile and run

Ubuntu 22.04 / WSL, GCC with C++17. No external runtime dependencies.

```sh
g++ -O2 -std=c++17 solver.cpp -o solver
./solver INPUT_PATH OUTPUT_PATH
```

No environment variables are needed. The compiled default is the budgeted
nine-seed portfolio. It is sequential and uses one CPU thread.

REPORT.pdf / REPORT.md describe the Method and every released case's
pass/fail, area, delay and runtime. Five measured rounds: 125/125 PASS,
all target delays met. Standalone validation, including an initial timeout and complete repeat runs,
is documented in the report and preserved result folders.
Area/delay improve together in 8 cases, match in 7, and trade off in 10;
the portfolio increases runtime. No hidden-case/global optimum claim.

Stage1-Handoff.md explains integration, experiments and limitations in Chinese.
VERSION.json and solver.manifest.json bind the source and package files.
DEVELOPMENT.md describes the full GitHub checkout; Makefile/tools commands
there apply to the repository checkout, not this standalone package.
Official inputs/evaluator are not redistributed. GitHub is not the course
submission platform: submit the source, README and report by the course channel.
""",encoding='utf-8')
files={'solver.cpp':dist/'solver.cpp','README.md':standalone,'DEVELOPMENT.md':r/'README.md',
 'REPORT.md':r/'docs/stage1-report.md','REPORT.pdf':r/'output/pdf/stage1-report.pdf',
 'Stage1-Handoff.md':r/'docs/Stage1-Handoff.md',
 'solver.manifest.json':dist/'solver.manifest.json'}
for folder in ['stage1-final-20261118','stage1-standalone-20261118','stage1-standalone-repeat-20261118']:
 for name in ['runs.csv','summary.csv','manifest.json','strategy_summary.json','final_comparison.csv','rss_probes.csv','report-summary.json','verification.json']:
  p=r/'results'/folder/name
  if p.exists():files['results/'+folder+'/'+name]=p
 for p in sorted((r/'results'/folder/'raw').glob('*.csv')):
  files['results/'+folder+'/raw/'+p.name]=p
manifest={'commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=r,text=True).strip(),
 'files':{name:hashlib.sha256(p.read_bytes()).hexdigest() for name,p in files.items()},
 'compile':'g++ -O2 -std=c++17 solver.cpp -o solver'}
(dist/'VERSION.json').write_text(json.dumps(manifest,indent=2)+'\n');files['VERSION.json']=dist/'VERSION.json'
zip_path=dist/(args.name+'.zip')
with zipfile.ZipFile(zip_path,'w',zipfile.ZIP_DEFLATED) as z:
 for name,p in files.items():z.write(p,name)
(dist/(args.name+'.sha256')).write_text(hashlib.sha256(zip_path.read_bytes()).hexdigest()+'  '+zip_path.name+'\n')
print(zip_path)
