"""Analyze complete repeated measurements, including equivalent A/D outcomes."""
import csv
import json
from collections import defaultdict
from math import isfinite
from statistics import median


def write_rows(path, rows):
    if not rows:
        return
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def dominates(a, b):
    return all(x <= y for x, y in zip(a, b)) and any(x < y for x, y in zip(a, b))


def aggregate_runs(case, profile, runs, rounds, allow_missing_hashes=False):
    good = [r for r in runs if r["status"].strip().upper() == "PASS"]
    times = [float(r["runtime_ms"]) for r in good if r.get("runtime_ms", "").strip()]
    if any(not isfinite(t) or t < 0 for t in times):
        raise ValueError(f"invalid runtime on {case}/{profile}")
    ad_pairs = {(int(r["area"]), int(r["delay"])) for r in good}
    hashes = {r["netlist_sha256"] for r in good if r.get("netlist_sha256")}
    missing_hash = any(not r.get("netlist_sha256") for r in good)
    reason = ""
    if sorted(int(r["round"]) for r in runs) != list(range(1, rounds + 1)):
        reason = "missing or duplicate measured round"
    elif len(good) != rounds:
        reason = "one or more failed or incomplete runs"
    elif len(times) != rounds:
        reason = "missing total runtime"
    elif len(ad_pairs) != 1 or len(hashes) > 1:
        reason = "unstable netlist or metrics"
    elif missing_hash and (hashes or not allow_missing_hashes):
        reason = "missing netlist hashes"
    ok = not reason
    row = dict(case=case, profile=profile, passed=len(good), eligible=int(ok),
               reason=reason, distinct_outputs=len(hashes) if hashes else "",
               seed_area="", seed_delay="", area="", delay="", target_met="",
               time_min_ms=min(times) if times else "", time_median_ms=median(times) if times else "",
               time_max_ms=max(times) if times else "",
               ad_frontier=0, adt_median_frontier=0, keep_ad=0, keep_time=0)
    if ok:
        row.update(seed_area=good[0].get("seed_area", ""), seed_delay=good[0].get("seed_delay", ""))
        (row["area"], row["delay"]), = ad_pairs
        row["target_met"] = int(row["delay"] <= int(good[0]["target"]))
    return row


def analyze(out, profiles, rounds, allow_missing_hashes=False):
    with (out / "runs.csv").open() as f:
        raw = list(csv.DictReader(f))
    by_case = defaultdict(lambda: defaultdict(list))
    for row in raw:
        if int(row["round"]) > 0:
            by_case[row["case"]][row["profile"]].append(row)
    rows = []
    for case, by_profile in sorted(by_case.items()):
        current = []
        for p in profiles:
            row = aggregate_runs(case, p, by_profile[p], rounds, allow_missing_hashes)
            if row["eligible"]:
                current.append(row)
            rows.append(row)
        baseline = next((r for r in current if r["profile"] == "github"), None)
        for r in current:
            ad = (r["area"], r["delay"])
            adt = (*ad, r["time_median_ms"])
            r["ad_frontier"] = int(not any(dominates((q["area"], q["delay"]), ad) for q in current))
            r["adt_median_frontier"] = int(not any(dominates((q["area"], q["delay"], q["time_median_ms"]), adt)
                                                   for q in current))
            same = [q for q in current if (q["area"], q["delay"]) == ad]
            # Equivalent AD is one point. Keep the reference if tied, else
            # select the first declared construction, unless one is reliably faster.
            if baseline and r["ad_frontier"] and baseline not in same:
                first = min(same, key=lambda q: profiles.index(q["profile"]))
                if r is first:
                    r["keep_ad"] = 1
            if not baseline or r is baseline or not r["adt_median_frontier"]:
                continue
            peers = [q for q in current if q is not r and q["area"] <= r["area"] and q["delay"] <= r["delay"]]
            # A runtime contribution has evidence only if every alternative with
            # at least this quality is slower even over observed ranges + a margin.
            margin = max(0.2, 0.05 * r["time_median_ms"])
            if peers and all(r["time_max_ms"] + margin < q["time_min_ms"] for q in peers):
                r["keep_time"] = 1
        # Where a duplicate AD has a clear speed winner, keep it as representative.
        for winner in current:
            if winner["keep_time"] and winner["ad_frontier"]:
                for r in current:
                    if (r["area"], r["delay"]) == (winner["area"], winner["delay"]) and r["keep_ad"]:
                        r["keep_ad"] = 0
                        winner["keep_ad"] = 1
    write_rows(out / "comparison.csv", rows)
    summary = []
    for p in profiles:
        values = [r for r in rows if r["profile"] == p]
        summary.append(dict(profile=p, eligible=sum(r["eligible"] for r in values),
            target_met=sum(r["target_met"] == 1 for r in values),
            ad_cases=sum(r["ad_frontier"] for r in values),
            median_adt_cases=sum(r["adt_median_frontier"] for r in values),
            new_ad_cases=sum(r["keep_ad"] for r in values),
            robust_time_cases=sum(r["keep_time"] for r in values),
            retained=p == "github" or any(r["keep_ad"] or r["keep_time"] for r in values)))
    write_rows(out / "summary.csv", summary)
    (out / "retained.json").write_text(json.dumps(
        [x["profile"] for x in summary if x["retained"]], indent=2) + "\n")
    return summary
