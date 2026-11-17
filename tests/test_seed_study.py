#!/usr/bin/env python3
"""Run from the repo with python3 tests/test_seed_study.py build/solver."""
import argparse
import itertools
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile

from verify_solver import check_circuit, make_case

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research" / "seed_study"))
from run import PROFILES


SAMPLE = ["00", "00", "10", "11", "10", "11", "10", "11"]
COSTS = [(2, 2), (8, 3), (1, 1)]


def cases():
    yield "course-example", 3, SAMPLE, COSTS, 5
    yield "constant", 1, ["01", "01"], COSTS, 1
    # Pure wires in a permuted order, with a duplicated output.
    yield "wires", 3, [f"{c}{a}{b}{a}" for a, b, c in itertools.product((0, 1), repeat=3)], COSTS, 1
    for permutation in [(0, 1, 2, 3, 4), (3, 1, 0, 4, 2)]:
        rows = []
        for bits in itertools.product((0, 1), repeat=5):
            a, b, c, d, e = (bits[i] for i in permutation)
            shared = (a & b) | (c if e else d)
            rows.append(f"{shared}{1-shared}{shared & a}{b ^ e}")
        yield f"permuted-{permutation[0]}", 5, rows, [(8, 1), (1, 7), (2, 3)], 15
    rng = random.Random(2106)
    for n in (4, 6):
        rows = ["".join(str(rng.getrandbits(1)) for _ in range(4)) for _ in range(1 << n)]
        yield f"random-{n}", n, rows, [(3, 2), (2, 1), (1, 3)], 20


def is_shared_or_and(text):
    lines = [line.split() for line in text.splitlines() if line.strip()]
    return (len(lines) == 3 and lines[0][:2] == ["4", "OR2"] and set(lines[0][2:]) == {"1", "2"}
            and lines[1][:2] == ["5", "AND2"] and set(lines[1][2:]) == {"3", "4"}
            and lines[-1] == ["4", "5"])


def main():
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("solver", type=Path)
    exe = args.parse_args().solver.resolve()
    checks, shared = 0, []
    env = {k: v for k, v in os.environ.items() if not k.startswith("TTC_")}
    library = dict(zip(("AND2", "OR2", "NOT"), COSTS))
    # Both lecture implementations are equivalent despite their different costs.
    example_b = "4 NOT 1\n5 NOT 2\n6 AND2 4 5\n7 NOT 6\n8 AND2 7 3\n7 8\n"
    assert check_circuit(3, SAMPLE, library, example_b) == (7, 6)
    with tempfile.TemporaryDirectory() as directory:
        source, output = (Path(directory) / name for name in ("case.txt", "netlist.txt"))

        def run(profile, **overrides):
            output.unlink(missing_ok=True)
            return subprocess.run([exe, source, output], env=dict(env, TTC_INITIAL_SEED=profile, **overrides),
                                  check=False, capture_output=True, text=True, timeout=10)

        for name, n, rows, costs, target in cases():
            source.write_text(make_case(n, rows, costs, target, ()))
            for profile in PROFILES:
                previous = None
                for _ in range(2):
                    result = run(profile)
                    assert result.returncode == 0, (profile, name, result.stderr)
                    stats = dict(field.split("=", 1) for field in result.stderr.split() if "=" in field)
                    assert stats["post_complete"] == stats["seed_complete"] == "1", (profile, name, stats)
                    net = output.read_text()
                    measured = check_circuit(n, rows, dict(zip(("AND2", "OR2", "NOT"), costs)), net)
                    assert (int(stats["area"]), int(stats["delay"])) == measured, (profile, name, measured)
                    snapshot = (net, stats["seed_area"], stats["seed_delay"])
                    assert previous is None or previous == snapshot, (profile, name, "nondeterministic")
                    previous = snapshot
                    checks += 1
                if name == "course-example" and is_shared_or_and(net):
                    assert measured == (10, 5)
                    shared.append(profile)
        assert shared, "no profiled construction produced the shared two-gate solution"
        result = run("unknown-profile")
        assert result.returncode != 0 and "unknown seed profile" in result.stderr and not output.exists()
        # A one-millisecond cap is below even the minimum reserved write budget.
        for profile in PROFILES:
            result = run(profile, TTC_RESEARCH_MS="1")
            assert result.returncode != 0 and not output.exists(), (profile, result.stderr)
    print(f"PASS {checks} full output checks across {len(PROFILES)} profiles. "
          f"Shared two-gate example (area 10, delay 5): {', '.join(shared)}. "
          "Lecture B (area 7, delay 6), invalid profile and budget cancellation verified.")


if __name__ == "__main__":
    main()
