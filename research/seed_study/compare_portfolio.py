"""Compare the selected one-process portfolio with the production solver."""
import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

from analyze import write_rows


def compare(out):
    with (out/'runs.csv').open() as f:
        raw = [r for r in csv.DictReader(f) if int(r['round']) > 0]
    groups = defaultdict(list)
    for row in raw:
        groups[row['case'],row['profile']].append(row)
    rows = []
    summary = Counter()
    for name in sorted({r['case'] for r in raw}):
        row = {'case': name}
        for profile, label in [('deployed','default'), ('retained-portfolio','portfolio')]:
            values = groups[name,profile]
            valid = [r for r in values if r['status']=='PASS']
            row[label+'_pass'] = len(valid)
            row[label+'_on_target'] = sum(r['target_met'].lower()=='yes' for r in valid)
            summary[label+'_passes'] += row[label+'_pass']
            summary[label+'_on_target'] += row[label+'_on_target']
            ad = {(int(r['area']),int(r['delay'])) for r in valid}
            row[label+'_distinct_outputs'] = len({r['netlist_sha256'] for r in valid})
            row[label+'_ad_pairs'] = ' | '.join(f'{a}/{d}' for a,d in sorted(ad))
            row[label+'_median_ms'] = median(float(r['runtime_ms']) for r in valid) if valid else ''
            row[label+'_stable'] = int(len(ad)==1 and len(valid)==len(values))
        row['ad_change'] = 'unstable or failed'
        if row['default_stable'] and row['portfolio_stable']:
            a,d=map(int,row['default_ad_pairs'].split('/'))
            b,e=map(int,row['portfolio_ad_pairs'].split('/'))
            if (a,d)==(b,e):
                row['ad_change']='same'
            elif b<=a and e<=d:
                row['ad_change']='better'
            elif a<=b and d<=e:
                row['ad_change']='worse'
            else:
                row['ad_change']='tradeoff'
        summary[row['ad_change']] += 1
        rows.append(row)
    write_rows(out/'comparison.csv',rows)
    for k in ['default', 'portfolio']:
        if all(r[k+'_stable'] for r in rows):
            summary[k+'_sum_case_median_ms'] = round(sum(r[k+'_median_ms'] for r in rows),3)
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    return summary


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out',type=Path)
    print(json.dumps(compare(parser.parse_args().out),indent=2))
