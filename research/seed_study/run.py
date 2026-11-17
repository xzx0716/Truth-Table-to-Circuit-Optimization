#!/usr/bin/env python3
"""Interleave seed profiles, timing the two-path solver until process exit."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import re
import signal
import subprocess
import sys
import tempfile
import time

from analyze import analyze

ROOT = Path(__file__).resolve().parents[2]
PROFILES = ["github", "forward-sop", "reverse-sop", "influence-sop", "forward-pos",
            "forward-demorgan", "forward-top3", "reverse-top3", "forward-rec3", "forward-adaptive3",
            "historical-adaptive"]
FIELDS = ["round", "sequence", "case", "profile", "status", "reason", "seed_area", "seed_delay",
          "area", "delay", "target", "runtime_ms", "limit_ms", "peak_kb", "ram_limit_kb",
          "netlist_sha256"]


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def metadata(path):
    with path.open("rb") as f:
        for _ in range(6):
            f.readline()
        target, limit, ram, *_ = [int(x) for x in f.read().split()] + [0, 0]
    return target, limit, ram


def measure(cmd, env, wall_limit_ms, log):
    # Spawn directly to avoid interpreter overhead inside the measured child.
    actions = [(os.POSIX_SPAWN_OPEN, 1, os.devnull, os.O_WRONLY, 0),
               (os.POSIX_SPAWN_OPEN, 2, str(log), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)]
    start = time.monotonic_ns()
    pid = os.posix_spawn(cmd[0], cmd, env, file_actions=actions, setpgroup=0)
    timed_out = False

    def kill(*args):
        nonlocal timed_out
        timed_out = True
        try:
            os.killpg(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    prev = signal.signal(signal.SIGALRM, kill)
    try:
        remaining = wall_limit_ms / 1000 - (time.monotonic_ns() - start) / 1e9
        if remaining > 0:
            signal.setitimer(signal.ITIMER_REAL, remaining)
        else:
            kill()
        _, status, usage = os.wait4(pid, 0)
        elapsed = (time.monotonic_ns() - start) / 1e6
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, prev)
    rss = int(usage.ru_maxrss)
    if sys.platform == "darwin":
        rss = (rss + 1023) // 1024
    return elapsed, rss, os.waitstatus_to_exitcode(status), timed_out


def trial(solver, checker, case, profile, limits, temp, verified):
    target, limit, ram = limits
    net, log = temp / "candidate.net", temp / "stderr"
    net.unlink(missing_ok=True)
    env = {k: v for k, v in os.environ.items() if not k.startswith("TTC_")}
    env["TTC_INITIAL_SEED"] = profile
    elapsed, rss, rc, expired = measure([str(solver), str(case), str(net)], env,
                                         limit or 120000, log)
    msg = log.read_text(errors="replace")
    fields = dict(re.findall(r"([a-z_]+)=([^\s]+)", msg))
    row = dict(case=case.name, profile=profile, status="FAIL", target=target,
               runtime_ms=f"{elapsed:.4f}", limit_ms=limit, peak_kb=rss, ram_limit_kb=ram,
               seed_area=fields.get("seed_area", ""), seed_delay=fields.get("seed_delay", ""))
    if expired or (limit and elapsed > limit):
        return dict(row, reason="timeout")
    if ram and rss > ram:
        return dict(row, reason="ram limit exceeded")
    if rc == 3 and fields.get("post_complete") == "0":
        return dict(row, status="INCOMPLETE", reason="seed or common downstream work exceeded budget")
    if "seed construction exceeded budget" in msg:
        return dict(row, status="INCOMPLETE", reason="seed construction exceeded budget")
    if rc or not net.is_file():
        return dict(row, reason=msg.strip()[-500:] or f"exit {rc}, missing netlist")
    out_hash = sha(net)
    key = (case, out_hash)
    if key not in verified:
        result = subprocess.run([checker, case, net], capture_output=True, text=True)
        verdict = json.loads(result.stdout)
        if result.returncode == 2:
            raise RuntimeError("checker error: " + str(verdict))
        verified[key] = verdict
    verdict = verified[key]
    row["netlist_sha256"] = out_hash
    if not verdict["correct"]:
        return dict(row, reason=verdict["reason"])
    row.update(area=verdict["area"], delay=verdict["delay"])
    if fields.get("post_complete") != "1":
        return dict(row, status="INCOMPLETE", reason="common downstream work not completed")
    if not row["seed_area"] or not row["seed_delay"]:
        raise RuntimeError("missing seed metrics in solver output: " + msg[-600:])
    if int(fields["area"]) != row["area"] or int(fields["delay"]) != row["delay"]:
        raise RuntimeError("checker and solver metrics disagree")
    return dict(row, status="PASS", reason="")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--solver", type=Path, default=ROOT / "build/solver")
    parser.add_argument("--checker", type=Path, required=True)
    parser.add_argument("--cases", type=Path, default=ROOT / "data/local/stage1")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--profiles", nargs="+", default=PROFILES)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--seed", type=int, default=2106)
    args = parser.parse_args()
    if args.rounds < 3 or "github" not in args.profiles or len(set(args.profiles)) != len(args.profiles):
        parser.error("provide at least three rounds and unique profiles including github")
    cases = sorted(args.cases.resolve().glob("*.txt"))
    if not cases:
        parser.error("no test cases")
    solver, checker = args.solver.resolve(), args.checker.resolve()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    sources = sorted(p for directory in ("include", "src", "research/seed_study")
                     for p in (ROOT / directory).rglob("*") if p.is_file()
                     and p.suffix in (".cpp", ".hpp", ".py"))
    manifest = dict(base_commit=subprocess.check_output(["git", "rev-parse", "HEAD"],
                    text=True, cwd=ROOT).strip(), platform=platform.platform(),
                    machine=platform.machine(), python=sys.version, solver_sha256=sha(solver),
                    checker_sha256=sha(checker), files={str(p.relative_to(ROOT)): sha(p) for p in sources},
                    inputs={p.name: sha(p) for p in cases},
                    compiler=subprocess.check_output(["c++", "--version"], text=True).splitlines()[0],
                    profiles=args.profiles, rounds=args.rounds, warmup="one full round",
                    shuffle_seed=args.seed, timing="separate process launch to exit with wait4",
                    admission="all measured rounds valid, identical emitted netlist SHA and full postpass",
                    time_evidence="disjoint observed ranges plus max(0.2 ms, 5% of median)")
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    rng, verified = random.Random(args.seed), {}
    limits = {c: metadata(c) for c in cases}
    with tempfile.TemporaryDirectory() as tmp, (out / "runs.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, FIELDS)
        writer.writeheader()
        for repeat in range(args.rounds + 1):
            case_order = rng.sample(cases, len(cases))
            seq = 0
            for case in case_order:
                for profile in rng.sample(args.profiles, len(args.profiles)):
                    row = trial(solver, checker, case, profile, limits[case], Path(tmp), verified)
                    writer.writerow(dict(row, round=repeat, sequence=seq))
                    seq += 1
                    f.flush()
                print(f"round={repeat} case={case.name} runs={seq}", flush=True)
    for s in analyze(out, args.profiles, args.rounds):
        print(s, flush=True)


if __name__ == "__main__":
    main()
