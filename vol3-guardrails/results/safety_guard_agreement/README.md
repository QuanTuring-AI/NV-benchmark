# Safety Guard 8B v3: how often two runs give a different verdict on the same item

[← Vol.3 README](../../README.md) · the two pre-registered looks at the same model on two servers: [`../model_free_nim/`](../model_free_nim/README.md), [`../safety_guard_recheck/`](../safety_guard_recheck/README.md)

**What this is.** The volume holds 11 runs of Llama 3.1 Nemotron Safety Guard 8B v3 over the same items: five on upstream vLLM 0.20.2 (2, 6 and 8 October), two in the generic NIM 2.0.12, two in the model's own NIM 1.14.0, and one each on upstream vLLM 0.27.1 and on the upstream image v0.10.0. Here every run is paired with every other (55 pairs, none left out) and the items on which the two gave a different verdict are counted, on the whole per-item file of each track (2,423 prompts, 813 responses).

**What it is not.** Nothing is judged: there is no threshold, no pass and no fail. The two pre-registered looks linked above each set a tolerance on rates beforehand, and each recorded "does not pass" for it; those records stand. This table gives the yardstick those files offer for reading such differences: how often the same server, started again, disagrees with itself.

**Order of work.** [`plan.json`](plan.json) (the runs, the pairs, how agreement is counted, and what the article would say in which case) was written at 2026-10-09T13:18:31+0800, before the pairs were computed; [`pairs.json`](pairs.json) records its SHA-256 and the program refuses to run on a changed plan. Four of the 55 pairs had been computed before, as parts of the two pre-registered looks: J6M and J6-tonight, M and U1, M and U2, U1 and U2. The others had not.

## The runs

| Run | Day | Server | Per-item files |
|---|---|---|---|
| J6 | 2026-10-02 | upstream vLLM 0.20.2 | [`../../results/p93_judges/J6/`](../../results/p93_judges/J6/) |
| J6-today | 2026-10-06 | upstream vLLM 0.20.2 | [`../../results/safety_guard_nim/J6-today/`](../../results/safety_guard_nim/J6-today/) |
| J6-tonight | 2026-10-08, night | upstream vLLM 0.20.2 | [`../../results/model_free_nim/J6-tonight/`](../../results/model_free_nim/J6-tonight/) |
| U1 | 2026-10-08, day | upstream vLLM 0.20.2 | [`../../results/safety_guard_recheck/U1/`](../../results/safety_guard_recheck/U1/) |
| U2 | 2026-10-08, day | upstream vLLM 0.20.2 | [`../../results/safety_guard_recheck/U2/`](../../results/safety_guard_recheck/U2/) |
| J6M | 2026-10-08, night | the generic NIM 2.0.12 | [`../../results/model_free_nim/J6M/`](../../results/model_free_nim/J6M/) |
| M | 2026-10-08, day | the generic NIM 2.0.12 | [`../../results/safety_guard_recheck/M/`](../../results/safety_guard_recheck/M/) |
| J6N | 2026-10-06 | the model's own NIM 1.14.0 | [`../../results/safety_guard_nim/J6N/`](../../results/safety_guard_nim/J6N/) |
| J6N-tonight | 2026-10-08, night | the model's own NIM 1.14.0 | [`../../results/model_free_nim/J6N-tonight/`](../../results/model_free_nim/J6N-tonight/) |
| J6-v0271 | 2026-10-08, night | upstream vLLM 0.27.1 | [`../../results/model_free_nim/J6-v0271/`](../../results/model_free_nim/J6-v0271/) |
| J6-v010 | 2026-10-06 | upstream vLLM image v0.10.0 | [`../../results/parser_and_engine_version/J6-v010/`](../../results/parser_and_engine_version/J6-v010/) |

## By kind of pair

Same verdict: over the items present in both files, the share with the same verdict (as criterion C3 of the second look counts it). A pair's smallest and largest value over the pairs of its group:

