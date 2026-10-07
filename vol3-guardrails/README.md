# Vol.3 · NeMo Guardrails on one RTX 5090: the models behind the rail — baseline data and the rail study
*The data here is the baseline for the judge study: Llama 3.1 8B judging its own answers through NeMo Guardrails 0.21.0 and 0.23.0, the self-check `max_tokens` setting, and the rails under load. The study itself (judge quality against latency) has not been published.*

> **Reproduce:** `git checkout vol3`. The harnesses here are frozen with the paths they were written with; [`../PATH_MAP.md`](../PATH_MAP.md) maps them to this directory and gives the commit at which those paths exist, for a byte-for-byte rerun.
The measurements, their boundaries and their results are in [`BASELINE.md`](BASELINE.md). Harnesses are in `scripts/`, results in `results/`.

![NeMo Guardrails on one RTX 5090: the models behind the rail](figures/cover_vol3.png)

*One RTX 5090 · one safety model on the card at a time · Aegis 2.0 test split and XSTest*

## The judge study: two figures, and where each number comes from

*Working data; no article has been published from it.* The study's result directories are [`results/p93_judges/`](results/p93_judges/README.md) (seven arms, one safety model on the card at a time), [`results/p102_followup/`](results/p102_followup/README.md) (a reasoning parser on the server; Llama Guard 3 8B as a reference arm) and [`results/lg3_timing_repeats/`](results/lg3_timing_repeats/README.md) (the reference arm's timed cells, repeated twice on a quiet host). Each of those READMEs gives the boundaries of its run.

**Added 2026-10-06:** [`results/safety_guard_nim/`](results/safety_guard_nim/README.md) serves the Safety Guard model through its NIM (arm J6N, the ninth point of both figures), with the study's arm J6 run again the same night, the prompt template of the NIM's documentation, and the model behind the NeMo Guardrails content-safety rail as the library documents it.

**Added 2026-10-06 (afternoon):** [`results/parser_and_engine_version/`](results/parser_and_engine_version/README.md) has two follow-up arms: the reasoning parser on the whole of both tracks (arm J2P: with the parser on the server the rail follows the model's answer on all but 2 of 3,236 items), and the Safety Guard model on the upstream vLLM image tagged v0.10.0 (arm J6-v010: within 4% of the NIM's rate, about 17% below upstream 0.20.2). The parser arm is the tenth point of both figures since 2026-10-07; J6-v010 is not drawn.

**Scope rule of the study.** Every figure is about one arm. Nothing here combines the per-item verdicts of two arms, and the figures and tables below state nothing that relates one arm to another: they list each arm's own values side by side.

### Figures

Aegis 2.0 prompts (the model sees the request alone):

![Aegis 2.0 prompts: share of harmful items flagged, with its Wilson 95% interval, against verdicts per second at 16 concurrent requests; one point per arm](figures/detection_vs_rate_input_dark.png)

Aegis 2.0 responses (the model sees the request and the response):

![Aegis 2.0 responses: share of harmful items flagged, with its Wilson 95% interval, against verdicts per second at 16 concurrent requests; one point per arm](figures/detection_vs_rate_output_dark.png)

*Drawn by [`figures/plot_detection_vs_rate.py`](figures/plot_detection_vs_rate.py) from the arms' own `summary.json` files, in a light and a dark version (SVG and PNG). Every point is listed with its source file and keys in [`figures/detection_vs_rate_points.json`](figures/detection_vs_rate_points.json); the script reads every value back from its source on each run.*

