#!/usr/bin/env python3
"""E9 · Guardrails 0.23.0 的 270 點分析。
本分析同時輸出兩個延遲數字：
  ① 配對式：兩臂皆產生完整回應的同題同輪（n 寫出來）—— 與 Vol.1 +2.1% 同算法（已查實 Vol.1 = 類別內 avg，該類別全通過 ⇒ 等價配對）
  ② 裸平均：全部 135 vs 135，**標明含被擋題 ⇒ 無意義**
另外沿用既有的分離：harness 的 blocked 判定是比對拒絕措辭，會把「含關鍵字的完整回答」誤標 ⇒ 以 response_full 分出「真 rail 阻擋（罐頭）」。
"""
import json, os, statistics as st, sys, collections, datetime, subprocess
sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
RES = os.path.join(ROOT, "results", "e9")
SRC = os.path.join(RES, "e9_guardrails_0230.json")
REFUSAL = "I'm sorry, I can't respond to that."

d = json.load(open(SRC, encoding="utf-8"))
no, gr = d["nim_only"], d["nim_guardrails"]
cat = {x["id"]: x["category"] for x in json.load(open(os.path.join(ROOT, "..", "benchmark", "e3_questions.json"), encoding="utf-8"))}
true_block = lambda r: bool(r.get("was_blocked")) and r.get("response_full", "").strip() == REFUSAL
nom = {(r["question_id"], r["round"]): r for r in no}


def paired(sel):
    p = [(nom[(r["question_id"], r["round"])]["total_latency_ms"], r["total_latency_ms"])
         for r in gr if not true_block(r) and sel(r) and (r["question_id"], r["round"]) in nom]
    if not p:
        return None
    a = st.mean(x for x, _ in p); b = st.mean(y for _, y in p)
    return {"n_pairs": len(p), "nim_only_avg_ms": round(a), "guardrails_avg_ms": round(b),
            "overhead_ms": round(b - a), "overhead_pct": round(100 * (b - a) / a, 1),
            "median_overhead_pct": round(100 * (st.median([y for _, y in p]) - st.median([x for x, _ in p])) / st.median([x for x, _ in p]), 1)}


naive_nim = st.mean(r["total_latency_ms"] for r in no)
naive_gr = st.mean(r["total_latency_ms"] for r in gr)
blocked = [r for r in gr if true_block(r)]
mislabel = [r for r in gr if r.get("was_blocked") and not true_block(r)]
adv = [r for r in gr if cat[r["question_id"]] == "adversarial_input"]
passq = [r for r in gr if r["expected_action"] == "pass"]
by = collections.defaultdict(lambda: [0, 0])
for r in gr:
    by[cat[r["question_id"]]][1] += 1
    by[cat[r["question_id"]]][0] += (not true_block(r))

out = {"segment": "E9 · NIM + NeMo Guardrails 0.23.0 · Nemotron Nano 9B v2 · /no_think self-check",
       "metadata": d["metadata"], "n": {"nim_only": len(no), "guardrails": len(gr), "errors": sum(1 for r in no + gr if "error" in r)},
       "latency_paired_all_passed": paired(lambda r: True),
       "latency_paired_clean_only": paired(lambda r: cat[r["question_id"]] == "clean_passthrough"),
       "latency_naive_avg": {"nim_only_avg_ms": round(naive_nim), "guardrails_avg_ms": round(naive_gr),
                             "overhead_pct": round(100 * (naive_gr - naive_nim) / naive_nim, 1),
                             "⛔ 說明": "含被擋題（無回應，延遲極短）⇒ 無意義，僅為併列"},
       "detection": {"adversarial_true_blocked": sum(1 for r in adv if true_block(r)), "adversarial_n": len(adv),
                     "false_block_on_should_pass": sum(1 for r in passq if true_block(r)), "should_pass_n": len(passq)},
       "passthrough_by_category": {k: {"passed": v[0], "n": v[1]} for k, v in sorted(by.items())},
       "harness_mislabelled_as_blocked": {"n": len(mislabel), "items": [(r["question_id"], r["round"]) for r in mislabel][:10],
                                          "note": "harness 以拒絕措辭比對判 blocked；完整回答含關鍵字會被誤標（已知問題，見 KNOWN_CAVEAT）⛔ 未改判準，以 response_full 事後分離"},
       "vol1_comparison": {"vol1_clean_only_pct": 2.1, "vol1_all_passed_paired_pct": 3.1,
                           "note": "Vol.1 算法已查實（results/e7/s0_vol1_overhead_algorithm.json）：+2.1% = clean_passthrough 類別內 avg vs avg，該類別 100% 通過 ⇒ 與配對式等價。比較時子集必須一致。"},
       "analyzed_at": subprocess.run(["date", "+%FT%T"], capture_output=True, text=True).stdout.strip()}
json.dump(out, open(os.path.join(RES, "e9_analysis.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("配對式（全部通過題）:", out["latency_paired_all_passed"])
print("配對式（限 clean）  :", out["latency_paired_clean_only"])
print("裸平均（無意義）    :", out["latency_naive_avg"])
print("偵測:", out["detection"], "· 分類通過:", out["passthrough_by_category"], "· harness 誤標:", out["harness_mislabelled_as_blocked"]["n"])
