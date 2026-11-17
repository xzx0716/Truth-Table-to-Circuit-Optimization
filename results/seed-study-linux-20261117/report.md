# Official Linux seed comparison

The controlled comparison uses 11 seed profiles, 25 cases and 5 measured rounds. It has 1375/1375 expected timed records. Status counts are {'PASS': 1375}. Output hashes are available for 1375 records.

Every controlled run uses the same downstream optimization and output selection. Three-dimensional membership uses median end-to-end runtime. Retention based on runtime also requires disjoint observed ranges plus a margin of max(0.2 ms, 5% of the candidate median). Admission requires correct outputs in all measured rounds, stable area and delay, and identical netlist hashes when the evaluator provides them. All claims concern observed profiles. The `deployed` solver is reported separately because its optimization path differs.

33 distinct new A/D points across 19 cases. 17 cases have a smaller area than the controlled reference while still reaching the case's delay target.

| Seed | Eligible cases | Met target | New A/D points | Runtime contribution cases | Keep |
|---|---:|---:|---:|---:|---|
| github | 25 | 25 | 0 | 0 | True |
| forward-sop | 25 | 13 | 0 | 0 | False |
| reverse-sop | 25 | 10 | 0 | 0 | False |
| influence-sop | 25 | 15 | 9 | 5 | True |
| forward-pos | 25 | 13 | 0 | 1 | True |
| forward-demorgan | 25 | 16 | 0 | 4 | True |
| forward-top3 | 25 | 19 | 1 | 6 | True |
| reverse-top3 | 25 | 17 | 1 | 4 | True |
| forward-rec3 | 25 | 22 | 12 | 3 | True |
| forward-adaptive3 | 25 | 14 | 1 | 0 | True |
| historical-adaptive | 25 | 25 | 9 | 0 | True |

Selected paired measurements with an A/D improvement and separated time ranges.

| Case | Seed | Reference area/delay/ms | Candidate area/delay/ms |
|---|---|---:|---:|
| case_003.txt | forward-rec3 | 25200 / 52 / 38.394 | 23248 / 51 / 33.757 |

The deployed comparisons in `deployed_comparison.csv` are per case, with differences computed as candidate minus deployed. A difference includes the effect of their different downstream pipelines. `per_case.csv` lists all new points and exclusions are identified in `comparison.csv`. The suggestions in `retained.json` were evaluated independently, not timed as a single portfolio.
