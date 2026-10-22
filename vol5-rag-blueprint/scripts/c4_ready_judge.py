#!/usr/bin/env python3
"""Vol.5 · cell C4, supplement 6: the steady state after the answer model is ready, for the configuration whose stages
are timed with all three services on the card.

  alone      from the event file, the alone runs named by their tag (alone_start.tag): the n3 embedder, the reranker
             and the answer model at the configuration's setting; S = spill_judge.steady_shared(their shared samples,
             ready sample), D = their card delta (spill_judge.py's own definitions, imported)
  window     the configuration's shared samples from 60 s after the answer model's ready sample (30 samples at 2 s)
             to the end of the configuration run
  verdict    spilled_after_ready if any sample of the window rises above S_embed + S_rank + S_llm + 512 MiB; the times
             are measured either way and marked coresident_spilled when it holds (supplement 6)
usage: c4_ready_judge.py --events FILE --res DIR --config NAME --embed-tag TAG --rank-tag TAG --llm-tag TAG --out FILE
"""
import argparse, csv, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import spill_judge as J  # noqa: E402

SETTLE = 30


def shared_col(path):
    return [int(r["shared_mib"]) for r in csv.DictReader(open(path, encoding="utf-8-sig"))]


def main():
    ap = argparse.ArgumentParser()
    for x in ("--events", "--res", "--config", "--embed-tag", "--rank-tag", "--llm-tag", "--out"):
        ap.add_argument(x, required=True)
    a = ap.parse_args()
    ev = [json.loads(l) for l in open(a.events, encoding="utf-8") if l.strip()]
    alone, tag = {}, None
    for e in ev:
        if e["kind"] == "alone_start":
            tag = e.get("tag") or e.get("service")
        elif e["kind"] == "service_verdict" and tag and e.get("up"):
            sh = shared_col(os.path.join(a.res, f"alone_{tag}_windows_gpu_adapter_memory.csv"))
            alone[tag] = {"service": e["service"], "shared_mib": J.steady_shared(sh, e["ready_sample"]), "card_delta_mib": e["card_delta_mib"], "at": e["at"]}
        elif e["kind"] in ("alone_end", "config_start"):
            tag = None
    need = [a.embed_tag, a.rank_tag, a.llm_tag]
    missing = [t for t in need if t not in alone]
    if missing:
        raise SystemExit(f"refused: no alone run for {missing}")
    inside, llm = False, None
    for e in ev:
        if e["kind"] == "config_start":
            inside = e.get("name") == a.config
        elif inside and e["kind"] == "service_verdict" and e["service"] == "llm":
            llm = e
        elif inside and e["kind"] == "config_complete":
            break
    if not llm or not llm.get("up"):
        raise SystemExit("refused: the answer model of the configuration is not up")
    shared = shared_col(os.path.join(a.res, f"{a.config}_windows_gpu_adapter_memory.csv"))
    window = shared[llm["ready_sample"] + SETTLE:]
    allowed = sum(alone[t]["shared_mib"] for t in need) + J.MARGIN_MIB
    rec = {"configuration": a.config, "alone": {t: alone[t] for t in need}, "allowance_mib": allowed, "window_samples": len(window),
           "window_from_sample": llm["ready_sample"] + SETTLE, "window_max_mib": max(window) if window else None, "window_median_mib": sorted(window)[len(window) // 2] if window else None,
           "card_used_at_answer_model_ready_mib": llm["card_used_after_mib"], "whole_run_max_mib": max(shared),
           "spilled_after_ready": bool(window) and max(window) > allowed}
    json.dump(rec, open(a.out, "w", encoding="utf-8", newline="\n"), indent=1)
    print(json.dumps({k: rec[k] for k in ("configuration", "allowance_mib", "window_samples", "window_max_mib", "whole_run_max_mib", "spilled_after_ready")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
