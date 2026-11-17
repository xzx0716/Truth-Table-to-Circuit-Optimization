#!/usr/bin/env python3
"""Meaningful regression tests for both exact synthesis encodings."""
import importlib.util
import sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'research/exact'))
from synthesize import Case, synthesize, sat_once, milp_once, evaluate

def check():
    costs=[(2,2),(8,3),(1,1)]
    micro=[
        ('constant-zero',Case(2,[0]*4,costs,10),0,0),
        ('constant-one',Case(2,[1]*4,costs,10),1,1),
        ('input',Case(2,[0,1,0,1],costs,10),0,0),
        ('and',Case(2,[0,0,0,1],costs,10),1,2),
        ('or-direct',Case(2,[0,1,1,1],costs,3),1,8),
        ('or-demorgan',Case(2,[0,1,1,1],costs,10),4,5),
        ('factor',Case(3,[int(((i>>2)&1) and (((i>>1)&1) or (i&1))) for i in range(8)],[(1,1)]*3,10),2,2),
    ]
    for backend in ('sat','milp'):
        for name,case,gates,expected in micro:
            report,net=synthesize(case,backend,gates,20,case.target)
            assert net is not None,(backend,name,report)
            assert report['status']=='BOUNDED_OPTIMAL',(backend,name,report)
            assert report['metrics']['area']==expected,(backend,name,report)
            assert report['metrics']['delay']<=case.target
            print(backend,name,report['metrics'],round(report['elapsed_ms'],2))
    # AND cannot be implemented with no gates, nor below its one-gate delay.
    case=Case(2,[0,0,0,1],costs,1)
    for backend in ('sat','milp'):
        report,net=synthesize(case,backend,2,10,1)
        assert net is None and report['status']=='BOUNDED_UNSAT',(backend,report)
    # Exhaust all sixteen two-input functions, arbitrary asymmetric costs.
    for pattern in range(16):
        case=Case(2,[(pattern>>i)&1 for i in range(4)],[(2,1),(3,2),(1,1)],10)
        a,an=synthesize(case,'sat',4,10,10)
        b,bn=synthesize(case,'milp',4,10,10)
        assert an is not None and bn is not None,(pattern,a,b)
        assert a['status']==b['status']=='BOUNDED_OPTIMAL',(pattern,a,b)
        assert a['metrics']['area']==b['metrics']['area'],(pattern,a,b)
    print('PASS: both encodings, known bounds, all 16 two-input functions')
if __name__=='__main__':check()
