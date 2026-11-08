# Chronicle of this repository's tags

Until 2026-10-01 this repository had nine tags. They were named after the volume numbers and the directory names of their day; three of them pointed to the same commit, and one carried a volume number that changed two days later. A reader could not tell which one to open. They were replaced by four: `vol1`, `vol2`, `vol3` and `chronicle`.

**Nothing was removed but the names.** Every commit in the table below is an ancestor of `main`, so every earlier state of the repository is still in it. To see one, use its full hash:

```
git checkout <full hash>
```

## The nine retired tags

| Tag | Commit (full hash) | Tag created | What it held, in today's volume numbers | Called at the time | Status |
|---|---|---|---|---|---|
| `vol1-vol2-published` | `aee6bfb19d4844b870b355f4019a36d4a04185fd` | 2026-10-01 | Vol.1 (renewed) and Vol.2 as the two articles describe them: all data of both volumes, the Vol.1 FP8 recheck, the READMEs with claim → evidence tables; in `vol1-nim/` and `vol2-nemotron/` | the same volume numbers | retired 2026-10-01 |
| `vol2-nemotron-published` | `6af6168cfe320d614919c2c48b9ab3445e93eb61` | 2026-10-01 | Vol.2 data through 2026-10-01 in `vol2-nemotron/`, and the Vol.1 FP8 recheck in `vol1-nim/results/p78_fp8_clean/`; the READMEs as they were before the rewrite | the same volume numbers. First set on 2026-09-29 at `e4f0ec5`, moved to this commit before it was ever pushed | retired 2026-10-01 |
| `vol3-judges-baseline` | `3efa794241d269f6f5e83e6b0bd4364b4fa8228e` | 2026-09-29 | Vol.3 baseline data, in `vol1b/` (the last commit before the directory renames) | Vol.3 by then; the directory still carried its first name | retired 2026-10-01 |
| `vol1-nim-published` | `3efa794241d269f6f5e83e6b0bd4364b4fa8228e` | 2026-09-28 | Vol.1 (renewed) as of 2026-09-28, in `vol1a-revisit/`; without the FP8 recheck | Vol.1; the directory still carried its first name | retired 2026-10-01 |
| `vol2-guardrails-published` | `3efa794241d269f6f5e83e6b0bd4364b4fa8228e` | 2026-09-28 | Vol.3 baseline data, in `vol1b/` | numbered Vol.2 from 2026-09-27 to 2026-09-29 | retired 2026-10-01 |
| `vol3-nemotron-published` | `e4f0ec5f401ed1c8c849e85cfea169f056c18ed1` | 2026-09-28 | Vol.2 data as of 2026-09-25, in `vol2/` | numbered Vol.3 from 2026-09-27 to 2026-09-29 | retired 2026-10-01 |
| `vol1-revisit-published` | `f6b73b2b67e6e5c1cd772fd5bcf70f17dda4a549` | 2026-09-27 | Vol.1 (renewed) as first pushed, in `vol1a-revisit/` | Vol.1 (renewed) | retired 2026-10-01 |
| `vol2-published` | `e4f0ec5f401ed1c8c849e85cfea169f056c18ed1` | 2026-09-25 | Vol.2 data as first pushed, in `vol2/` | Vol.2 | retired 2026-10-01 |
| `vol1b-published` | `40dfce018a877eeeaefb04dce6505a7daa75f604` | 2026-09-19 (a lightweight tag: the date of its commit) | Vol.3 baseline data as first pushed, in `vol1b/` | Vol.1-B | retired 2026-10-01 |

The hashes in this table were written by a script from `git rev-parse <tag>^{}` before the tags were removed.

## One more name, used for an hour

This file was first added as `HISTORY.md`, and the fourth tag was first called `history` (commit `75c1efc207751fab76493ca133ea9aeee233f182`). Both were renamed the same day, before any article or Release was published: "history" already means the commit history in git, and this file is a chronicle of the tags. `vol1`, `vol2` and `vol3` were first created on that commit too and were moved, with the fourth tag, to the commit that renames this file, so that all four open the same state.

## The six tags

