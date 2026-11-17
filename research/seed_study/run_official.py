"""Compare initial constructions with the course Linux evaluator. Run on Linux x86-64."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import shutil
import subprocess
import tempfile
from time import strftime, gmtime

from run import PROFILES


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def evaluate(args):
    root = Path(__file__).resolve().parents[2]
    out = args.out.resolve()
    out.mkdir(exist_ok=True, parents=True)
    if any(out.iterdir()):
        raise ValueError("choose an empty result directory")
    retained = None
    profiles = [*PROFILES, 'deployed']
    if args.portfolio:
        retained = json.loads(args.portfolio.read_text())
        if not retained or len(set(retained)) != len(retained) or not set(retained) <= set(PROFILES):
            raise ValueError('invalid list of retained seed profiles')
        profiles = ['retained-portfolio', 'deployed']
    source_paths = [root / 'Makefile', *sorted((root / 'include').rglob('*.hpp')),
                    *sorted((root / 'src').rglob('*.cpp')), Path(__file__), Path(__file__).with_name('run.py')]
    source_hashes = {str(p.relative_to(root)): sha(p) for p in source_paths}
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        cases = work / 'cases'
        shutil.copytree(args.cases, cases)
        inputs = sorted(cases.glob('*.txt'))
        if not inputs:
            raise ValueError('empty case folder')
        targets = {}
        for case in inputs:
            with case.open('rb') as f:
                for _ in range(6):
                    f.readline()
                targets[case.name] = int(f.readline())
        evaluator = work / 'evaluator'
        shutil.copyfile(args.evaluator, evaluator)
        evaluator.chmod(0o755)
        binary = work / 'solver'
        command = ['g++', '-O2', '-std=c++17', '-Wall', '-Wextra', '-Wpedantic', '-Iinclude',
                   'src/main.cpp', *sorted(str(p.relative_to(root)) for p in (root / 'src/optimization').glob('*.cpp')), '-o', str(binary)]
        subprocess.run(command, cwd=root, check=True)
        manifest = dict(base=args.base, host=platform.uname()._asdict(), environment=args.machine,
                        compiler=subprocess.check_output(['g++','--version'],text=True).splitlines()[0],
                        build=command, solver_sha256=sha(binary), sources=source_hashes,
                        inputs={p.name:sha(p) for p in inputs}, evaluator_sha256=sha(evaluator),
                        rounds=args.rounds, warmup=1, shuffle_seed=2106, profiles=profiles,
                        retained_in_order=retained,
                        measured_metric='Official evaluator runtime_ms from solver startup to exit',
                        controlled_post='normalize + one complete existing algebraic sweep + common selection',
                        production_reference='deployed uses all original default settings',
                        started=strftime('%Y-%m-%d %H:%M:%S UTC', gmtime()))
        (out / 'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
        (out / 'raw').mkdir()
        fields = ['round','sequence','case','profile','status','area','delay','target','target_met','runtime_ms','netlist_sha256','reason']
        rng = random.Random(2106)
        with (out/'runs.csv').open('w',newline='') as f:
            writer=csv.DictWriter(f,fields)
            writer.writeheader()
            for iteration in range(args.rounds+1):
                order = profiles.copy()
                rng.shuffle(order)
                for sequence, profile in enumerate(order,1):
                    report = out/'raw'/f'{iteration}-{profile}.csv'
                    env = {k:v for k,v in os.environ.items() if not k.startswith('TTC_')}
                    if profile=='retained-portfolio':
                        env['TTC_INITIAL_SEEDS'] = ','.join(retained)
                    elif profile!='deployed':
                        env['TTC_INITIAL_SEED'] = profile
                    with tempfile.TemporaryDirectory(dir=work) as buf:
                        saved=Path(buf)/'circuits'
                        cmd=[evaluator,binary,cases,'--report',report,'--save-outputs',saved]
                        completed=subprocess.run(cmd,cwd=work,env=env,capture_output=True,text=True)
                        if not report.is_file():
                            raise RuntimeError(str(cmd)+' '+completed.stderr[-800:])
                        with report.open() as r:
                            measured={row['case']:row for row in csv.DictReader(r)}
                        if measured.keys()!=targets.keys():
                            raise RuntimeError('official case list mismatch')
                        files=list(saved.rglob('*'))
                        for name, row in measured.items():
                            key=Path(name).stem
                            matches=[p for p in files if p.is_file() and (p.name==key or p.name.startswith(key+'.') or p.name.startswith(key+'_'))]
                            if row['status']=='PASS' and len(matches)!=1:
                                raise RuntimeError(f'cannot identify saved netlist for {key}: {[str(p.relative_to(saved)) for p in files][:6]}')
                            writer.writerow(dict(round=iteration,sequence=sequence,case=name,profile=profile,status=row['status'],
                                area=row['area'],delay=row['delay'],target=targets[name],target_met=row['target_met'],
                                runtime_ms=row['runtime_ms'],netlist_sha256=sha(matches[0]) if len(matches)==1 else '',
                                reason=row.get('reason','')))
                        f.flush()
                    print(iteration,profile,sum(row['status']=='PASS' for row in measured.values()),flush=True)
        if source_hashes!={str(p.relative_to(root)):sha(p) for p in source_paths}:
            raise RuntimeError('source files changed during experiment')
        manifest['finished']=strftime('%Y-%m-%d %H:%M:%S UTC',gmtime())
        (out/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cases',type=Path,required=True)
    p.add_argument('--evaluator',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--base',required=True)
    p.add_argument('--machine',default=platform.platform())
    p.add_argument('--rounds',type=int,default=5)
    p.add_argument('--portfolio',type=Path,help='time the retained portfolio in one process against the deployed default')
    evaluate(p.parse_args())
