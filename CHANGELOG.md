# Changelog

Every change to this repository that reached `main`, newest first. Volumes are named by their current numbers throughout; directory and tag names are given as they were at the time. To read the volumes themselves, start from the [README](README.md).

## 2026-10-02 · Vol.2 forum post published

- **Vol.2 forum post:** the article was posted on the NVIDIA Developer Forum on 2026-10-02. The link is on the front page, at the top of [`vol2-nemotron/README.md`](vol2-nemotron/README.md) and in `releases/vol2.md`. → <https://forums.developer.nvidia.com/t/nemotron-3-nano-on-one-rtx-5090-with-nim-300-tok-s-flat-to-120k-context-128-concurrent-requests/384859>
- **Where the figures are in the thread:** the cover illustration and the chat figure are in the post; the RAG figure is in reply #2, because a new forum account may attach two images per post.

## 2026-10-02 · Vol.2: a cover illustration; the figures say "per request"

- **Cover illustration** for Vol.2, without text or numbers ([`vol2-nemotron/figures/cover_vol2.png`](vol2-nemotron/figures/cover_vol2.png)), shown in the README and in `releases/vol2.md` together with the chat figure.
- **Wording on the two Vol.2 figures:** the horizontal axis and the note at the dashed line now read *per request* where they read *per user*. A closed-loop sweep counts concurrent requests, not people. Only the words changed: every point is where it was, and `pareto_points.json` is byte for byte the same (its key names are unchanged).
- **Dark version shown.** The READMEs and the release notes of both volumes now show the dark version of each data figure, the one the Vol.1 forum post uses. The light versions stay in the two `figures/` directories.

## 2026-10-02 · Figures for Vol.1 and Vol.2; the Vol.1 forum link; a correction in `PATH_MAP.md`

- **Figures, drawn from data already published; nothing was measured for them.** Vol.1: total output throughput against the number of concurrent requests, and a cover illustration without text or numbers ([`vol1-nim/figures/`](vol1-nim/figures/)). Vol.2: total throughput against per-user speed, one figure for chat-shaped and one for RAG-shaped requests ([`vol2-nemotron/figures/`](vol2-nemotron/figures/)). Each data figure comes in a light and a dark version (SVG and PNG), with the script that draws it and a table that gives the source file and key of every point; the scripts read every point back from its source on each run. No tag moved: the figures are on `main`, not at `vol1` or `vol2`.
- **Vol.1 forum post:** the link to the article of 2026-10-01 is on the front page, at the top of [`vol1-nim/README.md`](vol1-nim/README.md) and in `releases/vol1.md`.
- **`PATH_MAP.md` corrected.** The Vol.2 row named a commit made after the directory renames, where none of the earlier paths exist. All three rows now name `3efa794`, the last commit before the renames, where every path in the first column of the map exists. Files added after the renames have no row: they were written at the current paths and are reproduced at the current tags.
- **`releases/vol1.md`** now shows the cover illustration and the throughput figure.

## 2026-10-01 · `HISTORY.md` renamed to `CHRONICLE.md`; the fourth tag is `chronicle`

- **Renamed the same day, before any article or Release was published.** "History" already means the commit history in git; the file is a chronicle of this repository's tags. → [`CHRONICLE.md`](CHRONICLE.md)
- **Tags:** `chronicle` replaces `history`. `vol1`, `vol2` and `vol3` were moved from `75c1efc` to the commit that makes this rename, so that all four open the same state. From here on they do not move, except `vol3` once, on the day the judge study is published.
- **The section below is left as written:** it names the tag `history` and links `HISTORY.md`, which is now `CHRONICLE.md`.

## 2026-10-01 · Tags consolidated to `vol1` `vol2` `vol3` `history`; release notes; the front page is a directory

- **Four tags.** `vol1` and `vol2` open the repository as the Vol.1 and Vol.2 articles describe it; `vol3` holds the Vol.3 baseline data and will move once, on the day the judge study is published; `history` marks the commit that adds [`HISTORY.md`](HISTORY.md).
- **Nine tags retired:** `vol1-vol2-published`, `vol2-nemotron-published`, `vol3-judges-baseline`, `vol1-nim-published`, `vol2-guardrails-published`, `vol3-nemotron-published`, `vol1-revisit-published`, `vol2-published`, `vol1b-published`. Their names, full hashes and contents are in `HISTORY.md`; every commit they pointed to is an ancestor of `main`, so nothing was removed but the names.
- **The earlier sections of this file are left as written,** tag names included: they record what was true on their day. The table *Tags from earlier pushes* at the end says those tags stay on the remote; from today they do not.
- **[`PATH_MAP.md`](PATH_MAP.md)** gives a full commit hash for a byte-for-byte rerun of each volume, instead of a tag name.
- **`releases/vol1.md`, `releases/vol2.md`:** the text of the two GitHub Releases, kept in the repository.
- **Front page:** a Volumes table that points to each volume's page and Release; the volumes' numbers are no longer repeated there.