| Tag | What it is |
|---|---|
| `vol1` | Vol.1, *Why NIM?* — the repository as the article describes it |
| `vol2` | Vol.2, *Nemotron 3 Nano on one RTX 5090* — the repository as the article describes it |
| `vol3` | Vol.3, *NeMo Guardrails on one RTX 5090: the models behind the rail* — the repository as the article describes it |
| `vol4` | Vol.4, *Nemotron retrieval on one RTX 5090* — the repository as the article describes it |
| `vol5` | Vol.5, *Nemotron on NVIDIA's RAG Blueprint, one RTX 5090* — the repository as the article describes it |
| `chronicle` | The commit that gives this file its name |

`vol1`, `vol2`, `vol3` and `chronicle` were created on 2026-10-01 and moved once the same day, for the rename described above, to the commit that renames this file to `CHRONICLE.md`. From that commit on they do not move, with one exception: **`vol3` moved once**, on 2026-10-10, the day the judge study was published, to the commit that holds it. Until then it pointed to the same commit as the other three (`281e014f26f656b24d66b3f68d1406611e034e4b`), which holds the Vol.3 baseline data without the study.

`vol4` was created on 2026-10-31, the day Vol.4 was published, at the commit that merges it, and does not move.

The message of `vol4` gives the SHA-256 of the article's source text as prepared for the forum, before the images were attached. The text on the forum ([thread 387528](https://forums.developer.nvidia.com/t/nemotron-retrieval-on-one-rtx-5090-4-9m-passage-miracl-zh-7-0m-ja-and-where-embedding-and-reranking-nims-top-out/387528)) differs from it in these ways and no others: the first line, the title, is the topic's title; the image placeholders are the uploaded images; the forum's editor wrote list items with `*` and table rules with `----`; the first reply begins with an empty line, and neither text ends with a line break; the link to the Vol.4 README reads "Vol.4 README of NV-benchmark", without "(tag `vol4`)", and goes to the same address; and the last line, the company's signature, is not there, because the forum's guidelines ask that posts not be signed. The SHA-256 of the text the forum returns at `/raw/387528/1` and `/raw/387528/2`, read on 2026-10-31: post `6e722d2bf40eb9fe7c091ffeeacac00fe8561748e8330730921223cb9361ab8d`, first reply `e323b2da4b6b578cbc81f6d680bab26b810e90819a20c57ab2cc2d845e099671`. The three images in the thread have the same pixels as the figures in `vol4-retriever/figures/`; the forum stored two of them as smaller PNG files.

`vol5` was created on 2026-11-08, the day Vol.5 was published, at the commit that merges it, and does not move.

The message of `vol5` gives the SHA-256 of the article's source text as prepared for the forum, before the images were attached. The text on the forum ([thread 388384](https://forums.developer.nvidia.com/t/nemotron-on-nvidias-rag-blueprint-one-rtx-5090-5-2m-passage-hotpotqa-end-to-end-and-nine-defaults-to-check-before-you-deploy/388384)) differs from it in these ways and no others: the first line, the title, is the topic's title; the image placeholders are the uploaded images; the forum's editor wrote list items with `*`, table rules with `----` and empty table cells with two spaces, and put a backslash before each square bracket in the quoted error messages; the first reply begins with an empty line, and neither text ends with a line break. The SHA-256 of the text the forum returns at `/raw/388384/1` and `/raw/388384/2`, read on 2026-11-08: post `bb8ec97f10ea5819c8d45cb1987b0feb87ec9b15bb9c5766db5f3c3fe6174515`, first reply `81271f01af04faf87763cf6f44d8a1d0225e0308aaff3b520c18abcb0e573e32`. The three images in the thread have the same pixels as the figures in `vol5-rag-blueprint/figures/`; the forum stored all three as smaller PNG files.

So there are six tags: `vol1`, `vol2` and `chronicle` point to `281e014f26f656b24d66b3f68d1406611e034e4b`, `vol3` to `2a57b8e75ba30bb64aada180be0676348577a0bc`, `vol4` to `c6c52ee5fd5c36b2b4acd370ca622bba23eb1ba7`, and `vol5` to the commit that merges Vol.5.

To rerun a harness byte for byte at the paths it was written with, [`PATH_MAP.md`](PATH_MAP.md) gives the commit for each volume.
