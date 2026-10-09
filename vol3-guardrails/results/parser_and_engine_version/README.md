# Two follow-up arms of the judge study: the reasoning parser on whole tracks, and the Safety Guard model on an older upstream vLLM

*Working data, 2026-10-06. One RTX 5090 (32 GB), Windows 11 with Docker Desktop (WSL2), graphics driver 610.88 (the study's cells of 2026-10-02 and 2026-10-03 recorded 591.86). One model on the card at a time. Items, prompts, answer parser, sampling and the definition of every figure are the study's ([`../p93_judges/`](../p93_judges/README.md)); the study's programs run unchanged against another server.*

**Scope rule.** Every figure is about one arm. Nothing here combines the per-item verdicts of two arms; the tables list each arm's own values side by side.

| File | What it is |
|---|---|
| `prediction_parser_and_engine_version.json` | pre-registration, frozen 2026-10-06T14:48:38+0800 (before the first container), SHA-256 `89fa48a3cac703040e4ff72a993a76407d6f63393ada246b8169c48ac08fb15d` |
| `addendum_parser_arm_precheck.json` | first addendum, frozen 2026-10-06T15:39:13+0800, SHA-256 `843174f0df425c85bc616d549a20c63f074e19b295bdd1f7941137ebfbd322fe`: why the parser arm's first run ran no cell, and the one rule replaced for its second run |
| `addendum_rate_repeat.json` | second addendum, frozen 2026-10-06T16:12:47+0800, SHA-256 `5946b8e839a03cded0d8f32c583f3f7a90b98a9ade0b652b3aa7da8222699a87`: the whole-track cell once more, and the study's arm J2 on the same day |
| `J6-v010/` · `J2P/` · `J2P-repeat/` · `J2-today/` | one folder per arm: `cells.jsonl`, per-item verdict files, `summary.json`, precheck records |
| `J2P_first_run/` | the precheck records of the parser arm's first run (no cell was run) |
| `before_the_run/engine_settings_from_start_logs.json` · `J6-v010/engine_settings_from_start_log.json` | what each server printed about its engine at start-up |
| `table.md` · `table.json` · `rate_repeat.json` | the side-by-side tables, built from the arms' `summary.json` files |
| `events.jsonl` | every step of the three runs as it happened |

## 1 · The Safety Guard model on upstream vLLM 0.10.0 (arm J6-v010)

The model's NIM 1.14.0 (arm J6N) gave about a fifth fewer verdicts per second than upstream vLLM 0.20.2 the same night (arm J6-today), and its engine reports itself as built from vLLM 0.10.0. This arm serves the same open weights with the upstream image tagged `v0.10.0`, started as the study starts upstream vLLM (`--max-model-len 8192`, nothing else set), and asks as the study's arm J6.

| Arm | Server | c=16 verdicts/s · prompts | c=16 verdicts/s · responses | c=1 p50 ms · prompts | c=1 p50 ms · responses | Detection · prompts | False alarm · prompts | Detection · responses | False alarm · responses |
|---|---|---|---|---|---|---|---|---|---|
| J6-today | upstream vLLM 0.20.2 | 47.5 | 30.5 | 194.2 | 282.9 | 87.7% (911/1039) | 15.3% (136/889) | 87.3% (344/394) | 14.1% (59/419) |
| **J6-v010** | upstream image tag v0.10.0 | 39.5 | 25.4 | 228.1 | 321.7 | 87.8% (912/1039) | 15.4% (137/889) | 87.3% (344/394) | 14.3% (60/419) |
| J6N | NIM 1.14.0, generic profile | 38.5 | 24.5 | 234.9 | 337.5 | 87.8% (912/1039) | 15.6% (139/889) | 87.6% (345/394) | 14.1% (59/419) |

- **Branch (decided in advance): within 5% of J6N on both tracks.** J6-v010 is +2.6% (prompts) and +3.9% (responses) against J6N, and -16.8% and -16.5% against J6-today. The difference between the NIM and upstream 0.20.2 goes with the engine version the NIM carries; what the NIM adds around that engine costs little or nothing here.
- All cells of 2026-10-06, each arm alone on the card, the idle-card gate before every cell. J6-today and J6N ran in the early-morning session, J6-v010 at 15:20.
- The upstream image tagged `v0.10.0` reports itself as `v0.10.1.dev1+gbcc0a3cbe`; the NIM's engine reports `v0.10.0+4019fef1.nv25.06.post1`. "The same engine version" is as far as two version strings say.
- Not claimed: which change between 0.10 and 0.20 makes the difference; anything above 16 calls in flight; anything about other models or other NIMs.

What each server printed at start-up:

| Setting | J6N · NIM 1.14.0 | J6-v010 · upstream tag v0.10.0 | J6-today · upstream 0.20.2 |
|---|---|---|---|
| engine version line | `v0.10.0+4019fef1.nv25.06.post1` | `v0.10.1.dev1+gbcc0a3cbe` | `v0.20.2` |
| precision | `torch.bfloat16` | `torch.bfloat16` | `torch.bfloat16` |
| context | `8192` | `8192` | `8192` |
| memory share (argument) | `0.9` | not printed | `0.9200` |
| sequence limit (argument) | not printed | not printed | not printed |
| chunked prefill | `True` | `True` | `True` |
| batched-token line | `Chunked prefill is enabled with max_num_batched_tokens=2048` | `Chunked prefill is enabled with max_num_batched_tokens=2048` | not printed |
| KV cache, GiB | `13.20` | `13.20` | `12.79` |
| KV cache, tokens | `108,144` | `108,128` | `104,800` |
| CUDA graph sizes captured | `67` | `67` | `51` |
| prefix caching | `True` | `True` | `True` |
| attention backend line | `Using Flash Attention backend on V1 engine.` | `Using Flash Attention backend on V1 engine.` | `Using FLASH_ATTN attention backend out of potential backends: ['FLASH_ATTN', 'FLASHINFER', 'TRITON_ATTN', 'FLEX_ATTENTION'].` |

## 2 · The reasoning parser on the whole of both tracks (arm J2P)

Nemotron 3 Nano on NIM 2.0.12 (NVFP4), reasoning on, asked through the NeMo Guardrails 0.24.1 self-check action with the Vol.1 rail prompts: the study's arm J2, with one change on the server, `NIM_PASSTHROUGH_ARGS="--reasoning-parser nemotron_v3"`. The study found that without the parser the rail blocks every item; on 100 stored prompts the parser repaired it ([`../p102_followup/`](../p102_followup/README.md)).

| Arm | Track · data | Detection | False alarm | Rail blocks: harmful · harmless | No verdict | Stability |
|---|---|---|---|---|---|---|
| J2 (2026-10-02, no parser) | input · aegis2 | 66.5% (691/1039) | 10.9% (97/889) | 100.0% (1039/1039) · 100.0% (889/889) | 4 | 96.0% (192/200) |
| J2 (2026-10-02, no parser) | input · xstest | 89.5% (179/200) | 6.0% (15/250) | 100.0% (200/200) · 100.0% (250/250) | 0 | 96.0% (192/200) |
| J2 (2026-10-02, no parser) | output · aegis2 | 61.2% (241/394) | 14.1% (59/419) | 100.0% (394/394) · 100.0% (419/419) | 0 | 91.0% (91/100) |
| **J2P** (2026-10-06, parser) | input · aegis2 | 66.0% (686/1039) | 10.1% (90/889) | 66.1% (687/1039) · 10.2% (91/889) | 2 | 95.0% (190/200) |
| **J2P** (2026-10-06, parser) | input · xstest | 88.5% (177/200) | 6.8% (17/250) | 88.5% (177/200) · 6.8% (17/250) | 0 | 95.0% (190/200) |
| **J2P** (2026-10-06, parser) | output · aegis2 | 60.4% (238/394) | 15.3% (64/419) | 60.4% (238/394) · 15.3% (64/419) | 0 | 87.0% (87/100) |

- **Branch (decided in advance): the rail's decision and the verdict of the same call differ on at most 1% of a track.** Prompts: 2 of 2,423 (0.08%), classes `{"block_and_no_verdict_unreadable": 1, "block_and_no_verdict_truncated": 1}`; responses: 0 of 813 (0.00%). Where they differ there is no verdict (an answer cut at the token limit, an answer the parser cannot read) and the rail blocks. With the parser on the server, the rail does what the model answers, on the whole set. The items are listed by id and class in `J2P/rail_beside_verdict.json`.
- The reasoning switch, checked on the server in each container and on each track: 10 of 10, 10 of 10, 10 of 10, 10 of 10 harmless answers carried their reasoning in the message's `reasoning` field, none with a think tag in the content.
- J2 and J2P were measured four days apart. Their verdict counts differ by a few items per group; so do two runs of one arm (the stability column: an arm that reasons does not repeat all of its own verdicts). See section 3 for a second run of each on 2026-10-06.

### The first run ran no cell

Both containers of the first run reported ready, the study's precheck ended with its verdict `fail`, and the bound runner ran nothing. The precheck requires, for an arm with reasoning on, that at least 9 of 10 harmless answers show their reasoning in what the Guardrails action returns (0 of 10, 0 of 10, 0 of 10, 0 of 10 in the four records). With the parser the reasoning is taken out of the answer before the library sees it: the change under test. The two controls passed in all four records (the violating control blocked, the harmless one allowed). This was readable in the precheck's code before the pre-registration was frozen and was not looked up: an error of the plan, about ten minutes of the card. The first addendum replaces that one rule by the same question asked on the server and changes nothing else.

## 3 · The rate of the parser arm (arms J2P-repeat and J2-today)

In the parser arm's run the whole-track cells at 16 in flight ran at half the rate of the study's J2, while its second container judged the stability subsets at J2's rate. The second addendum measured the whole-track cell again in a new container, and the study's arm without the parser on the same day.

| Arm | Day · container | Parser | verdicts/s · prompts | verdicts/s · responses | tokens/s · prompts | tokens/s · responses | Detection · prompts | False alarm · prompts | Detection · responses | False alarm · responses |
|---|---|---|---|---|---|---|---|---|---|---|
| J2 | 2026-10-02 (driver 591.86) | no | 9.36 | 8.07 | 1484 | 1506 | 66.5% (691/1039) | 10.9% (97/889) | 61.2% (241/394) | 14.1% (59/419) |
| J2P | 2026-10-06 15:45, first container | yes | 4.77 | 4.40 | 764 | 806 | 66.0% (686/1039) | 10.1% (90/889) | 60.4% (238/394) | 15.3% (64/419) |
| J2P-repeat | 2026-10-06 16:18, new container | yes | 9.11 | 7.90 | 1446 | 1480 | 66.5% (691/1039) | 10.0% (89/889) | 62.7% (247/394) | 15.3% (64/419) |
| J2-today | 2026-10-06 16:30, new container | no | 9.02 | 8.01 | 1457 | 1485 | 66.2% (688/1039) | 11.2% (100/889) | 62.9% (248/394) | 15.8% (66/419) |

- **Branch (decided in advance): both arms within 10% of the study's J2 on both tracks.** J2P-repeat -2.7% and -2.1%, J2-today -3.6% and -0.7%. The half rate belongs to the first container of the parser arm's run, or to the host while it ran; not to the parser and not to the day. The parser arm's rate is the repeat's; the slow run stays in the table.
- What made that container slow was not found. Its cells with one call at a time took as long as J2's; the card showed 31,795 to 31,827 MiB in use against 31,674 to 31,810 MiB in the two later containers; the idle-card gate passed before every cell. A container that is slow from its start with no sign in the memory reading has been seen on this host before; a rate from one container is one sample.
- The pre-registration expected the parser arm's verdicts within 1 point of J2's and its rate within 10%. In the pre-registered run the responses' false alarm was 1.2 points away and the rate was half: both expectations failed there. The four runs above show how far the counts of this model move between runs of the same request.

## Reproduce

```bash
# env: NGC_ENV_FILE, NIM_CACHE_DIR, P93_HF_HUB, VOL3_FOLLOWUP_BUCKET (a folder outside the repository)
python scripts/parser_and_engine_version_run.py --prediction results/parser_and_engine_version/prediction_parser_and_engine_version.json --gr-py <python with nemoguardrails 0.24.1>
python scripts/parser_arm_run.py --prediction <the same> --addendum results/parser_and_engine_version/addendum_parser_arm_precheck.json --gr-py <...>
python scripts/parser_arm_rate_repeat.py --prediction <the same> --addendum results/parser_and_engine_version/addendum_rate_repeat.json --gr-py <...>
```

The programs refuse to overwrite a result file; a rerun needs an empty results folder (`VOL3_FOLLOWUP_RESULTS`).
