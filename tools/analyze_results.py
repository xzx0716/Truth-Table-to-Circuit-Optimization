#!/usr/bin/env python3
"""Summarize serial repeated official runs and per-case Pareto relationships."""
import argparse
import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path


def dominates(a, b, keys):
    return all(a[k] <= b[k] for k in keys) and any(a[k] < b[k] for k in keys)


def analyze(path, out):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        raw = list(csv.DictReader(handle))
    groups = defaultdict(list)
    for row in raw:
        groups[row["case"], row["strategy"]].append(row)
    summary = []
    for (case, strategy), rows in sorted(groups.items()):
        passed = [r for r in rows if r["status"] == "PASS"]
        numeric = []
        for row in passed:
            try:
                numeric.append(tuple(float(row[k]) for k in ("area", "delay", "runtime_ms")))
            except (ValueError, KeyError):
                continue
        entry = {"case": case, "strategy": strategy, "runs": len(rows), "passes": len(passed),
                 "all_pass": len(passed) == len(rows) and len(numeric) == len(rows),
                 "all_target_met": all(r.get("target_met", "").lower() == "yes" for r in rows),
                 "area": "", "delay": "", "runtime_median_ms": "", "runtime_min_ms": "",
                 "runtime_max_ms": "", "ad_stable": False,
                 "ad_nondominated": False, "adr_median_nondominated": False,
                 "adr_separated_nondominated": False,
                 "statuses": ";".join(sorted({r["status"] for r in rows}))}
        if numeric:
            areas, delays, runtimes = zip(*numeric)
            entry.update(area=statistics.median(areas), delay=statistics.median(delays),
                         runtime_median_ms=statistics.median(runtimes), runtime_min_ms=min(runtimes),
                         runtime_max_ms=max(runtimes), ad_stable=len(set(zip(areas, delays))) == 1)
        summary.append(entry)
    by_case = defaultdict(list)
    for row in summary:
        by_case[row["case"]].append(row)
    comparisons = []
    for case, rows in by_case.items():
        # Unstable A/D cannot safely be represented as one observed circuit pair.
        eligible = [r for r in rows if r["all_pass"] and r["ad_stable"]]
        for row in eligible:
            row["ad_nondominated"] = not any(dominates(other, row, ("area", "delay")) for other in eligible)
            row["adr_median_nondominated"] = not any(
                dominates(other, row, ("area", "delay", "runtime_median_ms")) for other in eligible)
            # Conservative descriptive relation, not a statistical significance test:
            # require A/D no worse and all observed runtime samples strictly faster.
            row["adr_separated_nondominated"] = not any(
                other["area"] <= row["area"] and other["delay"] <= row["delay"] and
                other["runtime_max_ms"] < row["runtime_min_ms"] for other in eligible)
        for i, a in enumerate(eligible):
            for b in eligible[i + 1:]:
                overlap = max(a["runtime_min_ms"], b["runtime_min_ms"]) <= min(
                    a["runtime_max_ms"], b["runtime_max_ms"])
                comparisons.append({"case": case, "a": a["strategy"], "b": b["strategy"],
                    "a_dominates_b_ad": dominates(a, b, ("area", "delay")),
                    "b_dominates_a_ad": dominates(b, a, ("area", "delay")),
                    "a_dominates_b_adr_median": dominates(a, b, ("area", "delay", "runtime_median_ms")),
                    "b_dominates_a_adr_median": dominates(b, a, ("area", "delay", "runtime_median_ms")),
                    "runtime_ranges_overlap": overlap,
                    "runtime_interpretation": "difference unresolved" if overlap else "observed ranges separated"})
    out.mkdir(parents=True, exist_ok=True)
    for name, data in (("summary.csv", summary), ("comparisons.csv", comparisons)):
        with (out / name).open("w", newline="") as handle:
            if data:
                writer = csv.DictWriter(handle, list(data[0]))
                writer.writeheader()
                writer.writerows(data)
    strategy_summary = []
    for strategy in sorted({r["strategy"] for r in summary}):
        rows = [r for r in summary if r["strategy"] == strategy]
        good = [r for r in rows if r["all_pass"] and r["ad_stable"]]
        strategy_summary.append({"strategy": strategy, "cases": len(rows),
            "all_pass_cases": sum(r["all_pass"] for r in rows),
            "all_target_met_cases": sum(r["all_target_met"] and r["all_pass"] for r in rows),
            "ad_frontier_cases": sum(r["ad_nondominated"] for r in rows),
            "adr_median_frontier_cases": sum(r["adr_median_nondominated"] for r in rows),
            "area_sum_descriptive": sum(r["area"] for r in good),
            "runtime_case_median_ms": statistics.median(r["runtime_median_ms"] for r in good) if good else None})
    (out / "strategy_summary.json").write_text(json.dumps(strategy_summary, indent=2) + "\n")
    notes = ["# Repeated-run analysis", "",
        "Area and delay are shown as one pair only when stable across all measured runs. "
        "Failed or incomplete strategies are excluded from the normal Pareto comparisons.", "",
        "The A/D/runtime frontier using median runtime is descriptive. Overlapping observed "
        "runtime ranges are marked as an unresolved runtime difference; separated ranges "
        "are also not a statistical significance claim. No official score is inferred.", "",
        "The area sum is a descriptive statistic only. Per-case medians are not independent "
        "extra cases, and per-case winners are not combined into a fictitious solver.", "",
        "| Strategy | All-pass cases | Target met | A/D frontier | A/D/runtime median frontier |",
        "|---|---:|---:|---:|---:|"]
    for r in strategy_summary:
        notes.append(f"| {r['strategy']} | {r['all_pass_cases']}/{r['cases']} | "
                     f"{r['all_target_met_cases']} | {r['ad_frontier_cases']} | {r['adr_median_frontier_cases']} |")
    (out / "analysis.md").write_text("\n".join(notes) + "\n")
    return strategy_summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    print(json.dumps(analyze(args.runs, args.out or args.runs.parent), indent=2))