## 2026-10-01 · READMEs rewritten around the articles' headlines; claim → evidence tables; tag `vol1-vol2-published`

- **Vol.1 and Vol.2 READMEs** now open the way the articles do: the headline (Vol.1: *Why NIM?*; Vol.2: *Nemotron 3 Nano on one RTX 5090*), a short summary, the `docker run` that was measured and the main table. No number changed.
- **Claim → evidence tables.** Every number in the two articles has a row with its file and the key inside it ([`vol1-nim/README.md`](vol1-nim/README.md), [`vol2-nemotron/README.md`](vol2-nemotron/README.md)). Where the stored value rounds differently from an earlier text, the table follows the file: the 4-bit build reads 3.3× fewer bytes per token, and bf16 NIM scores 68.9% on the MMLU sample.
- **Measurement conditions and what is not explained** have their own section in each README: other load on the desktop GPU, the part of a container that Windows can move to system RAM, container-to-container and session-to-session differences, the slow phase after READY, and the runs that are null by their own rules.
- **`tools/check_claims.py`** reads those tables, opens each file, follows each key and compares: `python tools/check_claims.py vol1-nim/README.md vol2-nemotron/README.md`.
- **Root README:** three lines per volume, a *How to check a number* walk-through, and the tags described by which article each one is for.
- **One statement narrowed:** `VLLM_USE_V2_MODEL_RUNNER=0` is needed by the Llama 3.1 8B image on this host; the Nemotron 3 Nano image started without it.
- **Tag** `vol1-vol2-published`: one tag for the Vol.1 and Vol.2 articles, holding all data of both volumes, the FP8 recheck and these READMEs. No pushed tag was moved.

## 2026-10-01 · Vol.2: answer quality, NIM against upstream vLLM, the concurrency sweeps repeated; Vol.1: FP8 in a clean window

- **Vol.2, answer quality:** GSM8K and an MMLU sample for both Nemotron options with reasoning on and off (P78). → [`vol2-nemotron/BASELINE.md`](vol2-nemotron/BASELINE.md) §H · `vol2-nemotron/results/p78_quality/`
- **Vol.2, NIM against the engine it contains, on Nemotron 3 Nano** (P78). → `BASELINE.md` §I · `vol2-nemotron/results/p78_nim_vs_vllm/`
- **Vol.2, the concurrency sweeps repeated on a gated night** (P80), after an audit of the earlier runs' end-of-cell GPU records (P78) and a diagnosis of a slow morning run (P79). Four of the six sweeps reproduce their SLO ceilings by the original runs' own rules; both values are published side by side. The dense option's engine exit is counted over two nights instead of being stated as a ceiling at 32. → `BASELINE.md` §C, §J · [`vol2-nemotron/results/p80_rerun/`](vol2-nemotron/results/p80_rerun/README.md) · `results/p78_audit/` · `results/p79_host_state/`
- **Vol.1, FP8 at 128 concurrent requests with the card otherwise idle** (P78, measured 29 September): 9,062 tok/s, 11.6× the clean-window 4-bit figure and 1.50× bf16 NIM in the same window. The two notes that announced this recheck are replaced by its result. → [`vol1-nim/README.md`](vol1-nim/README.md) §D · `vol1-nim/results/p78_fp8_clean/`
- **Tag** `vol2-nemotron-published` now points to `6af6168`, the commit that holds the runs above. It had been set to `e4f0ec5` on 2026-09-29 and was not pushed before today, so no pushed tag was moved. Two sentences were written while the tag still pointed to `e4f0ec5` and read wrongly at the new commit: `vol2-nemotron/README.md` says these runs "were added after the `vol2-nemotron-published` tag" (they are in it), and the two FP8 notes say "pending" (replaced on `main` by the commit after it). `vol3-judges-baseline` (`3efa794`) is pushed today as set on 2026-09-29.

## 2026-09-29 · Vol.2 and Vol.3 swapped; directories renamed again; this changelog

- **Vol.2 and Vol.3 swapped places** so that the reading order is NIM (Vol.1), then Nemotron on NIM (Vol.2), then judges (Vol.3): a reader meets Nemotron before reading about Nemotron as a judge.
- **Directories renamed to match**, as pure moves (1,228 files): `vol3-nemotron/` → [`vol2-nemotron/`](vol2-nemotron/README.md), `vol2-guardrails/` → [`vol3-judges/`](vol3-judges/README.md). Neither new name had been used before. [`PATH_MAP.md`](PATH_MAP.md) follows every path through both renames.
- **Tags** `vol2-nemotron-published` (`6af6168`; set to `e4f0ec5` on this day and moved on 2026-10-01 before it was ever pushed, see above) and `vol3-judges-baseline` (`3efa794`). This tag marks the baseline data; the judge study has not been published. The two tags pushed on 2026-09-28 for these volumes stay as they were (see the table below).
- **Vol.3** is titled as baseline data. Its Llama judge measurements (the Guardrails version bridge, the self-check `max_tokens` setting, the rails under load) are the baseline for a judge study that is in progress.
- **Vol.1:** its README no longer carries a Guardrails point, and it names no other volume.
- **This changelog** was added, and the README lists only the current tags.

