#!/usr/bin/env python3
"""Summarize five-round seed trials from the official evaluator's combined runs.csv."""
import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path

from analyze import aggregate_runs, analyze, dominates, write_rows
from run import PROFILES


def read_csv(path):
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def compare_deployed(rows, raw, rounds):
    runs = defaultdict(list)
    for r in raw:
        if r["profile"] == "deployed" and int(r["round"]) > 0:
            runs[r["case"]].append(r)
    comparisons = []
    for r in rows:
        ref = aggregate_runs(r["case"], "deployed", runs[r["case"]], rounds, True)
        eligible = r["eligible"] == "1" and ref["eligible"]
        row = dict(case=r["case"], profile=r["profile"], eligible=int(eligible),
                   deployed_area=ref["area"], deployed_delay=ref["delay"],
                   deployed_time_median_ms=ref["time_median_ms"], area=r["area"], delay=r["delay"],
                   time_median_ms=r["time_median_ms"], area_delta="", delay_delta="", time_delta_ms="",
                   all_three_strictly_better="")
        if eligible:
            deltas = (int(r["area"])-ref["area"], int(r["delay"])-ref["delay"],
                      float(r["time_median_ms"])-ref["time_median_ms"])
            row.update(area_delta=deltas[0], delay_delta=deltas[1], time_delta_ms=round(deltas[2], 4),
                       all_three_strictly_better=int(all(x < 0 for x in deltas)))
        comparisons.append(row)
    return comparisons


def case_summary(raw, rows):
    targets = {r["case"]: int(r["target"]) for r in raw}
    groups = defaultdict(list)
    for r in rows:
        groups[r["case"]].append(r)
    cases = []
    for name, group in sorted(groups.items()):
        eligible = [r for r in group if r["eligible"] == "1"]
        ref = next((r for r in eligible if r["profile"] == "github"), None)
        ad = lambda r: (int(r["area"]), int(r["delay"]))
        new = [r for r in eligible if r["keep_ad"] == "1"]
        triples = [r for r in eligible if r["keep_time"] == "1"]
        smaller_on_target = [r for r in eligible if ref and ad(r)[0] < ad(ref)[0]
                             and ad(r)[1] <= targets[name]]
        improvements = [r for r in eligible if ref and dominates(ad(r), ad(ref))
                        and float(r["time_max_ms"]) + max(0.2, 0.05 * float(r["time_median_ms"]))
                        < float(ref["time_min_ms"])]
        cases.append(dict(case=name, target=targets[name], eligible=len(eligible),
            reference_area=ref["area"] if ref else "", reference_delay=ref["delay"] if ref else "",
            reference_time_median_ms=ref["time_median_ms"] if ref else "",
            new_distinct_ad=len(new), new_ad_profiles=" ".join(r["profile"] for r in new),
            robust_time_profiles=" ".join(r["profile"] for r in triples),
            smaller_on_target_profiles=" ".join(r["profile"] for r in smaller_on_target),
            robust_joint_improvements=" ".join(r["profile"] for r in improvements)))
    return cases


def generate(out, rounds):
    raw = read_csv(out / "runs.csv")
    if not raw:
        raise ValueError("empty official run log")
    unexpected = {r["profile"] for r in raw} - set(PROFILES) - {"deployed"}
    if unexpected:
        raise ValueError(f"unknown profiles: {unexpected}")
    summary = analyze(out, PROFILES, rounds, allow_missing_hashes=True)
    rows = read_csv(out / "comparison.csv")
    cases = case_summary(raw, rows)
    write_rows(out / "per_case.csv", cases)
    deployed = compare_deployed(rows, raw, rounds)
    write_rows(out / "deployed_comparison.csv", deployed)
    expected = len(cases) * len(PROFILES) * rounds
    controlled = [r for r in raw if r["profile"] in PROFILES and int(r["round"]) > 0]
    statuses = Counter(r["status"] for r in controlled)
    hashed = sum(bool(r.get("netlist_sha256")) for r in controlled)
    report = ["# Official Linux seed comparison", "",
              f"The controlled comparison uses {len(PROFILES)} seed profiles, {len(cases)} cases and "
              f"{rounds} measured rounds. It has {len(controlled)}/{expected} expected timed records. "
              f"Status counts are {dict(statuses)}. Output hashes are available for {hashed} records.",
              "", "Every controlled run uses the same downstream optimization and output selection. "
              "Three-dimensional membership uses median end-to-end runtime. Retention based on runtime "
              "also requires disjoint observed ranges plus a margin of max(0.2 ms, 5% of the candidate "
              "median). Admission requires correct outputs in all measured rounds, stable area and delay, "
              "and identical netlist hashes when the evaluator provides them. All claims concern observed "
              "profiles. The `deployed` solver is reported separately because its optimization path differs.",
              "", f"{sum(r['new_distinct_ad'] for r in cases)} distinct new A/D points across "
              f"{sum(bool(r['new_distinct_ad']) for r in cases)} cases. "
              f"{sum(bool(r['smaller_on_target_profiles']) for r in cases)} cases have a smaller area "
              "than the controlled reference while still reaching the case's delay target.", "",
              "| Seed | Eligible cases | Met target | New A/D points | Runtime contribution cases | Keep |",
              "|---|---:|---:|---:|---:|---|"]
    for s in summary:
        report.append(f"| {s['profile']} | {s['eligible']} | {s['target_met']} | "
                      f"{s['new_ad_cases']} | {s['robust_time_cases']} | {s['retained']} |")
    examples = []
    for c in cases:
        names = c["robust_joint_improvements"].split()
        for name in names[:1]:
            p = next(r for r in rows if r["case"] == c["case"] and r["profile"] == name)
            examples.append((c, p))
    if examples:
        report.extend(["", "Selected paired measurements with an A/D improvement and separated time ranges.",
                       "", "| Case | Seed | Reference area/delay/ms | Candidate area/delay/ms |", "|---|---|---:|---:|"])
        for c, p in examples[:4]:
            report.append(f"| {c['case']} | {p['profile']} | {c['reference_area']} / {c['reference_delay']} / "
                          f"{float(c['reference_time_median_ms']):.3f} | {p['area']} / {p['delay']} / "
                          f"{float(p['time_median_ms']):.3f} |")
    report.extend(["", "The deployed comparisons in `deployed_comparison.csv` are per case, with differences "
                   "computed as candidate minus deployed. A difference includes the effect of their different "
                   "downstream pipelines. `per_case.csv` lists all new points and exclusions are identified in "
                   "`comparison.csv`. The suggestions in `retained.json` were evaluated independently, "
                   "not timed as a single portfolio.", ""])
    (out / "report.md").write_text("\n".join(report))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path)
    parser.add_argument("--rounds", type=int, default=5)
    options = parser.parse_args()
    generate(options.results, options.rounds)