- **Horizontal axis:** verdicts per second in the cell that ran the whole set at 16 concurrent requests, each arm alone on the card.
- **Vertical axis:** harmful items flagged ÷ harmful items, with the Wilson 95% interval as the bar. What the figures do not show: harmless items flagged (false alarms), XSTest, and the items without a verdict. Those are in the tables below and in [`results/p93_judges/table.md`](results/p93_judges/table.md).
- **Timings at one request at a time are not on the figures.** On this host the median of such a cell moved between runs of the same arm (51 · 60 · 66 ms for the reference arm's input track), while the rate at 16 concurrent requests stayed within 4% (98.1 · 95.3 · 94.6 verdicts per second). The one-at-a-time medians in the tables are therefore a range on this host, not a property of a model.
- The two arms asked through Guardrails' content-safety rail on a 200-item subset (`J4G`, `J5G`) have no timed cell and are not drawn.
- **A second outline around a marker** means that the arm is served by the model's NIM image (J6N), or that the server runs the reasoning parser (J2P).
- **The parser arm's point reads two files.** Its height is the arm's own whole-set cell (J2P, the first container of that arm). Its position along the horizontal axis is the whole-set cell of a second container of the same arm (J2P-repeat), because the first container ran that cell at about half the usual rate while its one-at-a-time timings were normal ([`results/parser_and_engine_version/`](results/parser_and_engine_version/README.md)). The second container's own share of harmful items flagged is in the table below (prompts 66.5%, responses 62.7%); the point table names both files.
- **The line under each figure gives the days and the driver versions** of the drawn arms, read from the arms' own files: the seven arms of the study on 2 October and the reference arm on 3 October with driver 591.86; the NIM arm and the parser arm on 6 October with 610.88. The same-day check of the study's arm J6 on 6 October is in [`results/safety_guard_nim/`](results/safety_guard_nim/README.md), section 2.
- Two squares of one colour stand for one model on two servers: Llama 3.1 Nemotron Safety Guard 8B v3 on upstream vLLM (J6, measured 2026-10-02) and through its NIM (J6N, measured 2026-10-06). The same-night partner of J6N is in [`results/safety_guard_nim/`](results/safety_guard_nim/README.md), section 2.

### The arms

| Arm | Model | Served by | How it is asked | Reasoning |
|---|---|---|---|---|
| J0 | Llama 3.1 8B Instruct | NIM 2.0.12 | NeMo Guardrails 0.24.1 self-check action, answer limited to 3 tokens | — |
| J1 | Llama 3.1 8B Instruct | NIM 2.0.12 | the same, the library's default limit | — |
| J2 | Nemotron 3 Nano | NIM 2.0.12 | the same | on |
| J3 | Nemotron 3 Nano | NIM 2.0.12 | the same | off |
| J4 | Nemotron 3.5 Content Safety | upstream vLLM 0.20.2 | direct request, the model's own prompt | off |
| J5 | Nemotron 3.5 Content Safety | upstream vLLM 0.20.2 | the same | on |
| J6 | Llama 3.1 Nemotron Safety Guard 8B v3 | upstream vLLM 0.20.2 | direct request, the model card's prompt | — |
| LG3 | Llama Guard 3 8B (reference arm) | upstream vLLM | direct request, the model's own prompt | — |
| J6N | Llama 3.1 Nemotron Safety Guard 8B v3 | NIM 1.14.0, generic profile (vLLM, BF16) | as J6: direct request, the model card's prompt | — |
| J2P | Nemotron 3 Nano | NIM 2.0.12, started with `--reasoning-parser nemotron_v3` | as J2: the self-check action | on |

### Claim → evidence

Every number of the study that an article may use, with the file it comes from and the key inside that file. Paths are relative to this directory. `Check`: `rounds` (the stored value rounds to the number). In a row with several numbers, they are in the order of the names in braces in the key.

**Aegis 2.0 prompts (input track), arms J0 · J1 · J2 · J3 · J4 · J5 · J6**

| In the post | Number | File | Key | Check |
|---|---|---|---|---|
| Aegis 2.0 prompts: harmful · harmless · items read | 1,039 · 889 · 1,928 | `results/p93_judges/table.json` | `arms.J0.tracks.input.quality.aegis2.{harmful,harmless,items}` | rounds |
| Aegis 2.0 prompts: harmful items flagged, % | 72.9 · 73.0 · 66.5 · 54.9 · 89.3 · 87.7 · 87.8 | `results/p93_judges/table.json` | `arms.{J0,J1,J2,J3,J4,J5,J6}.tracks.input.quality.aegis2.detection.rate * 100` | rounds |
| Aegis 2.0 prompts: the same, lower end of the Wilson 95% interval | 70.1 · 70.2 · 63.6 · 51.8 · 87.3 · 85.5 · 85.6 | `results/p93_judges/table.json` | `arms.{J0,J1,J2,J3,J4,J5,J6}.tracks.input.quality.aegis2.detection.wilson95[0] * 100` | rounds |
| Aegis 2.0 prompts: the same, upper end | 75.5 · 75.6 · 69.3 · 57.9 · 91.1 · 89.5 · 89.6 | `results/p93_judges/table.json` | `arms.{J0,J1,J2,J3,J4,J5,J6}.tracks.input.quality.aegis2.detection.wilson95[1] * 100` | rounds |
| Aegis 2.0 prompts: harmful items flagged, count | 757 · 758 · 691 · 570 · 928 · 911 · 912 | `results/p93_judges/table.json` | `arms.{J0,J1,J2,J3,J4,J5,J6}.tracks.input.quality.aegis2.detection.k` | rounds |
| Aegis 2.0 prompts: harmless items flagged (false alarm), % | 15.4 · 15.4 · 10.9 · 3.8 · 20.8 · 20.8 · 15.4 | `results/p93_judges/table.json` | `arms.{J0,J1,J2,J3,J4,J5,J6}.tracks.input.quality.aegis2.false_alarm.rate * 100` | rounds |
| Aegis 2.0 prompts: the same, lower end of the Wilson 95% interval | 13.2 · 13.2 · 9.0 · 2.7 · 18.3 · 18.3 · 13.2 | `results/p93_judges/table.json` | `arms.{J0,J1,J2,J3,J4,J5,J6}.tracks.input.quality.aegis2.false_alarm.wilson95[0] * 100` | rounds |
| Aegis 2.0 prompts: the same, upper end | 17.9 · 17.9 · 13.1 · 5.3 · 23.6 · 23.6 · 17.9 | `results/p93_judges/table.json` | `arms.{J0,J1,J2,J3,J4,J5,J6}.tracks.input.quality.aegis2.false_alarm.wilson95[1] * 100` | rounds |
| Aegis 2.0 prompts: harmless items flagged, count | 137 · 137 · 97 · 34 · 185 · 185 · 137 | `results/p93_judges/table.json` | `arms.{J0,J1,J2,J3,J4,J5,J6}.tracks.input.quality.aegis2.false_alarm.k` | rounds |
| Aegis 2.0 prompts: F1 of the harmful class, over items with a verdict | 0.788 · 0.789 · 0.758 · 0.695 · 0.862 · 0.854 · 0.874 | `results/p93_judges/table.json` | `arms.{J0,J1,J2,J3,J4,J5,J6}.tracks.input.quality.aegis2.f1_unsafe_over_items_with_verdict` | rounds |
| Aegis 2.0 prompts: items without a verdict, % | 0.8 · 0.9 · 0.2 · 0.6 · 0.0 · 0.3 · 0.0 | `results/p93_judges/table.json` | `arms.{J0,J1,J2,J3,J4,J5,J6}.tracks.input.quality.aegis2.no_verdict.share * 100` | rounds |

**XSTest prompts (input track), arms J0 · J1 · J2 · J3 · J4 · J5 · J6**

| In the post | Number | File | Key | Check |
|---|---|---|---|---|
| XSTest prompts: harmful · harmless · items read | 200 · 250 · 450 | `results/p93_judges/table.json` | `arms.J0.tracks.input.quality.xstest.{harmful,harmless,items}` | rounds |
| XSTest prompts: harmful items flagged, % | 86.5 · 86.5 · 89.5 · 72.5 · 99.0 · 98.0 · 94.0 | `results/p93_judges/table.json` | `arms.{J0,J1,J2,J3,J4,J5,J6}.tracks.input.quality.xstest.detection.rate * 100` | rounds |
| XSTest prompts: the same, lower end of the Wilson 95% interval | 81.1 · 81.1 · 84.5 · 65.9 · 96.4 · 95.0 · 89.8 | `results/p93_judges/table.json` | `arms.{J0,J1,J2,J3,J4,J5,J6}.tracks.input.quality.xstest.detection.wilson95[0] * 100` | rounds |
| XSTest prompts: the same, upper end | 90.6 · 90.6 · 93.0 · 78.2 · 99.7 · 99.2 · 96.5 | `results/p93_judges/table.json` | `arms.{J0,J1,J2,J3,J4,J5,J6}.tracks.input.quality.xstest.detection.wilson95[1] * 100` | rounds |
| XSTest prompts: harmful items flagged, count | 173 · 173 · 179 · 145 · 198 · 196 · 188 | `results/p93_judges/table.json` | `arms.{J0,J1,J2,J3,J4,J5,J6}.tracks.input.quality.xstest.detection.k` | rounds |
| XSTest prompts: harmless items flagged (false alarm), % | 18.4 · 18.4 · 6.0 · 1.6 · 25.6 · 25.6 · 24.0 | `results/p93_judges/table.json` | `arms.{J0,J1,J2,J3,J4,J5,J6}.tracks.input.quality.xstest.false_alarm.rate * 100` | rounds |
| XSTest prompts: the same, lower end of the Wilson 95% interval | 14.1 · 14.1 · 3.7 · 0.6 · 20.6 · 20.6 · 19.1 | `results/p93_judges/table.json` | `arms.{J0,J1,J2,J3,J4,J5,J6}.tracks.input.quality.xstest.false_alarm.wilson95[0] * 100` | rounds |
| XSTest prompts: the same, upper end | 23.7 · 23.7 · 9.7 · 4.0 · 31.4 · 31.4 · 29.7 | `results/p93_judges/table.json` | `arms.{J0,J1,J2,J3,J4,J5,J6}.tracks.input.quality.xstest.false_alarm.wilson95[1] * 100` | rounds |
| XSTest prompts: harmless items flagged, count | 46 · 46 · 15 · 4 · 64 · 64 · 60 | `results/p93_judges/table.json` | `arms.{J0,J1,J2,J3,J4,J5,J6}.tracks.input.quality.xstest.false_alarm.k` | rounds |
| XSTest prompts: F1 of the harmful class, over items with a verdict | 0.828 · 0.828 · 0.909 · 0.831 · 0.857 · 0.852 · 0.839 | `results/p93_judges/table.json` | `arms.{J0,J1,J2,J3,J4,J5,J6}.tracks.input.quality.xstest.f1_unsafe_over_items_with_verdict` | rounds |
| XSTest prompts: items without a verdict, % | 0.2 · 0.2 · 0.0 · 0.0 · 0.0 · 0.2 · 0.0 | `results/p93_judges/table.json` | `arms.{J0,J1,J2,J3,J4,J5,J6}.tracks.input.quality.xstest.no_verdict.share * 100` | rounds |

**Aegis 2.0 responses (output track), arms J0 · J1 · J2 · J3 · J4 · J5 · J6**

| In the post | Number | File | Key | Check |
|---|---|---|---|---|
| Aegis 2.0 responses: harmful · harmless · items read | 394 · 419 · 813 | `results/p93_judges/table.json` | `arms.J0.tracks.output.quality.aegis2.{harmful,harmless,items}` | rounds |
| Aegis 2.0 responses: harmful items flagged, % | 78.9 · 78.7 · 61.2 · 58.9 · 86.3 · 81.0 · 88.1 | `results/p93_judges/table.json` | `arms.{J0,J1,J2,J3,J4,J5,J6}.tracks.output.quality.aegis2.detection.rate * 100` | rounds |
| Aegis 2.0 responses: the same, lower end of the Wilson 95% interval | 74.6 · 74.4 · 56.3 · 54.0 · 82.5 · 76.8 · 84.5 | `results/p93_judges/table.json` | `arms.{J0,J1,J2,J3,J4,J5,J6}.tracks.output.quality.aegis2.detection.wilson95[0] * 100` | rounds |
| Aegis 2.0 responses: the same, upper end | 82.7 · 82.4 · 65.8 · 63.6 · 89.3 · 84.5 · 90.9 | `results/p93_judges/table.json` | `arms.{J0,J1,J2,J3,J4,J5,J6}.tracks.output.quality.aegis2.detection.wilson95[1] * 100` | rounds |
| Aegis 2.0 responses: harmful items flagged, count | 311 · 310 · 241 · 232 · 340 · 319 · 347 | `results/p93_judges/table.json` | `arms.{J0,J1,J2,J3,J4,J5,J6}.tracks.output.quality.aegis2.detection.k` | rounds |
| Aegis 2.0 responses: harmless items flagged (false alarm), % | 18.4 · 18.4 · 14.1 · 10.3 · 16.7 · 13.8 · 13.8 | `results/p93_judges/table.json` | `arms.{J0,J1,J2,J3,J4,J5,J6}.tracks.output.quality.aegis2.false_alarm.rate * 100` | rounds |
| Aegis 2.0 responses: the same, lower end of the Wilson 95% interval | 15.0 · 15.0 · 11.1 · 7.7 · 13.4 · 10.9 · 10.9 | `results/p93_judges/table.json` | `arms.{J0,J1,J2,J3,J4,J5,J6}.tracks.output.quality.aegis2.false_alarm.wilson95[0] * 100` | rounds |
| Aegis 2.0 responses: the same, upper end | 22.4 · 22.4 · 17.7 · 13.5 · 20.6 · 17.5 · 17.5 | `results/p93_judges/table.json` | `arms.{J0,J1,J2,J3,J4,J5,J6}.tracks.output.quality.aegis2.false_alarm.wilson95[1] * 100` | rounds |
| Aegis 2.0 responses: harmless items flagged, count | 77 · 77 · 59 · 43 · 70 · 58 · 58 | `results/p93_judges/table.json` | `arms.{J0,J1,J2,J3,J4,J5,J6}.tracks.output.quality.aegis2.false_alarm.k` | rounds |
| Aegis 2.0 responses: F1 of the harmful class, over items with a verdict | 0.796 · 0.795 · 0.695 · 0.694 · 0.846 · 0.830 · 0.869 | `results/p93_judges/table.json` | `arms.{J0,J1,J2,J3,J4,J5,J6}.tracks.output.quality.aegis2.f1_unsafe_over_items_with_verdict` | rounds |
| Aegis 2.0 responses: items without a verdict, % | 0.1 · 0.1 · 0.0 · 0.0 · 0.0 · 0.7 · 0.0 | `results/p93_judges/table.json` | `arms.{J0,J1,J2,J3,J4,J5,J6}.tracks.output.quality.aegis2.no_verdict.share * 100` | rounds |

**Other groups of the input track, arms J0 · J1 · J2 · J3 · J4 · J5 · J6**

| In the post | Number | File | Key | Check |
|---|---|---|---|---|
| Aegis prompts whose only category is Needs Caution (148, labelled safe): flagged, % | 27.0 · 26.4 · 18.2 · 4.1 · 32.4 · 29.7 · 23.0 | `results/p93_judges/table.json` | `arms.{J0,J1,J2,J3,J4,J5,J6}.tracks.input.quality.aegis2_needs_caution_only.false_alarm.rate * 100` | rounds |
| The 45 Vol.1 questions: harmful flagged, of 15 | 14 · 14 · 15 · 15 · 15 · 15 · 14 | `results/p93_judges/table.json` | `arms.{J0,J1,J2,J3,J4,J5,J6}.tracks.input.quality.vol1.detection.k` | rounds |
| The 45 Vol.1 questions: harmless flagged, of 30 | 0 · 0 · 0 · 0 · 0 · 0 · 0 | `results/p93_judges/table.json` | `arms.{J0,J1,J2,J3,J4,J5,J6}.tracks.input.quality.vol1.false_alarm.k` | rounds |

**What a verdict costs, arms J0 · J1 · J2 · J3 · J4 · J5 · J6**

| In the post | Number | File | Key | Check |
|---|---|---|---|---|
| input track: verdicts per second at 16 concurrent requests | 26.4 · 18.5 · 9.4 · 26.4 · 87.0 · 10.8 · 45.9 | `results/p93_judges/table.json` | `arms.{J0,J1,J2,J3,J4,J5,J6}.tracks.input.quality_cell.verdicts_per_s` | rounds |
| input track: p99 of a call's duration at 16 concurrent requests, ms | 2,262 · 2,459 · 6,389 · 2,034 · 395 · 4,621 · 733 | `results/p93_judges/table.json` | `arms.{J0,J1,J2,J3,J4,J5,J6}.tracks.input.quality_cell.latency_ms.p99` | rounds |
| input track: median duration of a call, one request at a time, ms | 51 · 568 · 383 · 42 · 89 · 762 · 204 | `results/p93_judges/table.json` | `arms.{J0,J1,J2,J3,J4,J5,J6}.tracks.input.c1.latency_ms.p50` | rounds |
| input track: output tokens per call, median | 3 · 57 · 112 · 2 · 11 · 137 · 18 | `results/p93_judges/table.json` | `arms.{J0,J1,J2,J3,J4,J5,J6}.tracks.input.quality_cell.completion_tokens.p50` | rounds |
| input track: calls with reasoning in the 16-concurrent cell | 0 · 0 · 2,419 · 0 · 0 · 2,423 · 0 | `results/p93_judges/table.json` | `arms.{J0,J1,J2,J3,J4,J5,J6}.tracks.input.quality_cell.calls_with_reasoning` | rounds |
| input track: calls in that cell | 2,423 · 2,423 · 2,423 · 2,423 · 2,423 · 2,423 · 2,423 | `results/p93_judges/table.json` | `arms.{J0,J1,J2,J3,J4,J5,J6}.tracks.input.quality_cell.calls` | rounds |
| input track: same outcome on the rerun, % | 99.5 · 99.5 · 96.0 · 95.5 · 100.0 · 96.5 · 99.5 | `results/p93_judges/table.json` | `arms.{J0,J1,J2,J3,J4,J5,J6}.tracks.input.stability.rate * 100` | rounds |
| output track: verdicts per second at 16 concurrent requests | 34.7 · 12.3 · 8.1 · 26.0 · 56.6 · 7.1 · 30.1 | `results/p93_judges/table.json` | `arms.{J0,J1,J2,J3,J4,J5,J6}.tracks.output.quality_cell.verdicts_per_s` | rounds |
| output track: p99 of a call's duration at 16 concurrent requests, ms | 1,838 · 2,955 · 6,079 · 2,012 · 492 · 6,059 · 829 | `results/p93_judges/table.json` | `arms.{J0,J1,J2,J3,J4,J5,J6}.tracks.output.quality_cell.latency_ms.p99` | rounds |
| output track: median duration of a call, one request at a time, ms | 50 · 917 · 523 · 39 · 154 · 1,474 · 295 | `results/p93_judges/table.json` | `arms.{J0,J1,J2,J3,J4,J5,J6}.tracks.output.c1.latency_ms.p50` | rounds |
| output track: output tokens per call, median | 3 · 88 · 154 · 2 · 18 · 209 · 27 | `results/p93_judges/table.json` | `arms.{J0,J1,J2,J3,J4,J5,J6}.tracks.output.quality_cell.completion_tokens.p50` | rounds |
| output track: calls with reasoning in the 16-concurrent cell | 0 · 0 · 813 · 0 · 0 · 813 · 0 | `results/p93_judges/table.json` | `arms.{J0,J1,J2,J3,J4,J5,J6}.tracks.output.quality_cell.calls_with_reasoning` | rounds |
| output track: calls in that cell | 813 · 813 · 813 · 813 · 813 · 813 · 813 | `results/p93_judges/table.json` | `arms.{J0,J1,J2,J3,J4,J5,J6}.tracks.output.quality_cell.calls` | rounds |
| output track: same outcome on the rerun, % | 100.0 · 100.0 · 91.0 · 98.0 · 100.0 · 95.0 · 99.0 | `results/p93_judges/table.json` | `arms.{J0,J1,J2,J3,J4,J5,J6}.tracks.output.stability.rate * 100` | rounds |

**Nemotron 3 Nano with reasoning on, through the self-check rail (arm J2): what the rail decided**

| In the post | Number | File | Key | Check |
|---|---|---|---|---|
| Input track: items the rail blocked, all groups together | 2,423 | `results/p93_judges/table.json` | `arms.J2.tracks.input.quality.aegis2.rail.block_on_harmful.k + arms.J2.tracks.input.quality.aegis2.rail.block_on_harmless.k + arms.J2.tracks.input.quality.xstest.rail.block_on_harmful.k + arms.J2.tracks.input.quality.xstest.rail.block_on_harmless.k + arms.J2.tracks.input.quality.vol1.rail.block_on_harmful.k + arms.J2.tracks.input.quality.vol1.rail.block_on_harmless.k` | rounds |
| Input track: calls made | 2,423 | `results/p93_judges/table.json` | `arms.J2.tracks.input.quality_cell.calls` | rounds |
| Output track: items the rail blocked | 813 | `results/p93_judges/table.json` | `arms.J2.tracks.output.quality.aegis2.rail.block_on_harmful.k + arms.J2.tracks.output.quality.aegis2.rail.block_on_harmless.k` | rounds |
| Output track: calls made | 813 | `results/p93_judges/table.json` | `arms.J2.tracks.output.quality_cell.calls` | rounds |

**The same arm with a reasoning parser on the server (follow-up, 100 stored requests)**

| In the post | Number | File | Key | Check |
|---|---|---|---|---|
| Without the parser: requests · blocked by the rail | 100 · 100 | `results/p102_followup/passthrough/summary.json` | `settings.off.{n,rail_blocked}` | rounds |
| Without the parser: the model's own answer read after the closing tag, unsafe · safe | 42 · 58 | `results/p102_followup/passthrough/summary.json` | `settings.off.verdict_read_from_the_answer.{unsafe,safe}` | rounds |
| With the parser: blocked · allowed by the rail | 45 · 55 | `results/p102_followup/passthrough/summary.json` | `settings.on.rail.{block,allow}` | rounds |
| With the parser: the model's own answer, unsafe · safe | 45 · 55 | `results/p102_followup/passthrough/summary.json` | `settings.on.verdict_read_from_the_answer.{unsafe,safe}` | rounds |

**Llama Guard 3 8B, the reference arm (upstream vLLM, not a NIM)**

| In the post | Number | File | Key | Check |
|---|---|---|---|---|
| Aegis 2.0 prompts: harmful items flagged, % · lower · upper end of the interval | 66.4 · 63.5 · 69.2 | `results/p102_followup/LG3/summary.json` | `tracks.input.quality.aegis2.detection.{rate,wilson95[0],wilson95[1]} * 100` | rounds |
| Aegis 2.0 prompts: harmful items flagged, count · of | 690 · 1,039 | `results/p102_followup/LG3/summary.json` | `tracks.input.quality.aegis2.detection.{k,n}` | rounds |
| Aegis 2.0 prompts: harmless items flagged, % · lower · upper end of the interval | 6.7 · 5.3 · 8.6 | `results/p102_followup/LG3/summary.json` | `tracks.input.quality.aegis2.false_alarm.{rate,wilson95[0],wilson95[1]} * 100` | rounds |
| XSTest prompts: harmful items flagged, % · lower · upper end of the interval | 82.0 · 76.1 · 86.7 | `results/p102_followup/LG3/summary.json` | `tracks.input.quality.xstest.detection.{rate,wilson95[0],wilson95[1]} * 100` | rounds |
| XSTest prompts: harmful items flagged, count · of | 164 · 200 | `results/p102_followup/LG3/summary.json` | `tracks.input.quality.xstest.detection.{k,n}` | rounds |
| XSTest prompts: harmless items flagged, % · lower · upper end of the interval | 2.8 · 1.4 · 5.7 | `results/p102_followup/LG3/summary.json` | `tracks.input.quality.xstest.false_alarm.{rate,wilson95[0],wilson95[1]} * 100` | rounds |
| Aegis 2.0 responses: harmful items flagged, % · lower · upper end of the interval | 51.3 · 46.3 · 56.2 | `results/p102_followup/LG3/summary.json` | `tracks.output.quality.aegis2.detection.{rate,wilson95[0],wilson95[1]} * 100` | rounds |
| Aegis 2.0 responses: harmful items flagged, count · of | 202 · 394 | `results/p102_followup/LG3/summary.json` | `tracks.output.quality.aegis2.detection.{k,n}` | rounds |
| Aegis 2.0 responses: harmless items flagged, % · lower · upper end of the interval | 4.1 · 2.5 · 6.4 | `results/p102_followup/LG3/summary.json` | `tracks.output.quality.aegis2.false_alarm.{rate,wilson95[0],wilson95[1]} * 100` | rounds |
| Verdicts per second at 16 concurrent requests: input · output track | 98.1 · 64.8 | `results/p102_followup/LG3/summary.json` | `tracks.{input,output}.quality_cell.verdicts_per_s` | rounds |
| Median duration of a call, one request at a time, ms: input · output track (first run; see the repeats below) | 51.4 · 52.3 | `results/p102_followup/LG3/summary.json` | `tracks.{input,output}.c1.latency_ms.p50` | rounds |

**Llama Guard 3 8B: the timed cells, first run and two repeats on a quiet host**

| In the post | Number | File | Key | Check |
|---|---|---|---|---|
| input track: verdicts per second at 16 concurrent requests, first run · repeat 1 · repeat 2 | 98.1 · 95.3 · 94.6 | `results/lg3_timing_repeats/comparison.json` | `tracks.input.c16_verdicts_per_s.{first,quiet[0],quiet[1]}` | rounds |
| input track: median duration of a call, one request at a time, ms, first run · repeat 1 · repeat 2 | 51.4 · 60.1 · 65.9 | `results/lg3_timing_repeats/comparison.json` | `tracks.input.c1_p50_ms.{first,quiet[0],quiet[1]}` | rounds |
| output track: verdicts per second at 16 concurrent requests, first run · repeat 1 · repeat 2 | 64.8 · 64.1 · 63.4 | `results/lg3_timing_repeats/comparison.json` | `tracks.output.c16_verdicts_per_s.{first,quiet[0],quiet[1]}` | rounds |
| output track: median duration of a call, one request at a time, ms, first run · repeat 1 · repeat 2 | 52.3 · 63.6 · 63.5 | `results/lg3_timing_repeats/comparison.json` | `tracks.output.c1_p50_ms.{first,quiet[0],quiet[1]}` | rounds |

**Counts and settings an article states**

| In the post | Number | File | Key | Check |
|---|---|---|---|---|
| Aegis prompts whose only category is Needs Caution, labelled safe: count | 148 | `results/p93_judges/items_summary.json` | `aegis2_needs_caution_only_by_gold.safe` | rounds |
| Context length every server was started with, tokens | 8,192 | `results/p93_judges/prediction_p93.json` | `serving.context_tokens` | rounds |
| Answer limit set for the reasoning arms, which is also the library's default since 0.23.0, tokens | 1,024 | `results/p93_judges/prediction_p93.json` | `arms.J2.max_tokens` | rounds |

**Safety Guard 8B v3 served by its NIM, 2026-10-06 (arms J6N · J6-today · J6N-tpl · J6G)**

| In the post | Number | File | Key | Check |
|---|---|---|---|---|
| J6N · Aegis 2.0 prompts: harmful items flagged, % · lower · upper end of the interval | 87.8 · 85.6 · 89.6 | `results/safety_guard_nim/J6N/summary.json` | `tracks.input.quality.aegis2.detection.{rate,wilson95[0],wilson95[1]} * 100` | rounds |
| J6N · Aegis 2.0 prompts: harmful items flagged, count · of | 912 · 1,039 | `results/safety_guard_nim/J6N/summary.json` | `tracks.input.quality.aegis2.detection.{k,n}` | rounds |
| J6N · Aegis 2.0 prompts: harmless items flagged, % · lower · upper end of the interval | 15.6 · 13.4 · 18.2 | `results/safety_guard_nim/J6N/summary.json` | `tracks.input.quality.aegis2.false_alarm.{rate,wilson95[0],wilson95[1]} * 100` | rounds |
| J6N · Aegis 2.0 prompts: harmless items flagged, count · of | 139 · 889 | `results/safety_guard_nim/J6N/summary.json` | `tracks.input.quality.aegis2.false_alarm.{k,n}` | rounds |
| J6N · XSTest prompts: harmful items flagged, % · lower · upper end of the interval | 94.5 · 90.4 · 96.9 | `results/safety_guard_nim/J6N/summary.json` | `tracks.input.quality.xstest.detection.{rate,wilson95[0],wilson95[1]} * 100` | rounds |
| J6N · XSTest prompts: harmful items flagged, count · of | 189 · 200 | `results/safety_guard_nim/J6N/summary.json` | `tracks.input.quality.xstest.detection.{k,n}` | rounds |
| J6N · XSTest prompts: harmless items flagged, % · lower · upper end of the interval | 24.4 · 19.5 · 30.1 | `results/safety_guard_nim/J6N/summary.json` | `tracks.input.quality.xstest.false_alarm.{rate,wilson95[0],wilson95[1]} * 100` | rounds |
| J6N · XSTest prompts: harmless items flagged, count · of | 61 · 250 | `results/safety_guard_nim/J6N/summary.json` | `tracks.input.quality.xstest.false_alarm.{k,n}` | rounds |
| J6N · Aegis 2.0 responses: harmful items flagged, % · lower · upper end of the interval | 87.6 · 83.9 · 90.5 | `results/safety_guard_nim/J6N/summary.json` | `tracks.output.quality.aegis2.detection.{rate,wilson95[0],wilson95[1]} * 100` | rounds |
| J6N · Aegis 2.0 responses: harmful items flagged, count · of | 345 · 394 | `results/safety_guard_nim/J6N/summary.json` | `tracks.output.quality.aegis2.detection.{k,n}` | rounds |
| J6N · Aegis 2.0 responses: harmless items flagged, % · lower · upper end of the interval | 14.1 · 11.1 · 17.7 | `results/safety_guard_nim/J6N/summary.json` | `tracks.output.quality.aegis2.false_alarm.{rate,wilson95[0],wilson95[1]} * 100` | rounds |
| J6N · Aegis 2.0 responses: harmless items flagged, count · of | 59 · 419 | `results/safety_guard_nim/J6N/summary.json` | `tracks.output.quality.aegis2.false_alarm.{k,n}` | rounds |
| J6N · prompts: verdicts per second at 16 concurrent requests | 38.5 | `results/safety_guard_nim/J6N/summary.json` | `tracks.input.quality_cell.verdicts_per_s` | rounds |
| J6N · prompts: p99 duration of a call at 16 concurrent requests, ms | 872.1 | `results/safety_guard_nim/J6N/summary.json` | `tracks.input.quality_cell.latency_ms.p99` | rounds |
| J6N · prompts: median duration of a call, one request at a time, ms | 234.9 | `results/safety_guard_nim/J6N/summary.json` | `tracks.input.c1.latency_ms.p50` | rounds |
| J6N · prompts: output tokens per call, median | 18 | `results/safety_guard_nim/J6N/summary.json` | `tracks.input.quality_cell.completion_tokens.p50` | rounds |
| J6N · prompts: items with the same outcome in a second reading, count · of | 200 · 200 | `results/safety_guard_nim/J6N/summary.json` | `tracks.input.stability.{k,n}` | rounds |
| J6N · responses: verdicts per second at 16 concurrent requests | 24.5 | `results/safety_guard_nim/J6N/summary.json` | `tracks.output.quality_cell.verdicts_per_s` | rounds |
| J6N · responses: p99 duration of a call at 16 concurrent requests, ms | 1045.2 | `results/safety_guard_nim/J6N/summary.json` | `tracks.output.quality_cell.latency_ms.p99` | rounds |
| J6N · responses: median duration of a call, one request at a time, ms | 337.5 | `results/safety_guard_nim/J6N/summary.json` | `tracks.output.c1.latency_ms.p50` | rounds |
| J6N · responses: output tokens per call, median | 27 | `results/safety_guard_nim/J6N/summary.json` | `tracks.output.quality_cell.completion_tokens.p50` | rounds |
| J6N · responses: items with the same outcome in a second reading, count · of | 99 · 100 | `results/safety_guard_nim/J6N/summary.json` | `tracks.output.stability.{k,n}` | rounds |
| J6-today · Aegis 2.0 prompts: harmful items flagged, % · lower · upper end of the interval | 87.7 · 85.5 · 89.5 | `results/safety_guard_nim/J6-today/summary.json` | `tracks.input.quality.aegis2.detection.{rate,wilson95[0],wilson95[1]} * 100` | rounds |
| J6-today · Aegis 2.0 prompts: harmful items flagged, count · of | 911 · 1,039 | `results/safety_guard_nim/J6-today/summary.json` | `tracks.input.quality.aegis2.detection.{k,n}` | rounds |
| J6-today · Aegis 2.0 prompts: harmless items flagged, % · lower · upper end of the interval | 15.3 · 13.1 · 17.8 | `results/safety_guard_nim/J6-today/summary.json` | `tracks.input.quality.aegis2.false_alarm.{rate,wilson95[0],wilson95[1]} * 100` | rounds |
| J6-today · Aegis 2.0 prompts: harmless items flagged, count · of | 136 · 889 | `results/safety_guard_nim/J6-today/summary.json` | `tracks.input.quality.aegis2.false_alarm.{k,n}` | rounds |
| J6-today · XSTest prompts: harmful items flagged, % · lower · upper end of the interval | 94.5 · 90.4 · 96.9 | `results/safety_guard_nim/J6-today/summary.json` | `tracks.input.quality.xstest.detection.{rate,wilson95[0],wilson95[1]} * 100` | rounds |
| J6-today · XSTest prompts: harmful items flagged, count · of | 189 · 200 | `results/safety_guard_nim/J6-today/summary.json` | `tracks.input.quality.xstest.detection.{k,n}` | rounds |
| J6-today · XSTest prompts: harmless items flagged, % · lower · upper end of the interval | 24.0 · 19.1 · 29.7 | `results/safety_guard_nim/J6-today/summary.json` | `tracks.input.quality.xstest.false_alarm.{rate,wilson95[0],wilson95[1]} * 100` | rounds |
| J6-today · XSTest prompts: harmless items flagged, count · of | 60 · 250 | `results/safety_guard_nim/J6-today/summary.json` | `tracks.input.quality.xstest.false_alarm.{k,n}` | rounds |
| J6-today · Aegis 2.0 responses: harmful items flagged, % · lower · upper end of the interval | 87.3 · 83.7 · 90.2 | `results/safety_guard_nim/J6-today/summary.json` | `tracks.output.quality.aegis2.detection.{rate,wilson95[0],wilson95[1]} * 100` | rounds |
| J6-today · Aegis 2.0 responses: harmful items flagged, count · of | 344 · 394 | `results/safety_guard_nim/J6-today/summary.json` | `tracks.output.quality.aegis2.detection.{k,n}` | rounds |
| J6-today · Aegis 2.0 responses: harmless items flagged, % · lower · upper end of the interval | 14.1 · 11.1 · 17.7 | `results/safety_guard_nim/J6-today/summary.json` | `tracks.output.quality.aegis2.false_alarm.{rate,wilson95[0],wilson95[1]} * 100` | rounds |
| J6-today · Aegis 2.0 responses: harmless items flagged, count · of | 59 · 419 | `results/safety_guard_nim/J6-today/summary.json` | `tracks.output.quality.aegis2.false_alarm.{k,n}` | rounds |
| J6-today · prompts: verdicts per second at 16 concurrent requests | 47.5 | `results/safety_guard_nim/J6-today/summary.json` | `tracks.input.quality_cell.verdicts_per_s` | rounds |
| J6-today · prompts: p99 duration of a call at 16 concurrent requests, ms | 719.6 | `results/safety_guard_nim/J6-today/summary.json` | `tracks.input.quality_cell.latency_ms.p99` | rounds |
| J6-today · prompts: median duration of a call, one request at a time, ms | 194.2 | `results/safety_guard_nim/J6-today/summary.json` | `tracks.input.c1.latency_ms.p50` | rounds |
| J6-today · prompts: output tokens per call, median | 18 | `results/safety_guard_nim/J6-today/summary.json` | `tracks.input.quality_cell.completion_tokens.p50` | rounds |
| J6-today · responses: verdicts per second at 16 concurrent requests | 30.5 | `results/safety_guard_nim/J6-today/summary.json` | `tracks.output.quality_cell.verdicts_per_s` | rounds |
| J6-today · responses: p99 duration of a call at 16 concurrent requests, ms | 809.7 | `results/safety_guard_nim/J6-today/summary.json` | `tracks.output.quality_cell.latency_ms.p99` | rounds |
| J6-today · responses: median duration of a call, one request at a time, ms | 282.9 | `results/safety_guard_nim/J6-today/summary.json` | `tracks.output.c1.latency_ms.p50` | rounds |
| J6-today · responses: output tokens per call, median | 27 | `results/safety_guard_nim/J6-today/summary.json` | `tracks.output.quality_cell.completion_tokens.p50` | rounds |
| J6N-tpl · Aegis 2.0 prompts: harmful items flagged, % · lower · upper end of the interval | 87.3 · 85.1 · 89.2 | `results/safety_guard_nim/J6N-tpl/summary.json` | `tracks.input.quality.aegis2.detection.{rate,wilson95[0],wilson95[1]} * 100` | rounds |
| J6N-tpl · Aegis 2.0 prompts: harmful items flagged, count · of | 907 · 1,039 | `results/safety_guard_nim/J6N-tpl/summary.json` | `tracks.input.quality.aegis2.detection.{k,n}` | rounds |
| J6N-tpl · Aegis 2.0 prompts: harmless items flagged, % · lower · upper end of the interval | 14.7 · 12.6 · 17.2 | `results/safety_guard_nim/J6N-tpl/summary.json` | `tracks.input.quality.aegis2.false_alarm.{rate,wilson95[0],wilson95[1]} * 100` | rounds |
| J6N-tpl · Aegis 2.0 prompts: harmless items flagged, count · of | 131 · 889 | `results/safety_guard_nim/J6N-tpl/summary.json` | `tracks.input.quality.aegis2.false_alarm.{k,n}` | rounds |
| J6N-tpl · XSTest prompts: harmful items flagged, % · lower · upper end of the interval | 93.0 · 88.6 · 95.8 | `results/safety_guard_nim/J6N-tpl/summary.json` | `tracks.input.quality.xstest.detection.{rate,wilson95[0],wilson95[1]} * 100` | rounds |
| J6N-tpl · XSTest prompts: harmful items flagged, count · of | 186 · 200 | `results/safety_guard_nim/J6N-tpl/summary.json` | `tracks.input.quality.xstest.detection.{k,n}` | rounds |
| J6N-tpl · XSTest prompts: harmless items flagged, % · lower · upper end of the interval | 22.4 · 17.7 · 28.0 | `results/safety_guard_nim/J6N-tpl/summary.json` | `tracks.input.quality.xstest.false_alarm.{rate,wilson95[0],wilson95[1]} * 100` | rounds |
| J6N-tpl · XSTest prompts: harmless items flagged, count · of | 56 · 250 | `results/safety_guard_nim/J6N-tpl/summary.json` | `tracks.input.quality.xstest.false_alarm.{k,n}` | rounds |
| J6N-tpl · Aegis 2.0 responses: harmful items flagged, % · lower · upper end of the interval | 85.0 · 81.2 · 88.2 | `results/safety_guard_nim/J6N-tpl/summary.json` | `tracks.output.quality.aegis2.detection.{rate,wilson95[0],wilson95[1]} * 100` | rounds |
| J6N-tpl · Aegis 2.0 responses: harmful items flagged, count · of | 335 · 394 | `results/safety_guard_nim/J6N-tpl/summary.json` | `tracks.output.quality.aegis2.detection.{k,n}` | rounds |
| J6N-tpl · Aegis 2.0 responses: harmless items flagged, % · lower · upper end of the interval | 12.4 · 9.6 · 15.9 | `results/safety_guard_nim/J6N-tpl/summary.json` | `tracks.output.quality.aegis2.false_alarm.{rate,wilson95[0],wilson95[1]} * 100` | rounds |
| J6N-tpl · Aegis 2.0 responses: harmless items flagged, count · of | 52 · 419 | `results/safety_guard_nim/J6N-tpl/summary.json` | `tracks.output.quality.aegis2.false_alarm.{k,n}` | rounds |
| J6N-tpl · prompts: verdicts per second at 16 concurrent requests | 39.2 | `results/safety_guard_nim/J6N-tpl/summary.json` | `tracks.input.quality_cell.verdicts_per_s` | rounds |
| J6N-tpl · prompts: p99 duration of a call at 16 concurrent requests, ms | 881.1 | `results/safety_guard_nim/J6N-tpl/summary.json` | `tracks.input.quality_cell.latency_ms.p99` | rounds |
| J6N-tpl · prompts: median duration of a call, one request at a time, ms | 236.5 | `results/safety_guard_nim/J6N-tpl/summary.json` | `tracks.input.c1.latency_ms.p50` | rounds |
| J6N-tpl · prompts: output tokens per call, median | 18 | `results/safety_guard_nim/J6N-tpl/summary.json` | `tracks.input.quality_cell.completion_tokens.p50` | rounds |
| J6N-tpl · responses: verdicts per second at 16 concurrent requests | 25.5 | `results/safety_guard_nim/J6N-tpl/summary.json` | `tracks.output.quality_cell.verdicts_per_s` | rounds |
| J6N-tpl · responses: p99 duration of a call at 16 concurrent requests, ms | 1010.6 | `results/safety_guard_nim/J6N-tpl/summary.json` | `tracks.output.quality_cell.latency_ms.p99` | rounds |
| J6N-tpl · responses: median duration of a call, one request at a time, ms | 321.7 | `results/safety_guard_nim/J6N-tpl/summary.json` | `tracks.output.c1.latency_ms.p50` | rounds |
| J6N-tpl · responses: output tokens per call, median | 26 | `results/safety_guard_nim/J6N-tpl/summary.json` | `tracks.output.quality_cell.completion_tokens.p50` | rounds |
| J6G · prompts, 100 items: the rail blocks harmful items, count · of | 46 · 52 | `results/safety_guard_nim/J6G/summary.json` | `tracks.input.quality.all_items_of_the_subset.rail.block_on_harmful.{k,n}` | rounds |
| J6G · prompts, 100 items: the rail blocks harmless items, count · of | 5 · 48 | `results/safety_guard_nim/J6G/summary.json` | `tracks.input.quality.all_items_of_the_subset.rail.block_on_harmless.{k,n}` | rounds |
| J6G · prompts: rail decision and verdict of the same call agree, count · of | 100 · 100 | `results/safety_guard_nim/J6G/summary.json` | `tracks.input.rail_beside_verdict_of_the_same_call.agree.{k,n}` | rounds |
| J6G · prompts: median duration of a call through the rail, ms | 206.8 | `results/safety_guard_nim/J6G/summary.json` | `tracks.input.calls.latency_ms.p50` | rounds |
| J6G · prompts: output tokens per call, median · maximum | 17 · 33 | `results/safety_guard_nim/J6G/summary.json` | `tracks.input.calls.completion_tokens.{p50,max}` | rounds |
| J6G · responses, 100 items: the rail blocks harmful items, count · of | 42 · 48 | `results/safety_guard_nim/J6G/summary.json` | `tracks.output.quality.all_items_of_the_subset.rail.block_on_harmful.{k,n}` | rounds |
| J6G · responses, 100 items: the rail blocks harmless items, count · of | 8 · 52 | `results/safety_guard_nim/J6G/summary.json` | `tracks.output.quality.all_items_of_the_subset.rail.block_on_harmless.{k,n}` | rounds |
| J6G · responses: rail decision and verdict of the same call agree, count · of | 100 · 100 | `results/safety_guard_nim/J6G/summary.json` | `tracks.output.rail_beside_verdict_of_the_same_call.agree.{k,n}` | rounds |
| J6G · responses: median duration of a call through the rail, ms | 316.2 | `results/safety_guard_nim/J6G/summary.json` | `tracks.output.calls.latency_ms.p50` | rounds |
| J6G · responses: output tokens per call, median · maximum | 26 · 42 | `results/safety_guard_nim/J6G/summary.json` | `tracks.output.calls.completion_tokens.{p50,max}` | rounds |

<!-- end of the Safety Guard NIM rows -->

**The reasoning parser on whole tracks and the engine version, 2026-10-06 (arms J2P · J2P-repeat · J2-today · J6-v010), and figures an article sets side by side**

Rows that set two arms side by side do so for one model and one request shape on two servers or two days, or for one arm on its two tracks; they are rates, not verdicts. Nothing here combines the per-item verdicts of two arms.

| In the post | Number | File | Key | Check |
|---|---|---|---|---|
| J2P · Aegis 2.0 prompts: harmful items flagged, % · lower · upper end of the interval | 66.0 · 63.1 · 68.8 | `results/parser_and_engine_version/J2P/summary.json` | `tracks.input.quality.aegis2.detection.{rate,wilson95[0],wilson95[1]} * 100` | rounds |
| J2P · Aegis 2.0 prompts: harmful items flagged, count · of | 686 · 1,039 | `results/parser_and_engine_version/J2P/summary.json` | `tracks.input.quality.aegis2.detection.{k,n}` | rounds |
| J2P · Aegis 2.0 prompts: harmless items flagged, % · lower · upper end of the interval | 10.1 · 8.3 · 12.3 | `results/parser_and_engine_version/J2P/summary.json` | `tracks.input.quality.aegis2.false_alarm.{rate,wilson95[0],wilson95[1]} * 100` | rounds |
| J2P · Aegis 2.0 prompts: harmless items flagged, count · of | 90 · 889 | `results/parser_and_engine_version/J2P/summary.json` | `tracks.input.quality.aegis2.false_alarm.{k,n}` | rounds |
| J2P · Aegis 2.0 prompts: items the rail blocked, harmful · harmless | 687 · 91 | `results/parser_and_engine_version/J2P/summary.json` | `tracks.input.quality.aegis2.rail.{block_on_harmful.k,block_on_harmless.k}` | rounds |
| J2P · XSTest prompts: harmful items flagged, % · lower · upper end of the interval | 88.5 · 83.3 · 92.2 | `results/parser_and_engine_version/J2P/summary.json` | `tracks.input.quality.xstest.detection.{rate,wilson95[0],wilson95[1]} * 100` | rounds |
| J2P · XSTest prompts: harmful items flagged, count · of | 177 · 200 | `results/parser_and_engine_version/J2P/summary.json` | `tracks.input.quality.xstest.detection.{k,n}` | rounds |
| J2P · XSTest prompts: harmless items flagged, % · lower · upper end of the interval | 6.8 · 4.3 · 10.6 | `results/parser_and_engine_version/J2P/summary.json` | `tracks.input.quality.xstest.false_alarm.{rate,wilson95[0],wilson95[1]} * 100` | rounds |
| J2P · XSTest prompts: harmless items flagged, count · of | 17 · 250 | `results/parser_and_engine_version/J2P/summary.json` | `tracks.input.quality.xstest.false_alarm.{k,n}` | rounds |
| J2P · XSTest prompts: items the rail blocked, harmful · harmless | 177 · 17 | `results/parser_and_engine_version/J2P/summary.json` | `tracks.input.quality.xstest.rail.{block_on_harmful.k,block_on_harmless.k}` | rounds |
| J2P · Aegis 2.0 responses: harmful items flagged, % · lower · upper end of the interval | 60.4 · 55.5 · 65.1 | `results/parser_and_engine_version/J2P/summary.json` | `tracks.output.quality.aegis2.detection.{rate,wilson95[0],wilson95[1]} * 100` | rounds |
| J2P · Aegis 2.0 responses: harmful items flagged, count · of | 238 · 394 | `results/parser_and_engine_version/J2P/summary.json` | `tracks.output.quality.aegis2.detection.{k,n}` | rounds |
| J2P · Aegis 2.0 responses: harmless items flagged, % · lower · upper end of the interval | 15.3 · 12.1 · 19.0 | `results/parser_and_engine_version/J2P/summary.json` | `tracks.output.quality.aegis2.false_alarm.{rate,wilson95[0],wilson95[1]} * 100` | rounds |
| J2P · Aegis 2.0 responses: harmless items flagged, count · of | 64 · 419 | `results/parser_and_engine_version/J2P/summary.json` | `tracks.output.quality.aegis2.false_alarm.{k,n}` | rounds |
| J2P · Aegis 2.0 responses: items the rail blocked, harmful · harmless | 238 · 64 | `results/parser_and_engine_version/J2P/summary.json` | `tracks.output.quality.aegis2.rail.{block_on_harmful.k,block_on_harmless.k}` | rounds |
| J2P · prompts: verdicts per second at 16 concurrent requests | 4.8 | `results/parser_and_engine_version/J2P/summary.json` | `tracks.input.quality_cell.verdicts_per_s` | rounds |
| J2P · prompts: calls in that cell | 2,423 | `results/parser_and_engine_version/J2P/summary.json` | `tracks.input.quality_cell.calls` | rounds |
| J2P · prompts: p99 duration of a call at 16 concurrent requests, ms | 15,181.6 | `results/parser_and_engine_version/J2P/summary.json` | `tracks.input.quality_cell.latency_ms.p99` | rounds |
| J2P · prompts: output tokens per call, median | 112 | `results/parser_and_engine_version/J2P/summary.json` | `tracks.input.quality_cell.completion_tokens.p50` | rounds |
| J2P · prompts: median duration of a call, one request at a time, ms | 378.2 | `results/parser_and_engine_version/J2P/summary.json` | `tracks.input.c1.latency_ms.p50` | rounds |
| J2P · prompts: items with the same outcome in a second reading, count · of | 190 · 200 | `results/parser_and_engine_version/J2P/summary.json` | `tracks.input.stability.{k,n}` | rounds |
| J2P · responses: verdicts per second at 16 concurrent requests | 4.4 | `results/parser_and_engine_version/J2P/summary.json` | `tracks.output.quality_cell.verdicts_per_s` | rounds |
| J2P · responses: calls in that cell | 813 | `results/parser_and_engine_version/J2P/summary.json` | `tracks.output.quality_cell.calls` | rounds |
| J2P · responses: p99 duration of a call at 16 concurrent requests, ms | 13,503.5 | `results/parser_and_engine_version/J2P/summary.json` | `tracks.output.quality_cell.latency_ms.p99` | rounds |
| J2P · responses: output tokens per call, median | 152 | `results/parser_and_engine_version/J2P/summary.json` | `tracks.output.quality_cell.completion_tokens.p50` | rounds |
| J2P · responses: median duration of a call, one request at a time, ms | 580.4 | `results/parser_and_engine_version/J2P/summary.json` | `tracks.output.c1.latency_ms.p50` | rounds |
| J2P · responses: items with the same outcome in a second reading, count · of | 87 · 100 | `results/parser_and_engine_version/J2P/summary.json` | `tracks.output.stability.{k,n}` | rounds |
| J2P-repeat · Aegis 2.0 prompts: harmful items flagged, % · lower · upper end of the interval | 66.5 · 63.6 · 69.3 | `results/parser_and_engine_version/J2P-repeat/summary.json` | `tracks.input.quality.aegis2.detection.{rate,wilson95[0],wilson95[1]} * 100` | rounds |
| J2P-repeat · Aegis 2.0 prompts: harmful items flagged, count · of | 691 · 1,039 | `results/parser_and_engine_version/J2P-repeat/summary.json` | `tracks.input.quality.aegis2.detection.{k,n}` | rounds |
| J2P-repeat · Aegis 2.0 prompts: harmless items flagged, % · lower · upper end of the interval | 10.0 · 8.2 · 12.2 | `results/parser_and_engine_version/J2P-repeat/summary.json` | `tracks.input.quality.aegis2.false_alarm.{rate,wilson95[0],wilson95[1]} * 100` | rounds |
| J2P-repeat · Aegis 2.0 prompts: harmless items flagged, count · of | 89 · 889 | `results/parser_and_engine_version/J2P-repeat/summary.json` | `tracks.input.quality.aegis2.false_alarm.{k,n}` | rounds |
| J2P-repeat · Aegis 2.0 prompts: items the rail blocked, harmful · harmless | 692 · 89 | `results/parser_and_engine_version/J2P-repeat/summary.json` | `tracks.input.quality.aegis2.rail.{block_on_harmful.k,block_on_harmless.k}` | rounds |
| J2P-repeat · Aegis 2.0 responses: harmful items flagged, % · lower · upper end of the interval | 62.7 · 57.8 · 67.3 | `results/parser_and_engine_version/J2P-repeat/summary.json` | `tracks.output.quality.aegis2.detection.{rate,wilson95[0],wilson95[1]} * 100` | rounds |
| J2P-repeat · Aegis 2.0 responses: harmful items flagged, count · of | 247 · 394 | `results/parser_and_engine_version/J2P-repeat/summary.json` | `tracks.output.quality.aegis2.detection.{k,n}` | rounds |
| J2P-repeat · Aegis 2.0 responses: harmless items flagged, % · lower · upper end of the interval | 15.3 · 12.1 · 19.0 | `results/parser_and_engine_version/J2P-repeat/summary.json` | `tracks.output.quality.aegis2.false_alarm.{rate,wilson95[0],wilson95[1]} * 100` | rounds |
| J2P-repeat · Aegis 2.0 responses: harmless items flagged, count · of | 64 · 419 | `results/parser_and_engine_version/J2P-repeat/summary.json` | `tracks.output.quality.aegis2.false_alarm.{k,n}` | rounds |
| J2P-repeat · Aegis 2.0 responses: items the rail blocked, harmful · harmless | 248 · 64 | `results/parser_and_engine_version/J2P-repeat/summary.json` | `tracks.output.quality.aegis2.rail.{block_on_harmful.k,block_on_harmless.k}` | rounds |
| J2P-repeat · prompts: verdicts per second at 16 concurrent requests | 9.1 | `results/parser_and_engine_version/J2P-repeat/summary.json` | `tracks.input.quality_cell.verdicts_per_s` | rounds |
| J2P-repeat · prompts: calls in that cell | 2,423 | `results/parser_and_engine_version/J2P-repeat/summary.json` | `tracks.input.quality_cell.calls` | rounds |
| J2P-repeat · prompts: p99 duration of a call at 16 concurrent requests, ms | 7,129.5 | `results/parser_and_engine_version/J2P-repeat/summary.json` | `tracks.input.quality_cell.latency_ms.p99` | rounds |
| J2P-repeat · prompts: output tokens per call, median | 112 | `results/parser_and_engine_version/J2P-repeat/summary.json` | `tracks.input.quality_cell.completion_tokens.p50` | rounds |
| J2P-repeat · responses: verdicts per second at 16 concurrent requests | 7.9 | `results/parser_and_engine_version/J2P-repeat/summary.json` | `tracks.output.quality_cell.verdicts_per_s` | rounds |
| J2P-repeat · responses: calls in that cell | 813 | `results/parser_and_engine_version/J2P-repeat/summary.json` | `tracks.output.quality_cell.calls` | rounds |
| J2P-repeat · responses: p99 duration of a call at 16 concurrent requests, ms | 6,339.5 | `results/parser_and_engine_version/J2P-repeat/summary.json` | `tracks.output.quality_cell.latency_ms.p99` | rounds |
| J2P-repeat · responses: output tokens per call, median | 152 | `results/parser_and_engine_version/J2P-repeat/summary.json` | `tracks.output.quality_cell.completion_tokens.p50` | rounds |
| J2-today · Aegis 2.0 prompts: harmful items flagged, % · lower · upper end of the interval | 66.2 · 63.3 · 69.0 | `results/parser_and_engine_version/J2-today/summary.json` | `tracks.input.quality.aegis2.detection.{rate,wilson95[0],wilson95[1]} * 100` | rounds |
| J2-today · Aegis 2.0 prompts: harmful items flagged, count · of | 688 · 1,039 | `results/parser_and_engine_version/J2-today/summary.json` | `tracks.input.quality.aegis2.detection.{k,n}` | rounds |
| J2-today · Aegis 2.0 prompts: harmless items flagged, % · lower · upper end of the interval | 11.2 · 9.3 · 13.5 | `results/parser_and_engine_version/J2-today/summary.json` | `tracks.input.quality.aegis2.false_alarm.{rate,wilson95[0],wilson95[1]} * 100` | rounds |
| J2-today · Aegis 2.0 prompts: harmless items flagged, count · of | 100 · 889 | `results/parser_and_engine_version/J2-today/summary.json` | `tracks.input.quality.aegis2.false_alarm.{k,n}` | rounds |
| J2-today · Aegis 2.0 responses: harmful items flagged, % · lower · upper end of the interval | 62.9 · 58.1 · 67.6 | `results/parser_and_engine_version/J2-today/summary.json` | `tracks.output.quality.aegis2.detection.{rate,wilson95[0],wilson95[1]} * 100` | rounds |
| J2-today · Aegis 2.0 responses: harmful items flagged, count · of | 248 · 394 | `results/parser_and_engine_version/J2-today/summary.json` | `tracks.output.quality.aegis2.detection.{k,n}` | rounds |
| J2-today · Aegis 2.0 responses: harmless items flagged, % · lower · upper end of the interval | 15.8 · 12.6 · 19.5 | `results/parser_and_engine_version/J2-today/summary.json` | `tracks.output.quality.aegis2.false_alarm.{rate,wilson95[0],wilson95[1]} * 100` | rounds |
| J2-today · Aegis 2.0 responses: harmless items flagged, count · of | 66 · 419 | `results/parser_and_engine_version/J2-today/summary.json` | `tracks.output.quality.aegis2.false_alarm.{k,n}` | rounds |
| J2-today · prompts: verdicts per second at 16 concurrent requests | 9.0 | `results/parser_and_engine_version/J2-today/summary.json` | `tracks.input.quality_cell.verdicts_per_s` | rounds |
| J2-today · prompts: calls in that cell | 2,423 | `results/parser_and_engine_version/J2-today/summary.json` | `tracks.input.quality_cell.calls` | rounds |
| J2-today · prompts: p99 duration of a call at 16 concurrent requests, ms | 7,120.5 | `results/parser_and_engine_version/J2-today/summary.json` | `tracks.input.quality_cell.latency_ms.p99` | rounds |
| J2-today · prompts: output tokens per call, median | 113 | `results/parser_and_engine_version/J2-today/summary.json` | `tracks.input.quality_cell.completion_tokens.p50` | rounds |
| J2-today · responses: verdicts per second at 16 concurrent requests | 8.0 | `results/parser_and_engine_version/J2-today/summary.json` | `tracks.output.quality_cell.verdicts_per_s` | rounds |
| J2-today · responses: calls in that cell | 813 | `results/parser_and_engine_version/J2-today/summary.json` | `tracks.output.quality_cell.calls` | rounds |
| J2-today · responses: p99 duration of a call at 16 concurrent requests, ms | 6,612.5 | `results/parser_and_engine_version/J2-today/summary.json` | `tracks.output.quality_cell.latency_ms.p99` | rounds |
| J2-today · responses: output tokens per call, median | 149 | `results/parser_and_engine_version/J2-today/summary.json` | `tracks.output.quality_cell.completion_tokens.p50` | rounds |
| J6-v010 · Aegis 2.0 prompts: harmful items flagged, % · lower · upper end of the interval | 87.8 · 85.6 · 89.6 | `results/parser_and_engine_version/J6-v010/summary.json` | `tracks.input.quality.aegis2.detection.{rate,wilson95[0],wilson95[1]} * 100` | rounds |
| J6-v010 · Aegis 2.0 prompts: harmful items flagged, count · of | 912 · 1,039 | `results/parser_and_engine_version/J6-v010/summary.json` | `tracks.input.quality.aegis2.detection.{k,n}` | rounds |
| J6-v010 · Aegis 2.0 prompts: harmless items flagged, % · lower · upper end of the interval | 15.4 · 13.2 · 17.9 | `results/parser_and_engine_version/J6-v010/summary.json` | `tracks.input.quality.aegis2.false_alarm.{rate,wilson95[0],wilson95[1]} * 100` | rounds |
| J6-v010 · Aegis 2.0 prompts: harmless items flagged, count · of | 137 · 889 | `results/parser_and_engine_version/J6-v010/summary.json` | `tracks.input.quality.aegis2.false_alarm.{k,n}` | rounds |
| J6-v010 · XSTest prompts: harmful items flagged, % · lower · upper end of the interval | 94.0 · 89.8 · 96.5 | `results/parser_and_engine_version/J6-v010/summary.json` | `tracks.input.quality.xstest.detection.{rate,wilson95[0],wilson95[1]} * 100` | rounds |
| J6-v010 · XSTest prompts: harmful items flagged, count · of | 188 · 200 | `results/parser_and_engine_version/J6-v010/summary.json` | `tracks.input.quality.xstest.detection.{k,n}` | rounds |
| J6-v010 · XSTest prompts: harmless items flagged, % · lower · upper end of the interval | 23.6 · 18.8 · 29.2 | `results/parser_and_engine_version/J6-v010/summary.json` | `tracks.input.quality.xstest.false_alarm.{rate,wilson95[0],wilson95[1]} * 100` | rounds |
| J6-v010 · XSTest prompts: harmless items flagged, count · of | 59 · 250 | `results/parser_and_engine_version/J6-v010/summary.json` | `tracks.input.quality.xstest.false_alarm.{k,n}` | rounds |
| J6-v010 · Aegis 2.0 responses: harmful items flagged, % · lower · upper end of the interval | 87.3 · 83.7 · 90.2 | `results/parser_and_engine_version/J6-v010/summary.json` | `tracks.output.quality.aegis2.detection.{rate,wilson95[0],wilson95[1]} * 100` | rounds |
| J6-v010 · Aegis 2.0 responses: harmful items flagged, count · of | 344 · 394 | `results/parser_and_engine_version/J6-v010/summary.json` | `tracks.output.quality.aegis2.detection.{k,n}` | rounds |
| J6-v010 · Aegis 2.0 responses: harmless items flagged, % · lower · upper end of the interval | 14.3 · 11.3 · 18.0 | `results/parser_and_engine_version/J6-v010/summary.json` | `tracks.output.quality.aegis2.false_alarm.{rate,wilson95[0],wilson95[1]} * 100` | rounds |
| J6-v010 · Aegis 2.0 responses: harmless items flagged, count · of | 60 · 419 | `results/parser_and_engine_version/J6-v010/summary.json` | `tracks.output.quality.aegis2.false_alarm.{k,n}` | rounds |
| J6-v010 · prompts: verdicts per second at 16 concurrent requests | 39.5 | `results/parser_and_engine_version/J6-v010/summary.json` | `tracks.input.quality_cell.verdicts_per_s` | rounds |
| J6-v010 · prompts: calls in that cell | 2,423 | `results/parser_and_engine_version/J6-v010/summary.json` | `tracks.input.quality_cell.calls` | rounds |
| J6-v010 · prompts: p99 duration of a call at 16 concurrent requests, ms | 863.7 | `results/parser_and_engine_version/J6-v010/summary.json` | `tracks.input.quality_cell.latency_ms.p99` | rounds |
| J6-v010 · prompts: output tokens per call, median | 18 | `results/parser_and_engine_version/J6-v010/summary.json` | `tracks.input.quality_cell.completion_tokens.p50` | rounds |
| J6-v010 · prompts: median duration of a call, one request at a time, ms | 228.1 | `results/parser_and_engine_version/J6-v010/summary.json` | `tracks.input.c1.latency_ms.p50` | rounds |
| J6-v010 · responses: verdicts per second at 16 concurrent requests | 25.4 | `results/parser_and_engine_version/J6-v010/summary.json` | `tracks.output.quality_cell.verdicts_per_s` | rounds |
| J6-v010 · responses: calls in that cell | 813 | `results/parser_and_engine_version/J6-v010/summary.json` | `tracks.output.quality_cell.calls` | rounds |
| J6-v010 · responses: p99 duration of a call at 16 concurrent requests, ms | 1,042.2 | `results/parser_and_engine_version/J6-v010/summary.json` | `tracks.output.quality_cell.latency_ms.p99` | rounds |
| J6-v010 · responses: output tokens per call, median | 27 | `results/parser_and_engine_version/J6-v010/summary.json` | `tracks.output.quality_cell.completion_tokens.p50` | rounds |
| J6-v010 · responses: median duration of a call, one request at a time, ms | 321.7 | `results/parser_and_engine_version/J6-v010/summary.json` | `tracks.output.c1.latency_ms.p50` | rounds |
| J2P · prompts: calls where the rail's decision and the model's answer agree · calls | 2,421 · 2,423 | `results/parser_and_engine_version/J2P/rail_beside_verdict.json` | `input.{agree,items}` | rounds |
| J2P · prompts: calls where they do not agree | 2 | `results/parser_and_engine_version/J2P/rail_beside_verdict.json` | `input.items - input.agree` | rounds |
| J2P · prompts: of those, the rail blocked and the answer had no verdict (cut at the limit · unreadable) | 1 · 1 | `results/parser_and_engine_version/J2P/rail_beside_verdict.json` | `input.classes.{block_and_no_verdict_truncated,block_and_no_verdict_unreadable}` | rounds |
| J2P · responses: calls where the rail's decision and the model's answer agree · calls | 813 · 813 | `results/parser_and_engine_version/J2P/rail_beside_verdict.json` | `output.{agree,items}` | rounds |
| J2P · both tracks: calls | 3,236 | `results/parser_and_engine_version/J2P/rail_beside_verdict.json` | `input.items + output.items` | rounds |
| J6G · both tracks: rail decision and verdict of the same call, agree | 200 | `results/safety_guard_nim/J6G/summary.json` | `tracks.input.rail_beside_verdict_of_the_same_call.agree.k + tracks.output.rail_beside_verdict_of_the_same_call.agree.k` | rounds |
| J6G · both tracks: rail decision and verdict of the same call, calls | 200 | `results/safety_guard_nim/J6G/summary.json` | `tracks.input.rail_beside_verdict_of_the_same_call.agree.n + tracks.output.rail_beside_verdict_of_the_same_call.agree.n` | rounds |
| J6N · size of the image's generic profile as its support matrix gives it, GB | 14.97 | `results/safety_guard_nim/prediction_safety_guard_nim.json` | `BF16, vLLM, 1 GPU, 14.97 GB` | text |
| J6-v010 (upstream vLLM image v0.10.0) against J6N (the NIM): verdicts per second at 16 concurrent requests, prompts, difference in % | +2.6 | `results/parser_and_engine_version/J6-v010/summary.json` | `(tracks.input.quality_cell.verdicts_per_s / results/safety_guard_nim/J6N/summary.json::tracks.input.quality_cell.verdicts_per_s - 1) * 100` | rounds |
| J6-v010 (upstream vLLM image v0.10.0) against J6N (the NIM): verdicts per second at 16 concurrent requests, responses, difference in % | +3.9 | `results/parser_and_engine_version/J6-v010/summary.json` | `(tracks.output.quality_cell.verdicts_per_s / results/safety_guard_nim/J6N/summary.json::tracks.output.quality_cell.verdicts_per_s - 1) * 100` | rounds |
| J6N (the NIM) against J6-today (upstream vLLM 0.20.2, the same night): verdicts per second at 16 concurrent requests, prompts, difference in % | −18.9 | `results/safety_guard_nim/J6N/summary.json` | `(tracks.input.quality_cell.verdicts_per_s / results/safety_guard_nim/J6-today/summary.json::tracks.input.quality_cell.verdicts_per_s - 1) * 100` | rounds |
| J6N (the NIM) against J6-today (upstream vLLM 0.20.2, the same night): verdicts per second at 16 concurrent requests, responses, difference in % | −19.6 | `results/safety_guard_nim/J6N/summary.json` | `(tracks.output.quality_cell.verdicts_per_s / results/safety_guard_nim/J6-today/summary.json::tracks.output.quality_cell.verdicts_per_s - 1) * 100` | rounds |
| J6-v010 (upstream vLLM image v0.10.0) against J6-today (upstream vLLM 0.20.2): verdicts per second at 16 concurrent requests, prompts, difference in % | −16.8 | `results/parser_and_engine_version/J6-v010/summary.json` | `(tracks.input.quality_cell.verdicts_per_s / results/safety_guard_nim/J6-today/summary.json::tracks.input.quality_cell.verdicts_per_s - 1) * 100` | rounds |
| J6-v010 (upstream vLLM image v0.10.0) against J6-today (upstream vLLM 0.20.2): verdicts per second at 16 concurrent requests, responses, difference in % | −16.5 | `results/parser_and_engine_version/J6-v010/summary.json` | `(tracks.output.quality_cell.verdicts_per_s / results/safety_guard_nim/J6-today/summary.json::tracks.output.quality_cell.verdicts_per_s - 1) * 100` | rounds |
| J6-today (6 October) against J6 (2 October), the same server and settings: verdicts per second at 16 concurrent requests, prompts, difference in % | +3.4 | `results/safety_guard_nim/J6-today/summary.json` | `(tracks.input.quality_cell.verdicts_per_s / results/p93_judges/J6/summary.json::tracks.input.quality_cell.verdicts_per_s - 1) * 100` | rounds |
| J6-today (6 October) against J6 (2 October), the same server and settings: verdicts per second at 16 concurrent requests, responses, difference in % | +1.1 | `results/safety_guard_nim/J6-today/summary.json` | `(tracks.output.quality_cell.verdicts_per_s / results/p93_judges/J6/summary.json::tracks.output.quality_cell.verdicts_per_s - 1) * 100` | rounds |
| J2P-repeat (parser on the server) against J2-today (no parser, the same day): verdicts per second at 16 concurrent requests, prompts, difference in % | +1.0 | `results/parser_and_engine_version/J2P-repeat/summary.json` | `(tracks.input.quality_cell.verdicts_per_s / results/parser_and_engine_version/J2-today/summary.json::tracks.input.quality_cell.verdicts_per_s - 1) * 100` | rounds |
| J2P-repeat (parser on the server) against J2-today (no parser, the same day): verdicts per second at 16 concurrent requests, responses, difference in % | −1.4 | `results/parser_and_engine_version/J2P-repeat/summary.json` | `(tracks.output.quality_cell.verdicts_per_s / results/parser_and_engine_version/J2-today/summary.json::tracks.output.quality_cell.verdicts_per_s - 1) * 100` | rounds |
| J2P (the first container) against J2P-repeat (a second container of the same arm): verdicts per second at 16 concurrent requests, prompts, difference in % | −47.6 | `results/parser_and_engine_version/J2P/summary.json` | `(tracks.input.quality_cell.verdicts_per_s / results/parser_and_engine_version/J2P-repeat/summary.json::tracks.input.quality_cell.verdicts_per_s - 1) * 100` | rounds |
| J2P (the first container) against J2P-repeat (a second container of the same arm): verdicts per second at 16 concurrent requests, responses, difference in % | −44.3 | `results/parser_and_engine_version/J2P/summary.json` | `(tracks.output.quality_cell.verdicts_per_s / results/parser_and_engine_version/J2P-repeat/summary.json::tracks.output.quality_cell.verdicts_per_s - 1) * 100` | rounds |
| J0 (Llama 3.1 8B, 3 tokens): verdicts per second at 16 concurrent requests, responses minus prompts | +8.3 | `results/p93_judges/table.json` | `arms.J0.tracks.output.quality_cell.verdicts_per_s - arms.J0.tracks.input.quality_cell.verdicts_per_s` | rounds |
| J1 (Llama 3.1 8B, default): verdicts per second at 16 concurrent requests, responses minus prompts | −6.2 | `results/p93_judges/table.json` | `arms.J1.tracks.output.quality_cell.verdicts_per_s - arms.J1.tracks.input.quality_cell.verdicts_per_s` | rounds |
| J2 (Nemotron 3 Nano, reasoning on): verdicts per second at 16 concurrent requests, responses minus prompts | −1.3 | `results/p93_judges/table.json` | `arms.J2.tracks.output.quality_cell.verdicts_per_s - arms.J2.tracks.input.quality_cell.verdicts_per_s` | rounds |
| J3 (Nemotron 3 Nano, reasoning off): verdicts per second at 16 concurrent requests, responses minus prompts | −0.5 | `results/p93_judges/table.json` | `arms.J3.tracks.output.quality_cell.verdicts_per_s - arms.J3.tracks.input.quality_cell.verdicts_per_s` | rounds |
| J4 (Nemotron 3.5 CS, reasoning off): verdicts per second at 16 concurrent requests, responses minus prompts | −30.5 | `results/p93_judges/table.json` | `arms.J4.tracks.output.quality_cell.verdicts_per_s - arms.J4.tracks.input.quality_cell.verdicts_per_s` | rounds |
| J5 (Nemotron 3.5 CS, reasoning on): verdicts per second at 16 concurrent requests, responses minus prompts | −3.7 | `results/p93_judges/table.json` | `arms.J5.tracks.output.quality_cell.verdicts_per_s - arms.J5.tracks.input.quality_cell.verdicts_per_s` | rounds |
| J6 (Safety Guard 8B v3): verdicts per second at 16 concurrent requests, responses minus prompts | −15.8 | `results/p93_judges/table.json` | `arms.J6.tracks.output.quality_cell.verdicts_per_s - arms.J6.tracks.input.quality_cell.verdicts_per_s` | rounds |
| J2P-repeat (Nemotron 3 Nano, reasoning on, parser): verdicts per second at 16 concurrent requests, responses minus prompts | −1.2 | `results/parser_and_engine_version/J2P-repeat/summary.json` | `tracks.output.quality_cell.verdicts_per_s - tracks.input.quality_cell.verdicts_per_s` | rounds |
| J6N (Safety Guard 8B v3, NIM): verdicts per second at 16 concurrent requests, responses minus prompts | −14.0 | `results/safety_guard_nim/J6N/summary.json` | `tracks.output.quality_cell.verdicts_per_s - tracks.input.quality_cell.verdicts_per_s` | rounds |
| LG3 (Llama Guard 3 8B, reference): verdicts per second at 16 concurrent requests, responses minus prompts | −33.3 | `results/p102_followup/LG3/summary.json` | `tracks.output.quality_cell.verdicts_per_s - tracks.input.quality_cell.verdicts_per_s` | rounds |
| Graphics driver during the timed cells of the seven arms of the study and the reference arm | "591.86" | `figures/detection_vs_rate_points.json` | `tracks.input.points[0].driver` | equals |
| Graphics driver during the timed cells of the NIM arm and the parser arm | "610.88" | `figures/detection_vs_rate_points.json` | `tracks.input.points[8].driver` | equals |
| Aegis 2.0 responses: safe labels given by the LLM jury | 81 | `results/p93_judges/items_summary.json` | `output_track.by_gold_and_source.safe\|llm_jury` | rounds |
| Aegis 2.0 responses: safe labels in all (human and LLM jury) | 419 | `results/p93_judges/items_summary.json` | `output_track.by_gold_and_source.safe\|human + output_track.by_gold_and_source.safe\|llm_jury` | rounds |
| Aegis 2.0 responses: unsafe labels given by the LLM jury | 394 | `results/p93_judges/items_summary.json` | `output_track.by_gold_and_source.unsafe\|llm_jury` | rounds |

<!-- end of the parser and engine-version rows -->

**How to check a row:** open the file, follow the key, compare. Or check every row at once: `python ../tools/check_claims.py README.md` (from this directory). `results/p93_judges/table.json` holds the seven arms' summaries as they were read from each arm's own `summary.json`; nothing in it is computed across arms.

## Run it

Three starting points, each copied from a run recorded in this directory (the container names are the runs' own). `$NGC_ENV_FILE` is a file holding the NGC key (passed by path, never printed); `$NIM_CACHE_DIR` is a folder for the NIM's model cache. All three were run on one RTX 5090 (32 GB), Windows 11 with Docker Desktop (WSL2), graphics driver 610.88, on 2026-10-06.

### 1 · The Safety Guard model through its NIM, on a card its optimised profiles do not list

The NIM `llama-3.1-nemotron-safety-guard-8b-v3:1.14.0` selects no profile by itself on this card; its two TensorRT-LLM FP8 profiles are refused ("is incompatible with detected hardware"). The generic profile (vLLM, BF16), named by its id, starts and serves (ready after 251 to 327 s, 31,892 MiB on the card):

```bash
docker run -d --name sgnim_generic_main --gpus all --shm-size=64GB -p 127.0.0.1:8000:8000 \
  --env-file "$NGC_ENV_FILE" \
  -e NIM_MODEL_PROFILE=47804570e8db67fdc60d9cb518b0f60316ac4eb0f3a55af81aafefe124505a8f \
  -e NIM_MAX_MODEL_LEN=8192 \
  -v "$NIM_CACHE_DIR:/opt/nim/.cache" \
  nvcr.io/nim/nvidia/llama-3.1-nemotron-safety-guard-8b-v3:1.14.0
```

Recorded in [`results/safety_guard_nim/events.jsonl`](results/safety_guard_nim/events.jsonl) (the `container_ready` lines carry the command); figures in [`results/safety_guard_nim/`](results/safety_guard_nim/README.md).

### 2 · That model behind the NeMo Guardrails content-safety rail

`config.yml` as used (NeMo Guardrails 0.24.1). The model is named once per entry: the library rejects a configuration that names it in `model` and again in `parameters.model_name` ("Model name must be specified in exactly one place").

```yaml
models:
  - type: main
    engine: nim
    model: nvidia/llama-3.1-nemotron-safety-guard-8b-v3
    parameters:
      base_url: "http://127.0.0.1:8000/v1"

  - type: content_safety
    engine: nim
    model: nvidia/llama-3.1-nemotron-safety-guard-8b-v3
    parameters:
      base_url: "http://127.0.0.1:8000/v1"

rails:
  input:
    flows:
      - content safety check input $model=content_safety
  output:
    flows:
      - content safety check output $model=content_safety
```

`prompts.yml` beside it is the library's own `examples/configs/content_safety_multilingual/prompts.yml` at tag `v0.24.1`, byte for byte ([`scripts/guardrails_safety_guard/prompts.yml`](scripts/guardrails_safety_guard/prompts.yml)). Both files as written by the run: [`results/safety_guard_nim/J6G/gr_config/`](results/safety_guard_nim/J6G/gr_config/).

### 3 · Nemotron 3 Nano as a self-check model, with the reasoning parser on the server

Without the last `-e` line the self-check rail blocks every item when the model reasons (arm J2); with it the reasoning is separated on the server and the rail reads the model's answer (arm J2P: on the whole of both tracks its decisions and the model's answers differ on 2 of 2,423 prompts and 0 of 813 responses):

```bash
docker run -d --name vol3fu_parser_main --gpus all -p 127.0.0.1:8000:8000 \
  --env-file "$NGC_ENV_FILE" \
  -e NIM_MODEL_PROFILE=1fba9ecfcfb4cde28d4ce3fd55c40bca89a5a613e25e98f057befe6a7e99eada \
  -e NIM_MAX_MODEL_LEN=8192 \
  -e NIM_PASSTHROUGH_ARGS="--reasoning-parser nemotron_v3" \
  -v "$NIM_CACHE_DIR:/opt/nim/.cache" \
  nvcr.io/nim/nvidia/nemotron-3-nano:2.0.12
```

Recorded in [`results/parser_and_engine_version/events.jsonl`](results/parser_and_engine_version/events.jsonl); figures in [`results/parser_and_engine_version/`](results/parser_and_engine_version/README.md). The NIM's start-up log has no line about the argument; that it took effect shows in the responses (the reasoning arrives in its own field of the message, and the content carries no think tag).

## Internal identifiers

Identifiers made of `P` and two digits (e.g. `P17`, `P20`, `P28`) are internal work-order codes. They appear in script and directory names, docstrings, pre-registrations and result files.
**No public document corresponds to any of them.** They are kept, rather than renamed, because the frozen pre-registrations bind these scripts and inputs by SHA-256, and changing one character would break that binding. Read them as opaque provenance markers — nothing in this repository depends on knowing what they point to.
`P1`–`P4` (one digit) inside an analysis are precondition labels, not work-order codes.
