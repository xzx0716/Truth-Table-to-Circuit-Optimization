#!/usr/bin/env python3
"""Run full official case sets serially, preserving every evaluator report and failure."""
import argparse
import csv
import hashlib
import json
import os
import platform
import re
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def capture(command, cwd):
    try:
        result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=15)
        return {"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"error": str(exc)}


def source_state(root):
    paths = sorted(p for folder in ("src", "include", "configs", "research/templates")
                   for p in (root / folder).rglob("*") if p.is_file())
    hashes = {p.relative_to(root).as_posix(): digest(p) for p in paths}
    return {"files": hashes,
            "tree_sha256": hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest(),
            "commit": capture(["git", "rev-parse", "HEAD"], root),
            "status": capture(["git", "status", "--porcelain"], root)}


def key_value(text):
    key, sep, value = text.partition("=")
    if not sep or not key or not value:
        raise argparse.ArgumentTypeError("expected NAME=VALUE")
    return key, value


def case_metadata(path):
    """Read specified line-based case fields without retaining the truth table."""
    try:
        with path.open() as handle:
            n, m = int(handle.readline()), int(handle.readline())
            handle.readline()
            trailing = [int(token) for token in handle.read().split()]
        return {"n": n, "m": m, "target_delay": trailing[6],
                "runtime_limit_ms": trailing[7] if len(trailing) > 7 else 0,
                "ram_limit_kb": trailing[8] if len(trailing) > 8 else 0}
    except (ValueError, IndexError, OSError) as exc:
        return {"metadata_error": str(exc)}


def execute(command, root, env, stdout, stderr, timeout):
    """On Linux kill the whole evaluator/solver group if the outer guard expires."""
    process = subprocess.Popen(command, cwd=root, env=env, stdout=stdout, stderr=stderr,
                               start_new_session=(os.name == "posix"))
    try:
        return process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        if os.name == "posix":
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        else:
            process.kill()
        process.wait()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--solver", type=key_value, action="append", required=True,
                        help="repeat NAME=/absolute/or/relative/binary")
    parser.add_argument("--env", action="append", default=[], metavar="NAME:KEY=VALUE",
                        help="per-strategy environment (also included in manifest)")
    parser.add_argument("--profile", type=key_value, action="append", default=[],
                        metavar="NAME=STRATEGY", help="shorthand for NAME:TTC_STRATEGY=STRATEGY")
    parser.add_argument("--cases", type=Path, default=Path("data/local/stage1"))
    parser.add_argument("--evaluator", type=Path, default=Path("data/local/evaluator"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=3600,
                        help="whole evaluator run timeout; case limits remain enforced by evaluator")
    parser.add_argument("--save-outputs", action="store_true")
    parser.add_argument("--rss-probe", action="store_true",
                        help="after official timings, separately measure solver-only peak RSS with /usr/bin/time")
    parser.add_argument("--build-command", default="not supplied; binary hash recorded",
                        help="exact command used to compile the supplied binaries")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root, out = args.root.resolve(), args.out.resolve()
    evaluator, cases = args.evaluator.resolve(), args.cases.resolve()
    if args.rounds < 1 or args.warmup < 0:
        parser.error("rounds must be positive and warmup nonnegative")
    if args.timeout <= 0:
        parser.error("timeout must be positive")
    if out.exists() and any(out.iterdir()):
        parser.error("output directory must be empty or new; never overwrite experiments")
    out.mkdir(parents=True, exist_ok=True)
    artifact_dir = root / "artifacts" / out.name
    if artifact_dir.exists() and any(artifact_dir.iterdir()):
        parser.error(f"artifact directory already contains a run: {artifact_dir}")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    solvers = {name: Path(path).resolve() for name, path in args.solver}
    if len(solvers) != len(args.solver):
        parser.error("strategy names must be unique")
    if any(not re.fullmatch(r"[A-Za-z0-9_-]+", name) for name in solvers):
        parser.error("strategy names may contain letters, digits, underscore and hyphen only")
    environments = {name: {} for name in solvers}
    for name, strategy in args.profile:
        if name not in solvers:
            parser.error(f"unknown profile strategy name: {name}")
        environments[name]["TTC_STRATEGY"] = strategy
    for item in args.env:
        name, sep, assignment = item.partition(":")
        if not sep or name not in solvers:
            parser.error(f"invalid strategy environment: {item}")
        key, value = key_value(assignment)
        environments[name][key] = value
    inputs = sorted(cases.glob("*.txt")) if cases.is_dir() else [cases]
    if not inputs:
        parser.error("no case .txt files found")
    manifest = {
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "command": sys.argv, "machine": platform.uname()._asdict(),
        "python": sys.version, "compiler": capture(["g++", "--version"], root),
        "build_command": args.build_command,
        "source_start": source_state(root),
        "solvers": {name: {"path": str(path), "sha256": digest(path),
                            "environment": environments[name]} for name, path in solvers.items()},
        "evaluator": {"path": str(evaluator), "sha256": digest(evaluator)},
        "inputs": {p.name: {"path": str(p), "sha256": digest(p), **case_metadata(p)} for p in inputs},
        "rounds": args.rounds, "warmup_rounds": args.warmup,
        "artifact_directory": str(artifact_dir),
        "runtime_definition": "official evaluator solver wall-clock runtime_ms; not evaluator elapsed time",
        "rss_note": "optional separate solver-only /usr/bin/time probe, never evaluator peak RSS",
        "runs": [],
    }
    manifest_path = out / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    rows = []
    names = list(solvers)
    for iteration in range(args.warmup + args.rounds):
        phase = "warmup" if iteration < args.warmup else "measured"
        number = iteration + 1 if phase == "warmup" else iteration - args.warmup + 1
        # Alternating/reversing order reduces fixed ordering bias, while remaining serial.
        order = names if iteration % 2 == 0 else list(reversed(names))
        if len(order) > 2:
            shift = (iteration // 2) % len(order)
            order = order[shift:] + order[:shift]
        for name in order:
            run_id = f"{phase}-{number:02d}-{name}"
            report = artifact_dir / f"{run_id}.csv"
            stdout = artifact_dir / f"{run_id}.stdout.log"
            stderr = artifact_dir / f"{run_id}.stderr.log"
            command = [str(evaluator), str(solvers[name]), str(cases), "--report", str(report)]
            if args.save_outputs:
                command += ["--save-outputs", str(artifact_dir / f"{run_id}-circuits")]
            # Do not let a development shell's TTC_RESEARCH_MS silently turn an
            # official run into research mode. Every TTC setting must be explicit.
            env = {key: value for key, value in os.environ.items() if not key.startswith("TTC_")}
            env.update(environments[name])
            started = time.perf_counter()
            error = None
            with stdout.open("wb") as outlog, stderr.open("wb") as errlog:
                try:
                    returncode = execute(command, root, env, outlog, errlog, args.timeout)
                except (OSError, subprocess.TimeoutExpired) as exc:
                    returncode, error = None, str(exc)
            elapsed = time.perf_counter() - started
            run = {"id": run_id, "phase": phase, "round": number, "strategy": name,
                   "command": command, "returncode": returncode, "error": error,
                   "evaluator_elapsed_seconds": elapsed,
                   "report": str(report), "stdout": str(stdout), "stderr": str(stderr)}
            observed = {}
            if report.exists():
                with report.open(newline="", encoding="utf-8-sig") as handle:
                    observed = {row["case"]: row for row in csv.DictReader(handle)}
            for case in inputs:
                row = observed.get(case.name, {"case": case.name, "status": "EVALUATOR_ERROR"})
                if phase == "measured":
                    metadata = manifest["inputs"][case.name]
                    rows.append({"strategy": name, "round": number, "case": case.name,
                                 "status": row.get("status", "UNKNOWN"),
                                 "area": row.get("area", ""), "delay": row.get("delay", ""),
                                 "runtime_ms": row.get("runtime_ms", ""),
                                 "target_met": row.get("target_met", ""),
                                 "target_delay": metadata.get("target_delay", ""),
                                 "runtime_limit_ms": metadata.get("runtime_limit_ms", ""),
                                 "ram_limit_kb": metadata.get("ram_limit_kb", ""),
                                 "evaluator_returncode": returncode,
                                 "error": error or "", "run_id": run_id})
            manifest["runs"].append(run)
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
            with (out / "runs.csv").open("w", newline="") as handle:
                fields = ["strategy", "round", "case", "status", "area", "delay", "runtime_ms",
                          "target_met", "target_delay", "runtime_limit_ms", "ram_limit_kb",
                          "evaluator_returncode", "error", "run_id"]
                writer = csv.DictWriter(handle, fields)
                writer.writeheader()
                writer.writerows(rows)
            passed = sum(r.get("status") == "PASS" for r in observed.values())
            print(f"{run_id}: {passed}/{len(inputs)} PASS; evaluator rc={returncode}", flush=True)
    if args.rss_probe:
        probes = []
        for name in names:
            for case in inputs:
                prefix = artifact_dir / f"rss-{name}-{case.stem}"
                rss_path = prefix.with_suffix(".rss.txt")
                command = ["/usr/bin/time", "-f", "%M", "-o", str(rss_path),
                           str(solvers[name]), str(case), str(prefix.with_suffix(".netlist.txt"))]
                env = {k: v for k, v in os.environ.items() if not k.startswith("TTC_")}
                env.update(environments[name])
                limit = manifest["inputs"][case.name].get("runtime_limit_ms", 0)
                # This is a diagnostic probe, not another official PASS/FAIL check.
                timeout = max(5, limit / 1000 * 2) if limit else args.timeout
                error = ""
                with prefix.with_suffix(".stdout.log").open("wb") as stdout, \
                        prefix.with_suffix(".stderr.log").open("wb") as stderr:
                    try:
                        code = execute(command, root, env, stdout, stderr, timeout)
                    except (OSError, subprocess.TimeoutExpired) as exc:
                        code, error = None, str(exc)
                rss = ""
                if rss_path.exists():
                    lines = rss_path.read_text().splitlines()
                    if lines and lines[-1].isdigit():
                        rss = int(lines[-1])
                probes.append({"strategy": name, "case": case.name, "peak_rss_kb": rss,
                               "returncode": code, "error": error})
        with (out / "rss_probes.csv").open("w", newline="") as handle:
            writer = csv.DictWriter(handle, ["strategy", "case", "peak_rss_kb", "returncode", "error"])
            writer.writeheader()
            writer.writerows(probes)
        manifest["rss_probe_note"] = "Separate solver-only runs; not used as official correctness or timing results."
    manifest["source_end"] = source_state(root)
    manifest["source_changed_during_run"] = (
        manifest["source_start"]["tree_sha256"] != manifest["source_end"]["tree_sha256"])
    manifest["binary_end_sha256"] = {name: digest(path) for name, path in solvers.items()}
    manifest["binary_changed_during_run"] = any(
        manifest["solvers"][name]["sha256"] != manifest["binary_end_sha256"][name]
        for name in solvers)
    manifest["finished_utc"] = datetime.now(timezone.utc).isoformat()
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Preserved all results: {out / 'runs.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
