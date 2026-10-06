Forum post: <FORUM_URL>

![NeMo Guardrails on one RTX 5090: the models behind the rail](https://raw.githubusercontent.com/QuanTuring-AI/NV-benchmark/main/vol3-guardrails/figures/cover_vol3.png)

![Aegis 2.0 prompts: share of harmful items flagged, with its Wilson 95% interval, against verdicts per second at 16 concurrent requests; one point per arm](https://raw.githubusercontent.com/QuanTuring-AI/NV-benchmark/main/vol3-guardrails/figures/detection_vs_rate_input_dark.png)

![Aegis 2.0 responses: share of harmful items flagged, with its Wilson 95% interval, against verdicts per second at 16 concurrent requests; one point per arm](https://raw.githubusercontent.com/QuanTuring-AI/NV-benchmark/main/vol3-guardrails/figures/detection_vs_rate_output_dark.png)

NeMo Guardrails on one RTX 5090: seven models behind the rail, what each one flags, and what a verdict costs. One model on the card at a time; every figure is about one arm on its own.

- **The dedicated safety models flag the most harmful prompts, and also raise the most false alarms.** Nemotron 3.5 Content Safety (reasoning off) flagged 89.3% of the harmful Aegis prompts and 20.8% of the harmless ones; Llama 3.1 Nemotron Safety Guard 8B v3 flagged 87.8% and 15.4%. Both have Aegis in their training lineage, so read XSTest beside it.
- **A general model through the Guardrails self-check rail sits lower: Llama 3.1 8B flagged 72.9% of the harmful prompts and 15.4% of the harmless ones.** Capping its answer at 3 tokens changed nothing in the verdicts (72.9% against 73.0%) and cut the median time per verdict from 568 ms to 51 ms at one request at a time.
- **Reasoning did not buy accuracy here.** Nemotron 3.5 Content Safety with reasoning on flagged 87.7% (off: 89.3%) with the same false-alarm rate, at 10.8 verdicts per second instead of 87.0 at 16 concurrent requests. Nemotron 3 Nano with reasoning on flagged more than with it off (66.5% against 54.9%), but see the next line.

**Read:** [Vol.3 README](https://github.com/QuanTuring-AI/NV-benchmark/blob/vol3/vol3-guardrails/README.md) — results, method, and a claim-to-evidence table: every number in the post has a row in the README's claim-to-evidence table.
**Check every number:** `python tools/check_claims.py vol3-guardrails/README.md`
**Reproduce:** `git checkout vol3`
