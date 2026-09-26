#!/usr/bin/env python3
"""Vol.1-A revisit, P63 · GSM8K again on the four P62 configurations with the generation cap raised from 256 to 1024.

Everything is P62's harness (vol1a-revisit/scripts/p62_quality.py, imported unchanged): images, profiles, slot counts,
context 8,192, the logging proxy, residency, P59's health gate, `ollama show`, the template probe, lm-eval 0.4.13
`local-chat-completions`, gsm8k_cot_llama (8-shot, multi-turn chat), concurrency 8, temperature 0. Two changes:
  1. lm-eval's gen_kwargs carries max_gen_toks=1024 (P62 sent lm-eval's default 256). The proxy records what each
     request carried (`gen_settings_seen`, `max_tokens_seen`); a run in which any request carried another max_tokens is
     void (the analyser checks it).
  2. The join of lm-eval's samples to the proxy's records assigns, per item, the record whose output equals lm-eval's own
     response for that item (P62's post-run correction, here from the start).
Runs: O-Q4 main -> N-BF16 main, N-BF16 repeat -> O-FP16 main -> N-FP8 main (P62's arm order; containers keep P62's names).
usage: p63_gsm8k.py --out DIR --tokenizer DIR --store DIR [--arms a,b] [--test N]
env: NGC_ENV_FILE (NIM arms, --env-file, never read) · NIM_CACHE_DIR
"""
import argparse, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import p62_quality as Q  # noqa: E402
H = Q.H

MAX_GEN = 1024
Q.RUNS = {"O-Q4": [("gsm8k", 8, "main")], "N-BF16": [("gsm8k", 8, "main"), ("gsm8k", 8, "repeat")],
          "O-FP16": [("gsm8k", 8, "main")], "N-FP8": [("gsm8k", 8, "main")]}


def items_joined(samples_by_task, rows):
    """P62's public_items, then per-item assignment among records that share a messages sha (by lm-eval's own response)."""
    by_msg = {}
    for r in rows:
        if r.get("status") == 200 and "messages_sha" in r:
            by_msg.setdefault(r["messages_sha"], []).append(r)
    items, _ = Q.public_items("gsm8k", samples_by_task, rows)
    resp = {(sub, s["doc_id"]): Q.sha((s["resps"][0][0] if s.get("resps") else "").encode("utf-8")) for sub, rs in samples_by_task.items() for s in rs}
    used, unjoined, mismatch, shared = set(), 0, 0, 0
    for it in items:
        cands = by_msg.get(it["messages_sha"], [])
        shared += len(cands) > 1
        pick = next((c for c in cands if c.get("output_sha") == resp[(it["task"], it["doc_id"])] and id(c) not in used), None)
        if pick is None:
            unjoined += 0 if cands else 1; mismatch += 1 if cands else 0; continue
        used.add(id(pick))
        it.update({"request_sha": pick.get("request_sha"), "output_sha": pick.get("output_sha"), "output_chars": pick.get("output_chars"),
                   "prompt_tokens": (pick.get("usage") or {}).get("prompt_tokens"), "completion_tokens": (pick.get("usage") or {}).get("completion_tokens"),
                   "finish_reason": pick.get("finish_reason")})
    return items, {"items": len(items), "unjoined": unjoined, "items_sharing_a_prompt": shared, "resp_vs_proxy_text_mismatch": mismatch}


def run_task(a, arm, model, kind, task_key, conc, tag, ev):
    import lm_eval
    raw = os.path.join(a.out, "raw", arm, f"{task_key}_{tag}"); os.makedirs(raw, exist_ok=True)
    proxy = Q.Proxy(H.BASE[kind], os.path.join(raw, "proxy.jsonl"))
    samples = {Q.TASKS[task_key]: list(range(a.test))} if a.test else None
    margs = {"model": model, "base_url": f"http://127.0.0.1:{Q.PROXY_PORT}/v1/chat/completions", "num_concurrent": conc, "max_retries": 3,
             "timeout": 1800, "tokenized_requests": False, "tokenizer_backend": None}
    gk = {"max_gen_toks": MAX_GEN}
    t0 = H.now(); print(f"  {arm} {task_key} {tag} c={conc} start {t0}", flush=True)
    err = None
    try:
        res = lm_eval.simple_evaluate(model="local-chat-completions", model_args=margs, tasks=[Q.TASKS[task_key]], apply_chat_template=True,
                                      fewshot_as_multiturn=True, log_samples=True, samples=samples, gen_kwargs=gk, bootstrap_iters=0)
    except Exception as e:
        res, err = None, repr(e)[:500]
    proxy.close()
    t1 = H.now()
    rows = [json.loads(l) for l in open(os.path.join(raw, "proxy.jsonl"), encoding="utf-8")]
    rec = {"kind": "task_run", "arm": arm, "task": task_key, "lm_eval_task": Q.TASKS[task_key], "run": tag, "concurrency": conc, "start": t0, "end": t1,
           "error": err, "proxy_requests": len(rows), "proxy_non_200": sum(1 for r in rows if r.get("status") != 200),
           "gen_settings_seen": sorted({json.dumps(r.get("gen"), sort_keys=True) for r in rows})[:3],
           "max_tokens_seen": sorted({(r.get("gen") or {}).get("max_tokens") for r in rows}, key=str),
           "model_args": dict(margs), "gen_kwargs": gk}
    if res:
        json.dump(res.get("samples"), open(os.path.join(raw, "samples.json"), "w", encoding="utf-8", newline="\n"), ensure_ascii=False, default=str)
        items, join = items_joined(res["samples"], rows)
        pub = os.path.join(a.out, "items", f"{arm}__{task_key}__{tag}.jsonl"); os.makedirs(os.path.dirname(pub), exist_ok=True)
        with open(pub, "w", encoding="utf-8", newline="\n") as f:
            for it in items:
                f.write(json.dumps(it, ensure_ascii=False, sort_keys=True) + "\n")
        rec.update({"join": join, "lm_eval_results": {k: {m: v for m, v in d.items() if isinstance(v, (int, float, str))} for k, d in (res.get("results") or {}).items()},
                    "lm_eval_version": getattr(lm_eval, "__version__", None)})
        json.dump(res.get("configs"), open(os.path.join(raw, "configs.json"), "w", encoding="utf-8", newline="\n"), ensure_ascii=False, default=str, indent=1)
    ev.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n"); ev.flush()
    print(f"     end {t1} err={err} requests={len(rows)} max_tokens_seen={rec['max_tokens_seen']} join={rec.get('join')}", flush=True)


Q.run_task = run_task   # P62's run_arm looks the name up in its module at call time

if __name__ == "__main__":
    sys.argv[0] = __file__
    raise SystemExit(Q.main())