| Pairs | How many | Prompts: same verdict | Prompts: items that differ | Responses: same verdict | Responses: items that differ |
|---|---|---|---|---|---|
| Upstream vLLM 0.20.2 against upstream vLLM 0.20.2 (another day or another container) | 10 | 99.55% to 99.79% | 5 to 11 | 99.02% to 99.63% | 3 to 8 |
| The generic NIM 2.0.12 against upstream vLLM 0.20.2 | 10 | 99.46% to 99.63% | 9 to 13 | 98.89% to 99.63% | 3 to 9 |
| The model's own NIM 1.14.0 against upstream vLLM 0.20.2 | 10 | 99.46% to 99.75% | 6 to 13 | 99.02% to 99.75% | 2 to 8 |
| Every other pair (a NIM against its own second run or against the other NIM; another version of upstream vLLM against anything) | 25 | 99.38% to 99.75% | 6 to 15 | 99.02% to 99.88% | 1 to 8 |

- On prompts the range of the generic NIM 2.0.12 against upstream overlaps the range of upstream against itself (its smallest value, 99.46%, is below upstream's smallest, 99.55%); on responses the range of the generic NIM 2.0.12 against upstream overlaps the range of upstream against itself (its smallest value, 98.89%, is below upstream's smallest, 99.02%).
- On prompts the range of the model's own NIM 1.14.0 against upstream overlaps the range of upstream against itself (its smallest value, 99.46%, is below upstream's smallest, 99.55%); on responses the range of the model's own NIM 1.14.0 against upstream overlaps the range of upstream against itself.
- These are ranges over ten pairs each, and the pairs of a group share runs: they are not ten independent observations, and no test is made on them.

## Direction, described and not tested

For each pair [`pairs.md`](pairs.md) also gives, over the items on which both runs gave a verdict, how many are unsafe in the first run only and how many in the second only.

Each NIM run against the five runs of upstream vLLM 0.20.2. The sums are over that run's five pairs; "larger" and "smaller" count the pairs in which the NIM run has more, or fewer, unsafe-only items than the upstream run.

| NIM run | Prompts: unsafe on upstream only, sum | on the NIM only, sum | NIM larger · smaller, of 5 pairs | Responses: unsafe on upstream only, sum | on the NIM only, sum | NIM larger · smaller, of 5 pairs |
|---|---|---|---|---|---|---|
| J6M: the generic NIM 2.0.12, night of 8 October | 24 | 26 | 2 · 2 | 5 | 17 | 4 · 0 |
| M: the generic NIM 2.0.12, day of 8 October | 40 | 17 | 0 · 5 | 10 | 22 | 4 · 0 |
| J6N: the model's own NIM 1.14.0, 6 October | 17 | 39 | 5 · 0 | 13 | 15 | 3 · 2 |
| J6N-tonight: the model's own NIM 1.14.0, night of 8 October | 15 | 27 | 5 · 0 | 6 | 13 | 3 · 1 |

Sums over pairs that share a run count the same items more than once: the table describes, it does not test. What it shows of the direction is in its columns, track by track and run by run.

The generic NIM against its own second run (J6M and M) differs on 15 prompts and 6 responses; the largest count among the ten upstream pairs is 11 prompts and 8 responses.

## Every pair

[`pairs.md`](pairs.md) lists the 55 pairs with their counts; [`pairs.json`](pairs.json) has the same with the SHA-256 of every file read.

## Checks

Before it writes anything the program pairs one file with three copies of itself whose answer is known: the file itself (0 items differ), a copy with 7 unsafe verdicts set to safe (7 differ, all 7 on the side of the original), and a copy without its first item (1 item in one file only). If one of them gives another answer, no table is written.

## Run it again

```bash
python vol3-guardrails/scripts/safety_guard_agreement.py run
```

It reads only files of this repository (item ids and verdicts; no text of the test sets is here) and rewrites `pairs.json` and `pairs.md`.