## 2026-09-28 · Directories renamed; clean-window rechecks; Vol.3 additions

- **Directories renamed to match the volume numbers**, as pure moves (1,832 files): `vol1a-revisit/` → `vol1-nim/` (with the NIM-against-vLLM run that sat in `vol2/results/p54_engine/`), `vol1b/` → `vol2-guardrails/`, `vol2/` → `vol3-nemotron/`. [`PATH_MAP.md`](PATH_MAP.md) maps every old path. Files written before the rename, including frozen pre-registrations, keep the paths they were written with; `python tools/bound_files.py --history` checks each binding in the commit where its pre-registration was frozen.
- **Tags** `vol1-nim-published` and `vol2-guardrails-published` (both `3efa794`) and `vol3-nemotron-published` (`e4f0ec5`). Each points to the last commit before the rename that holds its volume's runs, so every path in those runs is correct there.
- **Vol.1:** the 128-request headline re-checked with the GPU otherwise idle, on 27 September. It reproduced the published ratios within 6%. The FP8 arm has no clean-window figure: its calibration gate failed. → [`vol1-nim/results/p70_clean_recheck/`](vol1-nim/results/p70_clean_recheck/README.md)
- **Vol.3:** NeMo Guardrails 0.23.0 under load at 1–128 concurrent requests → [`results/p66_rails_under_load/`](vol3-judges/results/p66_rails_under_load/README.md). The Guardrails server's own limits (worker processes, keep-alive) → [`results/p67_rails_server_config/`](vol3-judges/results/p67_rails_server_config/README.md).
- **Vol.3:** the levels of those two runs that had run with other GPU load, repeated with the GPU idle. The NIM-direct levels reproduced. The server-side levels ran with the host in a different state, so they are recorded but do not replace the earlier numbers. → [`results/p69_clean_rerun/`](vol3-judges/results/p69_clean_rerun/README.md)
- **README:** the headline is stated in concurrent requests; the documents use the volume numbers of that day only.

## 2026-09-27 · Vol.1 (renewed); volume numbers changed

- **Vol.1 (renewed)** published in `vol1a-revisit/`, now [`vol1-nim/`](vol1-nim/README.md). It covers NIM 2.0.12 against the engine it contains, what NIM is worth once several requests run at once, and answer quality (MMLU, GSM8K). Tag `vol1-revisit-published` → `f6b73b2`.
- **Volume numbers changed:** the NeMo Guardrails volume (now Vol.3) was numbered 2 and the Nemotron volume (now Vol.2) was numbered 3, until 2026-09-29. Directory names stayed as they were until 2026-09-28.

## 2026-09-25 · Vol.2 data

- **Vol.2 data:** two Nemotron deployment options on one RTX 5090 (fit, speed, concurrency, long context, NeMo Guardrails), published in `vol2/`, now [`vol2-nemotron/`](vol2-nemotron/README.md). Tag `vol2-published` → `e4f0ec5`. The write-up is to follow.

## 2026-09-19 · Vol.3 baseline data; the March 2026 comparison closed

- **Vol.3 baseline data:** NIM 1.13.1 → 2.0.12 × NeMo Guardrails 0.21.0 → 0.23.0 on one RTX 5090, published in `vol1b/`, now [`vol3-judges/`](vol3-judges/README.md). Tag `vol1b-published` → `40dfce0`.
- **The March 2026 NIM-versus-Ollama comparison** is closed as an account: [`vol3-judges/BASELINE.md`](vol3-judges/BASELINE.md) §12.

## 2026-06-28 · README

- The repository landing page was rewritten.

## 2026-03-31 · Vol.1 first published

- **Vol.1:** NIM against Ollama, and NeMo Guardrails' latency, on one RTX 5090, published on the NVIDIA Developer Forum with its evidence in [`benchmark/`](benchmark/) and [`DEPLOYMENT_NOTES.md`](DEPLOYMENT_NOTES.md). Both are kept exactly as published.

## Tags from earlier pushes

These tags were pushed before the volumes took their current numbers and directories. Their names follow the volume numbers and directory names of their day. They stay on the remote unchanged because links that have already been sent point to them. To rerun a volume, use the current tags in the [README](README.md#tags).

| Tag | Commit | Holds | Pushed |
|---|---|---|---|
| `vol2-guardrails-published` | `3efa794` | Vol.3, in `vol1b/` | 2026-09-28 |
| `vol3-nemotron-published` | `e4f0ec5` | Vol.2, in `vol2/` | 2026-09-28 |
| `vol1-revisit-published` | `f6b73b2` | Vol.1 (renewed), in `vol1a-revisit/` | 2026-09-27 |
| `vol1b-published` | `40dfce0` | Vol.3, in `vol1b/` | 2026-09-19 |
| `vol2-published` | `e4f0ec5` | Vol.2, in `vol2/` | 2026-09-25 |
