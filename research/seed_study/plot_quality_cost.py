"""Regenerate the case_024 single-seed quality/cost curves from official measurements."""

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import StrMethodFormatter


ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results/seed-study-linux-20261117"
CASE = "case_024.txt"


def case_rows(filename):
    with (RESULTS / filename).open(newline="") as file:
        return [row for row in csv.DictReader(file) if row["case"] == CASE]


def improving_points(rows, delay_cap):
    points = []
    for row in sorted(rows, key=lambda r: (float(r["time_median_ms"]), int(r["area"]))):
        area = int(row["area"])
        if int(row["delay"]) <= delay_cap and (not points or area < points[-1][1]):
            points.append((float(row["time_median_ms"]), area))
    return points


def main():
    rows = [row for row in case_rows("comparison.csv") if row["eligible"] == "1"]
    target, = {int(row["target"]) for row in case_rows("runs.csv")}
    reference_delay = next(int(row["delay"]) for row in rows if row["profile"] == "github")
    upper_time = 10 * (int(max(float(row["time_median_ms"]) for row in rows)) // 10 + 1)

    plt.rcParams.update({"svg.fonttype": "none", "svg.hashsalt": "ttc-seed-study"})
    fig, ax = plt.subplots(figsize=(7.3, 3.9), layout="constrained")
    for cap, label, color, style in (
        (target, "Course target", "#176b55", "-"),
        (reference_delay, "GitHub reference delay", "#ab5019", "--"),
    ):
        points = improving_points(rows, cap)
        times, areas = zip(*points)
        ax.step([*times, upper_time], [*areas, areas[-1]], where="post",
                color=color, linestyle=style, label=f"{label} (≤ {cap})")
        ax.scatter(times, areas, color=color, s=24, zorder=3)

    ax.set_title("case_024  |  Best observed area within a runtime ceiling", loc="left")
    ax.set_xlabel("Single-seed median runtime ceiling (ms)")
    ax.set_ylabel("Minimum circuit area")
    ax.yaxis.set_major_formatter(StrMethodFormatter("{x:,.0f}"))
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=0.25)
    ax.legend(loc="upper left", frameon=False)
    fig.savefig(ROOT / "docs/seed-quality-cost.svg", metadata={"Date": None})
    plt.close(fig)


if __name__ == "__main__":
    main()
