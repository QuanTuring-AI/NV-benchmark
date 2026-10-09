# The timed cells of the Llama Guard 3 arm, run three times

*Two more runs on 2026-10-04, 04:00–04:17 (+0800), of the four timed cells first run on 2026-10-03 ([`../p102_followup/`](../p102_followup/README.md)). Same frozen pre-registration, same harness files, same image, weights and items; each run in a newly started container. Working data of the judge study; not published as an article.*

**Why.** During the first run, short commands that had nothing to do with it were started on the same host. Their effect on the durations was not known. The four cells were run twice more with nothing started from the measuring session between the launch and the exit of the runs (checked afterwards against the session's own record: no call between 04:00:32 and 04:17:28).

**What was fixed before the two runs.** [`BEFORE_THE_RUN.md`](BEFORE_THE_RUN.md), written at 03:59:44: what is compared, the reading rule and what either outcome would look like. Two repeats and not one, because one quiet run cannot tell a disturbance from the difference between two containers.

## The three runs side by side

Reading rule (fixed beforehand): a figure of the first run that lies between the two repeats, or within 5% of the nearer one, is "not distinguishable"; further out it is "outside", with the direction.

| Track | Figure | First run (2026-10-03 23:00) | Repeat 1 | Repeat 2 | Reading |
|---|---|---|---|---|---|
| Input | c=1 p50 per verdict | 51.4 ms | 60.1 | 65.9 | **outside the two repeats, lower** |
| Input | c=1 p99 | 105.6 ms | 116.6 | 112.9 | outside, lower |
| Input | c=16 verdicts per second | 98.1 | 95.3 | 94.6 | within 5% |
| Input | c=16 p50 / p99 | 148.4 / 372.3 ms | 151.0 / 363.8 | 151.1 / 368.8 | within 5% |
| Output | c=1 p50 per verdict | 52.3 ms | 63.6 | 63.5 | **outside the two repeats, lower** |
| Output | c=1 p99 | 100.8 ms | 106.1 | 113.3 | within 5% |
| Output | c=16 verdicts per second | 64.8 | 64.1 | 63.4 | within 5% |
| Output | c=16 p50 / p99 | 232.1 / 399.1 ms | 234.1 / 407.1 | 238.7 / 388.1 | within 5% / between |

- **Neither outcome written down beforehand happened.** A disturbance would have made the first run slower; no effect would have put it inside or near the repeats. The first run's c=1 figures are *faster* than both repeats. What can be said: there is no sign that the commands on the host slowed the first run. It cannot be said that they made it faster.
- **The c=16 rate held**: the three runs are within 4% of each other on both tracks.
- **The c=1 median of this arm is to be given as a range: 51 to 66 ms** (input), 52 to 64 ms (output). A single value of it should not be quoted.
- Control of the comparison program: in every run the c=16 rate is several times the c=1 rate (5.8, 6.1, 6.3 on the input track; 4.0, 4.4, 4.3 on the output track). Before the runs the program was tried on planted copies: a c=1 median made 30% faster was read as "outside", three flipped outcomes were counted.
- **The same arm judged again in another container** gave the same outcome as the first run's c=16 cell for 2,419 and 2,421 of 2,423 input items and for 810 and 813 of 813 output items. At temperature 0.0 the verdicts are not identical item by item across containers. Detection counts on the Aegis prompts over the three runs: 690, 688, 691 of 1,039; false alarms 60, 61, 59 of 889.

Both repeats: 3,636 calls in four cells, every call returned, no error, no answer without a verdict; 2 of 2 prechecks passed; five idle-card gates each, all passed (one in repeat 1 after three samples and 152 s, because the sample after the preceding cell had shown 7% utilization).

## Looked at afterwards (not part of the rule fixed beforehand)

Everything in this section was looked at after the comparison above was known.

**The per-call durations of this arm come in two groups, and the median falls between them.** Answers of 3 tokens (`safe`) take about 44 to 49 ms, answers of 6 tokens (`unsafe` and a category) about 74 to 78 ms; 120 of the 200 input items are of the first kind, so the 100th value lies in the tail of the first group. Over the three runs each group's own median moved by 3 to 5 ms (3 tokens: 43.7, 46.8, 48.8 ms; 6 tokens: 73.9, 78.1, 77.7 ms) while the median of the whole cell moved by 9 to 14 ms. [`durations_closer_look.txt`](durations_closer_look.txt).

**Inside each group there is a second cluster about 16 ms higher, and its share changes from run to run.** Input track, 3-token answers that took 56 ms or more: 14 of 120 in the first run, 28 of 120 and 49 of 120 in the repeats.

**The same two clusters appear without any model.** A stand-in server in a CPU-only container that answers every request after a 40 ms busy wait, called 300 times the way the harness calls a server ([`connection_probe/`](connection_probe/), run at 04:26):

| Client | p10 | p50 | p90 | Calls more than 10 ms above p10 | Shape |
|---|---|---|---|---|---|
| a new connection per call (what the harness does) | 43.6 | 54.2 | 65.7 | 151 of 300 | two clusters, 42–51 ms and 58–67 ms |
| the same, with a 1 ms timer requested from Windows | 43.9 | 59.2 | 66.1 | 166 of 300 | the same two clusters |
| a new connection per call, again | 44.8 | 57.1 | 65.2 | 157 of 300 | the same two clusters |
| one kept connection | 84.6 | 89.7 | 92.4 | 3 of 300 | one cluster, about 45 ms higher |

On this host (Windows 11, Docker Desktop, a container port published on 127.0.0.1) a call with a new connection costs the server's time plus about 3 ms or about 19 ms, and the share of the slower kind drifts. Which part of the path does it was not established. The probe shows that the host's path produces the two clusters by itself; it does not show that a real model server adds nothing of its own.

**Each arm's own median region** ([`median_region_per_arm.txt`](median_region_per_arm.txt), every arm for itself): the span from the 45th to the 55th percentile of the c=1 durations, as a share of the median, is 36% for this arm's first run and between 8% and 22% for the seven arms of the judge study. A wide span means that the median moves when a few calls shift.

**The two repeats were quiet on one side only.** Nothing was started from the measuring session, but the desktop held about 1.2 GiB of the card's memory during the repeats against about 0.35 GiB during the first run, and one sample in repeat 1 showed 7% utilization. The idle-card gate looks at utilization and power, not at memory.

## What follows for the figures of this study

- Speed of a judge is led by the **c=16 rate**. A c=1 median is a secondary figure and carries its boundary: client wall time, a new connection per call, on a host whose published port adds about 3 or about 19 ms.
- The direct arms of the judge study (J4, J5, J6) were measured through the same kind of connection; their c=1 medians contain a share of the slower kind that was not measured. They were not run again.
- The arms through Guardrails use the library's own kept connections, the other row of the probe table.

## Files

```
BEFORE_THE_RUN.md                  written before the two runs: what is compared and how it is read
quiet_run_1/ · quiet_run_2/        events.jsonl and LG3/ (per-item files without text, cells.jsonl, prechecks, summary.json), as in ../p102_followup/
comparison.json · comparison.txt   the three runs by the rule (../../scripts/lg3_repeats_compare.py)
durations_closer_look.txt          ../../scripts/lg3_repeats_look_closer.py
median_region_per_arm.txt          ../../scripts/lg3_repeats_median_region.py
connection_probe/                  server.py (runs in python:3.12-slim), client.py, the output of 2026-10-04
```

The three programs were written in a working folder and are here with their folder names changed and nothing else; `comparison.json` made from this directory is byte-identical to the one made there. To recompute a repeat's summary: `P102_RESULTS=<this directory>/quiet_run_1 python ../../scripts/p102_analyze.py --arm LG3`.
