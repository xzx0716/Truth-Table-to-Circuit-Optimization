#!/usr/bin/env python3
"""Build the submission report from one frozen, complete official experiment."""
import argparse
import csv
import hashlib
import json
import shutil
import statistics
from collections import Counter
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def rows(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def pdf_from_markdown(source, output):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Preformatted

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="BodyReport", fontName="Helvetica", fontSize=9.2, leading=12.6, spaceAfter=6))
    styles.add(ParagraphStyle(name="TitleReport", fontName="Helvetica-Bold", fontSize=20, leading=24, spaceAfter=12))
    styles.add(ParagraphStyle(name="H1Report", fontName="Helvetica-Bold", fontSize=13, leading=17, spaceBefore=9, spaceAfter=7))
    styles.add(ParagraphStyle(name="H2Report", fontName="Helvetica-Bold", fontSize=10, leading=14, spaceBefore=7, spaceAfter=4))
    styles.add(ParagraphStyle(name="CellReport", fontName="Helvetica", fontSize=7.1, leading=9.6))
    styles.add(ParagraphStyle(name="CodeReport", fontName="Courier", fontSize=7.4, leading=10, spaceAfter=8))

    def inline(text):
        import re
        text = escape(text)
        text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)
        text = re.sub(r"`(.*?)`", r'<font name="Courier">\1</font>', text)
        return text

    story, lines, i = [], source.splitlines(), 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if line == "<!-- PAGEBREAK -->":
            story.append(PageBreak()); i += 1; continue
        if line.startswith("```"):
            i += 1; block = []
            while i < len(lines) and not lines[i].startswith("```"):
                block.append(lines[i]); i += 1
            story.append(Preformatted("\n".join(block), styles["CodeReport"]))
            i += 1; continue
        if line.startswith("|"):
            data = []
            while i < len(lines) and lines[i].startswith("|"):
                cells = [v.strip() for v in lines[i].strip().strip("|").split("|")]
                if not all(set(c) <= set("-: ") for c in cells):
                    data.append(cells)
                i += 1
            count = len(data[0])
            if count == 9:
                widths = [44, 33, 53, 26, 26, 52, 52, 84, 53]
            elif count == 7:
                widths = [43, 66, 66, 67, 67, 57, 90]
            elif count == 3:
                widths = [135, 155, 233]
            else:
                widths = [523 / count] * count
            table = Table([[Paragraph(inline(c), styles["CellReport"]) for c in row] for row in data],
                          colWidths=widths, repeatRows=1, hAlign="LEFT")
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#18394d")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f5f7")]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LINEBELOW", (0, 0), (-1, 0), .5, colors.HexColor("#18394d")),
            ]))
            # Paragraph text colors override TableStyle unless styled explicitly.
            for c in table._cellvalues[0]:
                c.style = ParagraphStyle(name="TableHeading", parent=styles["CellReport"], textColor=colors.white)
                c.frags[0].textColor = colors.white
            story.extend([table, Spacer(1, 8)]); continue
        if line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            style = "TitleReport" if level == 1 else "H1Report" if level == 2 else "H2Report"
            story.append(Paragraph(inline(line.lstrip("# ")), styles[style])); i += 1; continue
        text = line
        i += 1
        while i < len(lines) and lines[i].strip() and not lines[i].startswith(("#", "|", "```", "<!--", "- ")):
            text += " " + lines[i].strip(); i += 1
        if text.startswith("- "):
            text = "- " + text[2:]
        story.append(Paragraph(inline(text), styles["BodyReport"]))

    def page(canvas, doc):
        canvas.setStrokeColor(colors.HexColor("#b8c6cf")); canvas.line(36, 37, 559, 37)
        canvas.setFont("Helvetica", 8); canvas.setFillColor(colors.HexColor("#52616c"))
        canvas.drawString(36, 25, "UFUG2106 | Stage 1 | Truth Table to Circuit")
        canvas.drawRightString(559, 25, str(doc.page))

    output.parent.mkdir(parents=True, exist_ok=True)
    SimpleDocTemplate(str(output), pagesize=A4, leftMargin=36, rightMargin=36, topMargin=32,
                      bottomMargin=49, title="Stage 1: Truth Table to Circuit", author="Project team").build(story, onFirstPage=page, onLaterPages=page)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", type=Path, default=ROOT / "results/stage1-final-20261118")
    args = ap.parse_args()
    directory = args.results.resolve()
    manifest = json.loads((directory / "manifest.json").read_text())
    assert "finished_utc" in manifest, "experiment is incomplete"
    assert not manifest["source_changed_during_run"] and not manifest["binary_changed_during_run"]
    raw, summary = rows(directory / "runs.csv"), rows(directory / "summary.csv")
    assert len(raw) == 250 and all(r["status"] == "PASS" for r in raw)
    indexed = {(r["case"], r["strategy"]): r for r in summary}
    names = sorted({r["case"] for r in raw})
    assert len(names) == 25
    assert all(r["ad_stable"] == "True" and r["all_target_met"] == "True" for r in summary)
    first = {r["case"]: r for r in raw if r["strategy"] == "final" and r["round"] == "1"}
    comparisons = []
    for name in names:
        f, b = indexed[name, "final"], indexed[name, "fast"]
        af, df, ab, db = (float(r[k]) for r, k in [(f,"area"),(f,"delay"),(b,"area"),(b,"delay")])
        relation = "same" if (af,df)==(ab,db) else "better" if af<=ab and df<=db else "worse" if ab<=af and db<=df else "tradeoff"
        comparisons.append({"case":name,"fast_area":int(ab),"fast_delay":int(db),"final_area":int(af),"final_delay":int(df),
                            "fast_median_ms":float(b["runtime_median_ms"]),"final_median_ms":float(f["runtime_median_ms"]),"relation":relation})
    with (directory / "final_comparison.csv").open("w", newline="") as f:
        writer=csv.DictWriter(f,list(comparisons[0])); writer.writeheader(); writer.writerows(comparisons)
    counts = Counter(r["relation"] for r in comparisons)
    fast_time=sum(r["fast_median_ms"] for r in comparisons)
    final_time=sum(r["final_median_ms"] for r in comparisons)
    fast_area=sum(r["fast_area"] for r in comparisons); final_area=sum(r["final_area"] for r in comparisons)
    rss=rows(directory / "rss_probes.csv")
    max_rss=max(int(r["peak_rss_kb"]) for r in rss if r["strategy"]=="final")
    max_fraction=max(float(r["runtime_ms"])/float(r["runtime_limit_ms"]) for r in raw if r["strategy"]=="final")
    commit=manifest["source_start"]["commit"]["stdout"].strip()
    source_hash=manifest["source_start"]["tree_sha256"]
    binary_hash=manifest["solvers"]["final"]["sha256"]
    table="\n".join(f"| {name[5:8]} | PASS | {first[name]['area']} | {first[name]['delay']} | {first[name]['target_delay']} | {float(first[name]['runtime_ms']):.3f} | {float(indexed[name,'final']['runtime_median_ms']):.3f} | {float(indexed[name,'final']['runtime_min_ms']):.3f}-{float(indexed[name,'final']['runtime_max_ms']):.3f} | {first[name]['runtime_limit_ms']} |" for name in names)
    comparison_table="\n".join(f"| {r['case'][5:8]} | {r['fast_area']}/{r['fast_delay']} | {r['final_area']}/{r['final_delay']} | {r['fast_median_ms']:.3f} | {r['final_median_ms']:.3f} | {r['relation']} | {'yes' if r['final_delay']<=int(first[r['case']]['target_delay']) else 'no'} |" for r in comparisons)
    repeat_dir=ROOT / "results/stage1-standalone-repeat-20261118"
    repeat_manifest=json.loads((repeat_dir / "manifest.json").read_text())
    assert "finished_utc" in repeat_manifest
    repeated=rows(repeat_dir / "runs.csv")
    assert len(repeated)==125 and all(r["status"]=="PASS" for r in repeated)
    assert not repeat_manifest["source_changed_during_run"] and not repeat_manifest["binary_changed_during_run"]
    standalone_rows=rows(ROOT / "results/stage1-standalone-20261118/runs.csv")
    standalone_pass=sum(r["status"]=="PASS" for r in standalone_rows)
    assert standalone_pass==24
    repeat_max=max(float(r["runtime_ms"])/float(r["runtime_limit_ms"]) for r in repeated)
    # Compare every repeated standalone cost against the frozen modular output.
    assert all((r["area"],r["delay"])==(first[r["case"]]["area"],first[r["case"]]["delay"]) for r in repeated)
    report=f"""# Stage 1: Initial Method

## Truth Table to Circuit Optimization

UFUG2106 Final Project. Submission version: `stage1-final-v1`. Prepared 18 November 2026; Stage 1 deadline: 19 November 2026, 23:59.

Our program constructs a shared combinational circuit from a complete multi-output truth table using only AND2, OR2 and NOT. The final method runs nine complementary constructions sequentially under one resource budget, applies a common algebraic rewrite pass, and selects an area-delay compromise. On all 25 released cases, the final default passes all five measured official evaluations and meets every target delay. The source, compilation README and this report form the Stage 1 submission.

## 1. Method: from a truth table to gates

### 1.1 Input, representation and exact costs

Each invocation reads one input file and writes one output file. Input x0 is the most significant bit of the row index; output characters retain their original order. A circuit is a directed acyclic graph (DAG). Signal 0 is constant zero, signals 1 through n are inputs, and gates receive consecutive IDs after the inputs. Constant one is generated by NOT 0. Gates reference only smaller IDs; the last line lists all output signals.

For each normalized, reachable candidate C, area is the sum of the case-specific areas of all emitted gates, counting shared gates once. Arrival times obey t(NOT a)=t(a)+dNOT and t(a op b)=max(t(a),t(b))+dop, with input and constant-zero arrival times zero. Circuit delay is the maximum output arrival time. Unreachable gates are removed before output, so the internal reachable-area measure agrees with the evaluator's count of every listed gate.

### 1.2 Reduced decision diagrams and sharing

For each output function f and a selected variable x, Shannon's identity gives the exact decomposition:

```
f = (NOT x AND f[x=0]) OR (x AND f[x=1]).
```

The recursion reads the corresponding truth-table entries. Identical children eliminate a decision; identical (variable, low child, high child) triples share one decision node, including across outputs. Eight-bit subfunctions on the final three variables are cached. This computes equivalent functions directly from the supplied table; it does not predict an unknown rule from case labels.

The decision graph is mapped into the allowed gates. Constant branches and identical signals simplify immediately. Gate hashing shares identical operations, input order is canonicalized for AND/OR, double negation is removed, and complemented wires are reused. Alternative Shannon mappings use either the sum-of-products identity above or the equivalent product-of-sums form (x OR f0) AND ((NOT x) OR f1).

### 1.3 Grouping, balancing and polarity mapping

Grouping several decision levels collects the selector conditions that reach the same remaining subfunction. Their OR is computed once and combined with that residual function. Top-level grouping, recursive groups of three, and adaptive widths 1-3 explore different amounts of this sharing. Adaptive width uses a residual-multiplicity and estimated gate-cost/delay heuristic, followed by exact whole-circuit measurement.

Associative AND/OR trees merge earlier-arriving signals first. The baseline additionally balances private same-type chains while protecting shared subgraphs. De Morgan alternatives allow a costly AND or OR to be realized using the opposite gate and inversions. Dual-polarity remapping propagates timing requirements backward and uses area flow to choose implementations. Area flow apportions shared cost among consumers; it is an estimate, not an exact global optimizer. Every resulting circuit is ranked using its actual gate area and critical-path delay.

<!-- PAGEBREAK -->

## 2. Portfolio, improvement and selection

### 2.1 Nine constructions in one invocation

The following fixed order is compiled into the final default. All candidates use the same input, gate library, budget and postprocessing. No filename, case number or stored public answer controls synthesis.

| Profile | Construction | Purpose |
|---|---|---|
| github | Original forward BDD, top grouping, balancing, remapping | First complete incumbent |
| influence-sop | Variables ordered by sampled output changes | Different decomposition order |
| forward-pos | Forward BDD, product-of-sums MUX | Alternative gate/sharing structure |
| forward-demorgan | Forward sum-of-products, polarity remapping | Exploit asymmetric gate costs |
| forward-top3 | Group first three levels | Share top selectors/residuals |
| reverse-top3 | Reverse order and top groups of three | Different residual sharing |
| forward-rec3 | Groups of three throughout recursion | Share selectors recursively |
| forward-adaptive3 | Locally choose grouping width 1-3 | Adapt expansion cost |
| historical-adaptive | Earlier forward/conditional reverse policy | Additional order/mapping candidate |

Influence ordering samples at most 512 assignments, counts output changes when each input flips, and uses fixed random seed 2106 with stable ties. The historical profile decides whether to attempt reverse order using table size, resource limits and forward BDD size, with a bounded reverse-node allowance. These are heuristics; their usefulness can vary on future cases. Simple forward/reverse single-variable sum-of-products profiles remain available for experiments but are excluded from the final nine after the documented eleven-profile study.

### 2.2 One shared algebraic improvement pass

Each completed seed is normalized and receives exactly one complete production algebraic sweep. The sweep considers absorption, factoring, reassociation and De Morgan rules, including AND/OR duals. Replacements respect sharing when estimating removable cost and are verified on all assignments of their local boundary inputs. Accepted proposals are rebuilt together through the hashed DAG, avoiding a whole-graph rebuild for each small rewrite. Exact costs then choose between the incoming and rewritten circuit. An interrupted optional seed or sweep is discarded; the saved initial complete circuit provides a fallback.

### 2.3 Area-delay Pareto archive and final decision

The outer archive removes circuits dominated in both exact area and delay. It receives the selected circuit of each completed seed, not every intermediate mapping. Among candidates meeting D <= T, let Amin and Dmin be the best area and delay observed in that feasible set. We select the circuit minimizing:

```
max((A-Amin)/max(1,Amin), (D-Dmin)/max(1,Dmin)).
```

Ties use the sum of the two relative losses, then area. If no candidate meets the target, the fallback minimizes delay, then area and gate count. This is our internal policy, not the undisclosed official scoring formula. It permits area/delay tradeoffs and does not solve minimum area subject to delay exactly. Adding candidates can change the relative ideal point and hence the selected compromise.

### 2.4 Runtime and memory management

All work is single threaded. One wall-clock budget starts at main entry and covers parsing, constructions, rewriting and output. Positive limits reserve max(5 ms, 10% of the limit) for finishing and writing. Optional loops poll the budget; sweep admission uses measured unit-cost estimates with a 1.5 margin. On Linux, positive RAM limits also trigger an RSS check with an 85% threshold. The portfolio uses the remaining case budget; the old fast control instead adds at most a 100 ms local-search window and up to 16 sweeps. Some parsing, first construction, mapping and copying operations are not fully interruptible, so these mechanisms do not prove compliance for arbitrary tight limits.

<!-- PAGEBREAK -->

## 3. Results: all 25 released cases

Official Linux x86-64 evaluator; original inputs and resource fields; WSL2 Ubuntu 22.04, GCC 11.4.0, C++17 -O2, single thread. We ran one warmup and five measured rounds, alternating final and fast configurations serially. The final configuration uses only the required two path arguments, with no TTC environment overrides. The table reports one complete first measured round, plus five-round timing summaries; it does not splice per-case results from different versions.

Case 001 denotes case_001.txt, and similarly for all rows. Area and delay use the assignment's abstract gate units; runtime and runtime limit are milliseconds. T is target delay. A/D was identical across the five measured rounds for each configuration.

| Case | Status | Area | Delay | T | Runtime R1 | Median | Min-max | Limit |
|---|---|---:|---:|---:|---:|---:|---:|---:|
{table}

**Final: 125/125 measured PASS, 125/125 target met.** The fast control also passes 125/125 and meets every target. Maximum measured final runtime/limit ratio is {max_fraction:.1%}. All 25 public cases have omitted or zero RAM limits; separate solver-only peak-RSS probes reach {max_rss:,} KB. These probes are diagnostics, not official RAM-limit tests or worst-case memory bounds.

Runtime is the official evaluator's solver process wall-clock measurement, from program start to exit. It excludes correctness checking; the much longer evaluator invocation duration is not used as solver runtime. Target delay is a soft scoring target; a circuit exceeding it can still PASS if functional, format and resource requirements hold.

<!-- PAGEBREAK -->

## 4. Comparison with the previous fast method

Both methods use the same final binary. The fast control explicitly sets TTC_STRATEGY=sweep, reproducing the preceding default pipeline; the final method has no overrides. A/D denotes area/delay, and time columns are per-case five-round medians in milliseconds. Better means both A/D no worse and at least one strictly better; tradeoff means one improves while the other worsens.

| Case | Fast A/D | Final A/D | Fast ms | Final ms | A/D change | Target met |
|---|---:|---:|---:|---:|---|---|
{comparison_table}

The final selection dominates the fast circuit in {counts['better']} cases, matches it in {counts['same']}, and trades area for delay in {counts['tradeoff']}; {counts['worse']} cases are dominated by the control. Sum of per-case runtime medians: {fast_time:.3f} ms (fast) versus {final_time:.3f} ms (final), a {final_time/fast_time:.2f}x factor. Area sums are {fast_area:,} and {final_area:,}; these sums are descriptive and are not an official aggregate score. Lower delay in some cases costs additional area, and the portfolio pays runtime to explore more circuits.

For case 024, the previous circuit is 178001/69 and the final choice is 149346/63: area falls by about 16.1% and delay by about 8.7%. In contrast, case 007 changes from 112652/73 to 142253/56: the chosen circuit is faster but larger. The final default follows our selected compromise policy. Without the official numerical weighting, this evidence cannot establish which configuration earns a higher overall grade.

The earlier teammate experiment independently found the same 8/7/10 A/D split on Linux x86-64 in an Apple Silicon container, with a 2.56x runtime-median sum. Its timings are preserved separately and are not mixed with the WSL measurements above.

<!-- PAGEBREAK -->

## 5. Validation, reproducibility and limitations

### 5.1 Correctness and independent checks

Shannon decomposition, elimination of equal branches, grouping of selectors and Boolean rewrite identities preserve each output function for every input. Gate construction remains topological and normalization removes unreachable logic. The official evaluator performs the end-to-end correctness and resource checks on every released case.

The final default additionally passed 400 generated cases with exhaustive simulation and independent format/area/delay checks. These include all single-output functions up to three inputs, constants, direct wires, sharing, complements, random functions and resource fields. Local-rewrite tests verified 510 candidate substitutions and cutoff behavior. Seed-interface tests performed 154 full output checks across eleven profiles, deterministic repeats, invalid-profile rejection and budget cancellation. Earlier held-out structured/permuted functions and larger random gate-network studies are preserved in the repository; they are evidence of additional coverage, not hidden-case scores.

The exported standalone source was compiled independently with the README command and passed the same 400 generated checks. Its first official full-set run passed 24/25: case 011 hit TIME_LIMIT (100 ms), and the other 24 passed. An isolated diagnostic then passed case 011 in 33.947 ms. We retained the original failure and ran five new complete rounds without changing the source or binary: all 125/125 passed, met their target delays, and matched the modular area/delay values in the tables. Maximum runtime/limit ratio in these repeat rounds was {repeat_max:.1%}. This isolated timeout and the spread of recorded times show that resource compliance is sensitive to execution conditions; repeated success is not a guarantee against future timing failures. Both the initial and repeat result folders are included in the delivery.

### 5.2 Frozen version and measurement evidence

Algorithm source commit: `{commit}`. Later documentation and packaging commits preserve the same C++ sources. All measured rounds used unchanged sources and binary, verified by before/after hashes. Full source, binary, evaluator and individual input hashes, compiler, environment, commands and resource fields are recorded in the experiment manifest.

```
Source-tree SHA-256:
{source_hash}
Measured modular binary SHA-256:
{binary_hash}
```

Primary evidence: results/stage1-final-20261118/runs.csv (250 measurements), summary.csv, final_comparison.csv, rss_probes.csv and manifest.json. Raw official per-round CSV reports are retained under its raw/ directory. Standalone evidence: results/stage1-standalone-20261118/ (initial 24/25), results/stage1-standalone-repeat-20261118/ (five complete 25/25 rounds). The exported standalone C++ source receives its own manifest and official validation; the package VERSION.json binds the distributed files. Course input files and the evaluator are not redistributed.

<!-- PAGEBREAK -->

## 6. Limitations and next stage

### 6.1 Complexity and limits of the result

Reading the complete truth table costs at least O(m * 2^n). Reduced BDDs can still grow exponentially with n and depend strongly on variable order. Grouping enumerates up to 2^k selectors for width k; widths are deliberately bounded. Hashing and memoization reuse subfunctions and gates but do not remove the exponential worst case. Candidate normalization, exact measurement and DAG rebuilding also cost time and memory.

The eleven-profile retention study used the public Stage 1 cases, so its ordering and retention decisions may favor this set. Functional correctness rests on identities and validation, whereas quality and runtime on new cases remain empirical. The implementation does not include the separate original AIG project. It does not implement global Pareto dynamic programming, unrestricted variable sifting, or an exact full-case optimizer.

### 6.2 Research alternatives and next stage

The repository preserves additional greedy, beam, simulated annealing, multistart and larger-cut searches. Many costly profiles exceeded original case time limits; research runs with relaxed limits are explicitly separated from compliant results. Bounded SAT/MILP models and universal small-function templates were explored offline. Their local proofs do not establish a whole-case optimum, and external solvers are not dependencies of the submitted execution path.

For Stage 2 we would compare adaptive seed scheduling by expected benefit/cost, sharing-aware rewrites and richer order/mapping alternatives, keeping the Stage 1 version frozen as the comparison baseline. All newly released cases should be evaluated with both versions. This report covers only the 25 Stage 1 cases; Stage 2 and the 50 hidden final cases have not been evaluated.

### 6.3 Compile and run

The accompanying README gives the complete standalone instructions:

```
g++ -O2 -std=c++17 solver.cpp -o solver
./solver INPUT_PATH OUTPUT_PATH
```

No Python, SAT solver, MILP solver or external library is required by the executable. The full repository can alternatively be built with make. This release prepares the required source, README and report; uploading to GitHub does not submit them to the course platform.
"""
    (ROOT / "docs/stage1-report.md").write_text(report, encoding="utf-8")
    # Preserve evaluator reports without including copyrighted input tables.
    artifact = Path(manifest["artifact_directory"])
    if not artifact.exists():
        artifact = ROOT / "artifacts" / directory.name
    destination = directory / "raw"; destination.mkdir(exist_ok=True)
    for run in manifest["runs"]:
        shutil.copyfile(artifact / Path(run["report"]).name, destination / Path(run["report"]).name)
    pdf_from_markdown(report, ROOT / "output/pdf/stage1-report.pdf")
    (directory / "report-summary.json").write_text(json.dumps({"ad_relations":dict(counts),"fast_median_sum_ms":fast_time,
        "final_median_sum_ms":final_time,"fast_area_sum":fast_area,"final_area_sum":final_area,
        "source_commit":commit,"source_tree_sha256":source_hash,"max_runtime_limit_fraction":max_fraction},indent=2)+"\n")
    print("Wrote Markdown, PDF, comparison and preserved raw official CSV reports.")


if __name__ == "__main__":
    main()
