#!/usr/bin/env python3
"""Vol.2 · P78 · one chunk of an lm-eval run, in its own process (so that a chunk that hangs can be stopped from
outside and an engine that exits costs one chunk, not a task).

lm-evaluation-harness 0.4.13 (pinned venv), `local-chat-completions`, --apply_chat_template, --fewshot_as_multiturn,
temperature 0, the task's own prompt and few-shot configuration, pointed at the P78 logging proxy. The proxy (in the
parent process, p78_quality.py) applies the pre-registered request changes; this process does not know about them.
Writes, into --out:
  docs.jsonl     one row per document: task, doc_id, the sha256 of the messages lm-eval sent, and the gold answer
                 (GSM8K: the text after '####', normalised as p78_scorer does; MMLU: the letter)
  samples.json   lm-eval's logged samples (process bucket; they hold the prompt text)
  results.json   lm-eval's own aggregate metrics (kept for reference; P78 scores with p78_scorer)
usage: p78_lmeval_chunk.py --tasks T[,T] --ids FILE --model M --base URL --conc N --max-gen N --out DIR
"""
import argparse, hashlib, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import p78_scorer as SC  # noqa: E402

canon = lambda o: json.dumps(o, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def messages_of(sample):
    ctx = sample["arguments"]["gen_args_0"]["arg_0"] if isinstance(sample["arguments"], dict) else sample["arguments"][0][0]
    while isinstance(ctx, (list, tuple)) and ctx and not isinstance(ctx[0], dict):   # [[ctx], gen_kwargs] -> [ctx] -> ctx
        ctx = ctx[0]
    return json.loads(ctx) if isinstance(ctx, str) else ctx


def gold_of(task, sample):
    t = str(sample.get("target", "")).strip()
    if task.startswith("gsm8k"):
        return SC.gold_gsm8k(t)
    return t.rstrip(".").strip().upper()          # mmlu_llama targets are "A." .. "D."


def main():
    ap = argparse.ArgumentParser()
    for k in ("--tasks", "--ids", "--model", "--base", "--out"):
        ap.add_argument(k, required=True)
    ap.add_argument("--conc", type=int, required=True); ap.add_argument("--max-gen", type=int, required=True)
    a = ap.parse_args()
    import lm_eval
    os.makedirs(a.out, exist_ok=True)
    ids = json.load(open(a.ids, encoding="utf-8"))
    tasks = a.tasks.split(",")
    samples = {t: ids[t] for t in tasks}
    margs = {"model": a.model, "base_url": a.base, "num_concurrent": a.conc, "max_retries": 3, "timeout": 3600,
             "tokenized_requests": False, "tokenizer_backend": None}
    res = lm_eval.simple_evaluate(model="local-chat-completions", model_args=margs, tasks=tasks, apply_chat_template=True,
                                  fewshot_as_multiturn=True, log_samples=True, samples=samples,
                                  gen_kwargs={"max_gen_toks": a.max_gen}, bootstrap_iters=0)
    json.dump(res.get("samples"), open(os.path.join(a.out, "samples.json"), "w", encoding="utf-8", newline="\n"), ensure_ascii=False, default=str)
    json.dump({"results": res.get("results"), "lm_eval_version": getattr(lm_eval, "__version__", None), "model_args": margs,
               "tasks": tasks, "n_ids": {t: len(v) for t, v in samples.items()}},
              open(os.path.join(a.out, "results.json"), "w", encoding="utf-8", newline="\n"), ensure_ascii=False, default=str, indent=1)
    n = 0
    with open(os.path.join(a.out, "docs.jsonl"), "w", encoding="utf-8", newline="\n") as f:
        for task, rows in (res.get("samples") or {}).items():
            seen = set()
            for s in rows:
                if s["doc_id"] in seen:          # one row per document (lm-eval logs one sample per filter)
                    continue
                seen.add(s["doc_id"])
                f.write(json.dumps({"task": task, "doc_id": s["doc_id"], "messages_sha": hashlib.sha256(canon(messages_of(s))).hexdigest(),
                                    "gold": gold_of(task, s)}, ensure_ascii=False) + "\n"); n += 1
    want = sum(len(v) for v in samples.values())
    print(f"chunk docs {n} of {want}")
    return 0 if n == want else 4


if __name__ == "__main__":
    raise SystemExit(main())
