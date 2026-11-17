#!/usr/bin/env python3
"""Generate reproducible structured/random/variable-permuted resource cases."""
import argparse
import hashlib
import json
import random
from pathlib import Path


def make(n, kind, seed):
    rng = random.Random(seed)
    permutation = list(range(n))
    if kind == "permuted":
        rng.shuffle(permutation)
    gates = []
    def gate(op, a, b=None):
        gates.append((op, a, b))
        return n + len(gates)
    def reduce(op, signals):
        while len(signals) > 1:
            signals = [gate(op, signals[i], signals[i + 1]) if i + 1 < len(signals) else signals[i]
                       for i in range(0, len(signals), 2)]
        return signals[0]
    inputs = [x + 1 for x in permutation]
    if kind == "random":
        for _ in range(4 * n):
            a, b = rng.randrange(n + len(gates) + 1), rng.randrange(n + len(gates) + 1)
            op = rng.choice(("AND2", "OR2", "NOT"))
            gate(op, a, b if op != "NOT" else None)
        outputs = list(range(n + len(gates) - 3, n + len(gates) + 1))
    else:
        shared = reduce("OR2", inputs[:max(2, n // 2)])
        tail = reduce("AND2", inputs[max(2, n // 2):])
        both = gate("AND2", shared, tail)
        inverse = gate("NOT", shared)
        outputs = [shared, both, inverse, gate("OR2", both, inputs[-1])]
    return gates, outputs, permutation


def write_case(path, n, gates, outputs, costs, runtime, ram):
    # A Python integer is a packed column of 2^n truth values. This creates an
    # exact known circuit oracle without storing 2^n Python lists of all gates.
    count = 1 << n
    mask = (1 << count) - 1
    columns = [0]
    for variable in range(n):
        block = 1 << (n - 1 - variable)
        # Row zero occupies the least significant bit.
        columns.append((((1 << block) - 1) << block) * (mask // ((1 << (2 * block)) - 1)))
    for op, a, b in gates:
        columns.append((mask ^ columns[a]) if op == "NOT" else
                       (columns[a] & columns[b] if op == "AND2" else columns[a] | columns[b]))
    # Convert whole columns once; repeatedly right-shifting a 2^20-bit integer
    # per row would otherwise become quadratic.
    packed = [columns[o].to_bytes((count + 7) // 8, "little") for o in outputs]
    with path.open("w", newline="\n") as handle:
        handle.write(f"{n}\n{len(outputs)}\n")
        for base in range(0, count, 4096):
            rows = ["".join(str((column[i >> 3] >> (i & 7)) & 1) for column in packed)
                    for i in range(base, min(count, base + 4096))]
            handle.write(" ".join(rows) + ("\n" if base + 4096 >= count else " "))
        for area, delay in costs:
            handle.write(f"{area} {delay}\n")
        handle.write(f"{max(20, 8 * n)}\n{runtime}\n{ram}\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("artifacts/generated-suite"))
    parser.add_argument("--n", type=int, nargs="+", default=[12, 16, 20])
    parser.add_argument("--seed", type=int, default=210617)
    parser.add_argument("--runtime", type=int, default=10000)
    parser.add_argument("--ram", type=int, default=262144)
    args = parser.parse_args()
    if args.out.exists() and any(args.out.iterdir()):
        parser.error("output directory must be empty or new")
    if any(n < 4 or n > 24 for n in args.n):
        parser.error("this generator supports 4<=n<=24; n=24 can produce very large files")
    args.out.mkdir(parents=True, exist_ok=True)
    manifest = {"seed": args.seed, "cases": [], "oracle": "known acyclic gate circuit"}
    for n in args.n:
        for kind in ("structured", "permuted", "random"):
            seed = args.seed + n * 101 + {"structured": 0, "permuted": 1, "random": 2}[kind]
            gates, outputs, permutation = make(n, kind, seed)
            name = f"{kind}_n{n:02d}.txt"
            path = args.out / name
            costs = [(2, 2), (8, 3), (1, 1)] if kind != "random" else [(3, 1), (1, 4), (1, 1)]
            write_case(path, n, gates, outputs, costs, args.runtime, args.ram)
            manifest["cases"].append({"name": name, "n": n, "seed": seed,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "gates": gates,
                "outputs": outputs, "permutation": permutation})
            print(name, flush=True)
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
