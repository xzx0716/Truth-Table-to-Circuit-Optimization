#!/usr/bin/env python3
import argparse,hashlib,json,subprocess,zipfile
from pathlib import Path
ap=argparse.ArgumentParser();ap.add_argument('--name',default='stage1-person-a');args=ap.parse_args()
r=Path(__file__).resolve().parents[1];dist=r/'dist';dist.mkdir(exist_ok=True)
subprocess.run(['python3','tools/export_submission.py','--output','dist/solver.cpp'],cwd=r,check=True)
standalone=dist/'README.md'
standalone.write_text("""# Stage 1: compile and run\n\nUbuntu 22.04 / WSL, GCC with C++17. No external runtime dependencies.\n\n```sh\ng++ -O2 -std=c++17 solver.cpp -o solver\n./solver INPUT_PATH OUTPUT_PATH\n```\n\nREPORT.md contains Method and all25 official case results.\nStage1-Handoff.md explains implementation, experiments and limitations.\nVERSION.json and solver.manifest.json bind the source and package files.\nDEVELOPMENT.md documents the full GitHub checkout; its Makefile/tools commands\napply to the repository checkout, not this standalone package.\n\nDefault sweep preserves all25 delays and reduces area in9 cases.\nFive measured rounds:125/125 PASS; no hidden-case/global optimum claim.\n""",encoding='utf-8')
files={'solver.cpp':dist/'solver.cpp','README.md':standalone,'DEVELOPMENT.md':r/'README.md',
 'REPORT.md':r/'docs/stage1-report.md','Stage1-Handoff.md':r/'docs/Stage1-Handoff.md',
 'solver.manifest.json':dist/'solver.manifest.json'}
for folder in ['A-20261117-final-calibrated','A-20261117-final','A-20261117-formal']:
 for name in ['runs.csv','summary.csv','manifest.json','strategy_summary.json']:
  p=r/'results'/folder/name
  if p.exists():files['results/'+folder+'/'+name]=p
manifest={'commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=r,text=True).strip(),
 'files':{name:hashlib.sha256(p.read_bytes()).hexdigest() for name,p in files.items()},
 'compile':'g++ -O2 -std=c++17 solver.cpp -o solver'}
(dist/'VERSION.json').write_text(json.dumps(manifest,indent=2)+'\n');files['VERSION.json']=dist/'VERSION.json'
zip_path=dist/(args.name+'.zip')
with zipfile.ZipFile(zip_path,'w',zipfile.ZIP_DEFLATED) as z:
 for name,p in files.items():z.write(p,name)
(dist/(args.name+'.sha256')).write_text(hashlib.sha256(zip_path.read_bytes()).hexdigest()+'  '+zip_path.name+'\n')
print(zip_path)
