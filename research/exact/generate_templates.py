#!/usr/bin/env python3
"""Generate a generic two-input truth-function library, never public-case answers."""
import argparse
import hashlib
import json
from pathlib import Path
from synthesize import Case,synthesize,netlist_text

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,default=Path(__file__).with_name('generic_templates.json'));ap.add_argument('--max-gates',type=int,default=4);args=ap.parse_args()
    templates=[]
    for pattern in range(16):
        truth=[(pattern>>i)&1 for i in range(4)]
        case=Case(2,truth,[(1,1)]*3,10)
        frontier=[]
        for delay in (1,2,3,4):
            report,net=synthesize(case,'sat',args.max_gates,10,delay)
            entry={'pattern_lsb_row0':pattern,'truth':truth,'delay_bound':delay,'status':report['status'],'metrics':report['metrics'],'attempts':report['attempts']}
            if net is not None:entry['netlist']=netlist_text(case,net)
            templates.append(entry)
    result={'purpose':'generic two-input AND2/OR2/NOT replacement candidates, independent of public cases','costs':[(1,1)]*3,'max_gates':args.max_gates,'source_sha256':hashlib.sha256(Path(__file__).with_name('synthesize.py').read_bytes()).hexdigest(),'records':templates}
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print('saved',len(templates),'bounded queries',args.output)
if __name__=='__main__':main()
