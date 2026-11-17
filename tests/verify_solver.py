#!/usr/bin/env python3
"""Independent, exhaustive verification of small synthesized circuits.

Uses only the Python standard library. This is a development check, not a
replacement for the instructor's evaluator or a reproduction of its score.
"""
import argparse
import itertools
import random
import subprocess
import tempfile
from pathlib import Path


def check_circuit(n, rows, library, text):
    lines = [line.split() for line in text.splitlines() if line.strip()]
    m = len(rows[0])
    assert lines, "empty circuit"
    gates = []
    arrival = [0] * (n + 1)
    area = 0
    for tokens in lines[:-1]:
        gate_id, op = int(tokens[0]), tokens[1]
        assert gate_id == len(arrival), "nonconsecutive gate ID"
        assert op in library, "unsupported gate"
        fanins = tuple(map(int, tokens[2:]))
        assert len(fanins) == (1 if op == "NOT" else 2)
        assert all(0 <= x < gate_id for x in fanins), "invalid reference"
        gates.append((op, fanins))
        arrival.append(max(arrival[x] for x in fanins) + library[op][1])
        area += library[op][0]
    outputs = tuple(map(int, lines[-1]))
    assert len(outputs) == m
    assert all(0 <= x < len(arrival) for x in outputs)
    for i, expected in enumerate(rows):
        values = [0] + [(i >> (n - 1 - k)) & 1 for k in range(n)]
        for op, fanins in gates:
            a = values[fanins[0]]
            if op == "NOT":
                result = 1 - a
            else:
                b = values[fanins[1]]
                result = a & b if op == "AND2" else a | b
            values.append(result)
        actual = "".join(str(values[x]) for x in outputs)
        assert actual == expected, f"row {i}: expected {expected}, got {actual}"
    return area, max(arrival[x] for x in outputs)


def make_case(n, rows, costs, target, limits):
    return "\n".join([
        str(n), str(len(rows[0])), " ".join(rows),
        *(f"{area} {delay}" for area, delay in costs), str(target),
        *(str(x) for x in limits),
    ]) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("solver", type=Path)
    parser.add_argument("--no-stats", action="store_true",
                        help="check an external solver that does not print area/delay statistics")
    args = parser.parse_args()
    solver = args.solver.resolve()
    rng = random.Random(2106)
    cases = []
    # Exhaust every one-output Boolean function with 1, 2, or 3 inputs.
    for n in range(1, 4):
        for function in range(1 << (1 << n)):
            rows = [str((function >> i) & 1) for i in range(1 << n)]
            costs = [(rng.randint(1, 9), rng.randint(1, 5)) for _ in range(3)]
            cases.append((n, rows, costs, rng.randint(1, 30), ()))
    # Duplicate/complemented outputs, constants, direct input wires, and shared logic.
    for n in range(1, 9):
        rows = []
        for bits in itertools.product((0, 1), repeat=n):
            a, b, c = bits[0], bits[-1], bits[n // 2]
            shared = a | b
            values = [0, 1, a, 1-a, shared, 1-shared, shared & c, shared]
            rows.append("".join(map(str, values)))
        for costs in (
            [(2, 2), (8, 3), (1, 1)],
            [(8, 3), (2, 2), (1, 1)],
            [(2, 2), (2, 3), (4, 2)],
        ):
            cases.append((n, rows, costs, 30, (0, 0)))
    # General multi-output functions and all supported optional-limit forms.
    for k in range(100):
        n, m = rng.randint(1, 8), rng.randint(1, 10)
        rows = ["".join(str(rng.getrandbits(1)) for _ in range(m)) for _ in range(1 << n)]
        costs = [(rng.randint(1, 12), rng.randint(1, 6)) for _ in range(3)]
        limits = [(), (0,), (0, 0), (10000, 262144)][k % 4]
        cases.append((n, rows, costs, rng.randint(1, 80), limits))
    with tempfile.TemporaryDirectory(prefix="ufug2106-verify-") as temp:
        input_path, output_path = Path(temp) / "input.txt", Path(temp) / "output.txt"
        for index, (n, rows, costs, target, limits) in enumerate(cases, 1):
            input_path.write_text(make_case(n, rows, costs, target, limits))
            result = subprocess.run(
                [str(solver), str(input_path), str(output_path)],
                capture_output=True, text=True, timeout=10,
            )
            assert result.returncode == 0, result.stderr
            library = dict(zip(("AND2", "OR2", "NOT"), costs))
            area, delay = check_circuit(n, rows, library, output_path.read_text())
            if not args.no_stats:
                stats = dict(token.split("=", 1) for token in result.stderr.split() if "=" in token)
                assert int(stats["area"]) == area, (index, "area mismatch")
                assert int(stats["delay"]) == delay, (index, "delay mismatch")
    print(f"PASS: {len(cases)} generated cases; exhaustive logic, format, area and delay checks")


if __name__ == "__main__":
    main()
