#!/usr/bin/env python3
import argparse,json,hashlib
from pathlib import Path
ap=argparse.ArgumentParser();ap.add_argument('--cases',type=Path,required=True);ap.add_argument('--outputs',type=Path,required=True);args=ap.parse_args()
results=[]
for case in sorted(args.cases.glob('*.txt')):
 net=next(args.outputs.glob(case.stem+'*'),None)
 if net is None:raise RuntimeError('missing output '+case.name)
 words=case.read_text().split();n,m=map(int,words[:2]);rows=1<<n;expected=words[2:2+rows]
 mask=(1<<rows)-1;vals=[0]
 for var in range(n):
  block=1<<(n-1-var);vals.append((((1<<block)-1)<<block)*(mask//((1<<(2*block))-1)))
 lines=net.read_text().splitlines();area=0;arrival=[0]*(n+1);costs=list(map(int,words[2+rows:2+rows+6]));ops=['AND2','OR2','NOT']
 for line in lines[:-1]:
  t=line.split();i=int(t[0]);op=t[1];a=int(t[2]);b=int(t[3]) if op!='NOT' else 0
  assert i==len(vals) and a<i and b<i
  k=ops.index(op);area+=costs[2*k];arrival.append(max(arrival[a],arrival[b])+costs[2*k+1])
  vals.append(mask^vals[a] if op=='NOT' else vals[a]&vals[b] if op=='AND2' else vals[a]|vals[b])
 outputs=list(map(int,lines[-1].split()));assert len(outputs)==m
 for j,out in enumerate(outputs):
  target=int.from_bytes(bytes(sum((expected[base+k][j]=='1')<<k for k in range(min(8,rows-base))) for base in range(0,rows,8)),'little')
  assert vals[out]==target,(case.name,j)
 results.append({'case':case.name,'status':'PASS','area':area,'delay':max(arrival[x] for x in outputs),'input_sha256':hashlib.sha256(case.read_bytes()).hexdigest()})
 print(case.name,'PASS',flush=True)
print(json.dumps(results,indent=2))
