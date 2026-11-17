#!/usr/bin/env python3
import subprocess,os,json,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
mode=sys.argv[1] if len(sys.argv)>1 else 'scale'
variants={
 'scale':{
  'cut2':{'TTC_STRATEGY':'greedy','TTC_CUT':'2','TTC_SEARCH_MS':'100','TTC_ROUNDS':'2'},
  'cut4':{'TTC_STRATEGY':'greedy','TTC_CUT':'4','TTC_SEARCH_MS':'200','TTC_ROUNDS':'4'},
  'cut6':{'TTC_STRATEGY':'beam','TTC_CUT':'6','TTC_SEARCH_MS':'400','TTC_ROUNDS':'8','TTC_BEAM':'8'},
  'cut8':{'TTC_STRATEGY':'multistart','TTC_CUT':'8','TTC_SEARCH_MS':'800','TTC_ROUNDS':'8','TTC_RESTARTS':'8'},
  'cut10':{'TTC_STRATEGY':'anneal','TTC_CUT':'10','TTC_SEARCH_MS':'1600','TTC_ROUNDS':'16'},
  'portfolio':{'TTC_STRATEGY':'portfolio','TTC_CUT':'6','TTC_SEARCH_MS':'2000','TTC_ROUNDS':'8','TTC_BEAM':'8','TTC_RESTARTS':'8'},
 },
 'formal':{
  'baseline':{'TTC_STRATEGY':'baseline'},
  'algebraic':{'TTC_STRATEGY':'greedy','TTC_CUT':'0','TTC_SEARCH_MS':'15','TTC_ROUNDS':'2'},
  'adaptive':{'TTC_STRATEGY':'portfolio','TTC_CUT':'4','TTC_SEARCH_MS':'30','TTC_ROUNDS':'3'},
 }
}[mode]
cmd=['python3','tools/run_experiments.py','--out',f'results/A-20261117-{mode}',
 '--rounds','5' if mode=='formal' else '1','--warmup','1' if mode=='formal' else '0',
 '--save-outputs','--build-command','make']
for name,env in variants.items():
 cmd+=['--solver',name+'=build/solver']
 if mode=='scale':env['TTC_RESEARCH_MS']='5000'
 for k,v in env.items():cmd+=['--env',name+':'+k+'='+v]
jsondir=root/'configs';jsondir.mkdir(exist_ok=True)
(jsondir/(mode+'.json')).write_text(json.dumps(variants,indent=2)+'\n')
raise SystemExit(subprocess.call(cmd,cwd=root))
