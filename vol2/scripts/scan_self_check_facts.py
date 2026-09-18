#!/usr/bin/env python3
"""self_check_facts 鑑別力 · 單句污染掃描（SciFact · judge = Llama 3.1 8B · Guardrails 0.21.0）

設計：
  Phase A（校準閘）：SciFact 原生標籤 —— N 個 CONTRADICT (claim, evidence) 應得低分；N 個 SUPPORT 應得高分（陽性對照）。
      🔴 閘不過 ⇒ parser 讀不到答案 ⇒ 停，不跑 Phase B。
  Phase B（主掃描）：N=5 句答案取自 abstract；k=0..5 句由「程式」污染（數值替換／語義反轉／來源張冠李戴）；
      evidence = 完整 abstract（⛔ 不經檢索器）；每格 ≥20 題。
      k=5 是第二道陽性對照（全假仍未偵測 ⇒ 管線壞）。

量法：直接呼叫 nemoguardrails.library.self_check.facts.actions.self_check_facts
     （context = {relevant_chunks, bot_message}），得到 rail 的 float 分數（1.0 grounded / 0.0 not）。
     另以 monkeypatch 截取 judge 的原始 3-token 回應，逐題存檔供稽核。
"""
import argparse, asyncio, json, os, random, re, sys, time, datetime, hashlib
sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from nim_ttft import ctx, kernel_path   # 同一把尺：measurement_context / kernel 驗證

# ---------- SciFact ----------
def load_scifact(d):
    corpus = {x["doc_id"]: x for x in map(json.loads, open(os.path.join(d, "corpus.jsonl"), encoding="utf-8"))}
    claims = []
    for split in ("claims_train", "claims_dev"):
        for c in map(json.loads, open(os.path.join(d, f"{split}.jsonl"), encoding="utf-8")):
            c["_split"] = split; claims.append(c)
    return corpus, claims

def native_pairs(corpus, claims, label, n, rng):
    out = []
    for c in claims:
        for doc_id, evs in (c.get("evidence") or {}).items():
            for ev in evs:
                if ev["label"] == label:
                    doc = corpus[int(doc_id)]
                    sents = [doc["abstract"][i] for i in ev["sentences"] if i < len(doc["abstract"])]
                    out.append({"claim_id": c["id"], "split": c["_split"], "doc_id": int(doc_id), "label": label,
                                "claim": c["claim"], "evidence_sentences": sents, "abstract": doc["abstract"]})
    rng.shuffle(out); return out[:n]

# ---------- 程式化污染（⛔ 不用模型）----------
_INV = [("increase", "decrease"), ("increased", "decreased"), ("increases", "decreases"), ("higher", "lower"),
        ("more", "less"), ("positive", "negative"), ("positively", "negatively"), ("activates", "inhibits"),
        ("activation", "inhibition"), ("promotes", "suppresses"), ("promote", "suppress"), ("upregulated", "downregulated"),
        ("enhanced", "reduced"), ("enhances", "reduces"), ("greater", "smaller"), ("improved", "worsened"),
        ("significantly", "not significantly"), ("associated with", "not associated with"), (" is ", " is not "),
        (" are ", " are not "), (" was ", " was not "), (" were ", " were not "), (" can ", " cannot "), ("required", "not required")]
_NUM = re.compile(r"(?:(?<=^)|(?<=[\s(]))(\d+(?:\.\d+)?)(?=[\s%,.;)]|$)")   # 只改獨立數字，⛔ 不動 TLR-4 / CD14 這類識別碼

def pollute_numeric(s):
    m = _NUM.search(s)
    if not m: return None, None
    num = m.group(1); new = (str(int(float(num) * 10)) if "." not in num else f"{float(num) * 10:.1f}")
    return s[:m.start(1)] + new + s[m.end(1):], f"numeric:{num}->{new}"

def pollute_invert(s):
    low = s.lower()
    for a, b in _INV:
        i = low.find(a)
        if i >= 0:
            return s[:i] + b + s[i + len(a):], f"invert:{a.strip()}->{b.strip()}"
    return None, None

def pollute_misattrib(s, idx, corpus, doc_id, rng):
    for _ in range(50):
        other = corpus[rng.choice(list(corpus.keys()))]
        if other["doc_id"] != doc_id and len(other["abstract"]) > idx:
            return other["abstract"][idx], f"misattrib:doc{other['doc_id']}"
    return None, None

def pollute(sent, idx, method, corpus, doc_id, rng):
    order = {"numeric": [pollute_numeric, pollute_invert], "invert": [pollute_invert, pollute_numeric], "misattrib": []}[method]
    for f in order:
        new, tag = f(sent)
        if new and new != sent: return new, tag
    new, tag = pollute_misattrib(sent, idx, corpus, doc_id, rng)
    return new, tag

# ---------- rail 直呼 ----------
class Judge:
    def __init__(self, cfg_dir):
        from nemoguardrails import RailsConfig, LLMRails
        import nemoguardrails.library.self_check.facts.actions as fa
        self.rails = LLMRails(RailsConfig.from_path(cfg_dir))
        self.fa = fa; self.raw = []
        orig = fa.llm_call
        async def wrapped(*a, **k):
            r = await orig(*a, **k); self.raw.append(getattr(r, "content", r)); return r  # 0.23.0 回 LLMResponse 物件；0.21.0 回 str（不變）
        fa.llm_call = wrapped
        self.loop = asyncio.new_event_loop()

    def score(self, evidence_text, answer_text):
        self.raw.clear(); t0 = time.perf_counter()
        r = self.loop.run_until_complete(self.fa.self_check_facts(
            llm_task_manager=self.rails.runtime.llm_task_manager,
            context={"relevant_chunks": evidence_text, "bot_message": answer_text},
            llm=self.rails.llm, config=self.rails.config))
        return float(r), (self.raw[-1] if self.raw else None), round((time.perf_counter() - t0) * 1000, 1)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["gate", "scan", "both"], default="both")
    ap.add_argument("--scifact", default=os.path.join(ROOT, "data", "scifact", "data"))
    ap.add_argument("--cfg", default=os.path.join(HERE, "guardrails"))
    ap.add_argument("--container", required=True)
    ap.add_argument("--gate-n", type=int, default=10)
    ap.add_argument("--docs", type=int, default=24, help="Phase B 每個 k 的題數（≥20）")
    ap.add_argument("--N", type=int, default=5)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out-dir", default=os.path.join(ROOT, "results", "s6"))
    a = ap.parse_args()
    os.makedirs(a.out_dir, exist_ok=True)
    rng = random.Random(a.seed)
    corpus, claims = load_scifact(a.scifact)
    judge = Judge(a.cfg)
    before = ctx(); started = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    meta = {"judge_model": judge.rails.config.models[0].model, "guardrails_version": __import__("importlib.metadata").metadata.version("nemoguardrails"),
            "prompt_self_check_facts": next(p.content for p in judge.rails.config.prompts if p.task == "self_check_facts"),
            "scifact_manifest": json.load(open(os.path.join(ROOT, "data", "scifact", "scifact.manifest.json"), encoding="utf-8")),
            "seed": a.seed, "N": a.N, "started": started, "ctx_before": before}

    # ---- Phase A ----
    gate = None
    if a.phase in ("gate", "both"):
        rows = []
        for label, expect in (("CONTRADICT", 0.0), ("SUPPORT", 1.0)):
            for p in native_pairs(corpus, claims, label, a.gate_n, rng):
                for ev_kind, ev in (("cited_sentences", " ".join(p["evidence_sentences"])), ("full_abstract", " ".join(p["abstract"]))):
                    s, raw, ms = judge.score(ev, p["claim"])
                    rows.append({"label": label, "expect": expect, "evidence": ev_kind, "score": s, "raw": raw, "ms": ms,
                                 "claim_id": p["claim_id"], "doc_id": p["doc_id"], "hit": s == expect})
                    print(f"  [gate] {label:10s} {ev_kind:15s} score={s} raw={raw!r} {'✓' if s == expect else '✗'}")
        def rate(lbl, ev): v = [r["hit"] for r in rows if r["label"] == lbl and r["evidence"] == ev]; return sum(v) / len(v) if v else None
        gate = {"rows": rows, "contradict_low_rate": {ev: rate("CONTRADICT", ev) for ev in ("cited_sentences", "full_abstract")},
                "support_high_rate": {ev: rate("SUPPORT", ev) for ev in ("cited_sentences", "full_abstract")},
                "unparsed_raw": sum(1 for r in rows if not (r["raw"] or "").strip().lower().split(" ")[:1] or (r["raw"] or "").strip().lower().split()[0].strip('".,') not in ("yes", "no"))}
        c_ok = (gate["contradict_low_rate"]["cited_sentences"] or 0) >= 0.7; s_ok = (gate["support_high_rate"]["cited_sentences"] or 0) >= 0.7
        gate["passed"] = bool(c_ok and s_ok)
        gate["criterion"] = "cited_sentences 下 CONTRADICT 得 0 的比例 ≥ 0.7 且 SUPPORT 得 1 的比例 ≥ 0.7（兩者缺一 ⇒ parser 或方向壞 ⇒ 停）"
        json.dump({"meta": meta, "gate": gate}, open(os.path.join(a.out_dir, "phaseA_gate.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"[gate] CONTRADICT low-rate {gate['contradict_low_rate']} · SUPPORT high-rate {gate['support_high_rate']} · unparsed {gate['unparsed_raw']} · PASSED={gate['passed']}")
        if not gate["passed"]:
            print("🔴 校準閘未過 ⇒ 停，不跑主掃描"); sys.exit(2)

    # ---- Phase B ----
    if a.phase in ("scan", "both"):
        docs = [d for d in corpus.values() if len(d["abstract"]) >= a.N and all(len(s) > 20 for s in d["abstract"][:a.N])]
        rng2 = random.Random(a.seed + 1); rng2.shuffle(docs); docs = docs[:a.docs]
        items = []; methods = ["numeric", "invert", "misattrib"]
        for k in range(0, a.N + 1):
            for di, d in enumerate(docs):
                sents = list(d["abstract"][:a.N]); r = random.Random(a.seed * 1000 + k * 100 + di)
                pos = sorted(r.sample(range(a.N), k)); applied = []
                for j, idx in enumerate(pos):
                    new, tag = pollute(sents[idx], idx, methods[(di + j) % 3], corpus, d["doc_id"], r)
                    sents[idx] = new; applied.append({"idx": idx, "tag": tag})
                answer = " ".join(sents); evidence = " ".join(d["abstract"])
                s, raw, ms = judge.score(evidence, answer)
                items.append({"k": k, "doc_id": d["doc_id"], "score": s, "raw": raw, "ms": ms, "polluted": applied, "answer": answer})
            ks = [i for i in items if i["k"] == k]
            print(f"  [scan] k={k}: mean score {sum(i['score'] for i in ks)/len(ks):.2f} · grounded {sum(1 for i in ks if i['score']==1.0)}/{len(ks)}")
        curve = {}
        for k in range(0, a.N + 1):
            ks = [i for i in items if i["k"] == k]; g = sum(1 for i in ks if i["score"] == 1.0)
            curve[k] = {"n": len(ks), "mean_score": round(sum(i["score"] for i in ks) / len(ks), 3), "grounded_rate": round(g / len(ks), 3),
                        "detection_rate": None if k == 0 else round(1 - g / len(ks), 3), "false_alarm_rate": round(1 - g / len(ks), 3) if k == 0 else None}
        bym = {}
        for i in items:
            for p in i["polluted"]:
                m = (p["tag"] or "none").split(":")[0]; bym.setdefault(m, [0, 0]); bym[m][1] += 1; bym[m][0] += (i["score"] == 0.0)
        after = ctx(); kp = kernel_path(a.container)
        res = {"meta": meta, "curve": curve, "k1_detection_rate": curve[1]["detection_rate"], "k5_positive_control": curve[a.N],
               "detection_by_method_any_k": {m: {"detected": v[0], "total": v[1]} for m, v in bym.items()},
               "docs": len(docs), "measurement_context": {"before": before, "after": after}, "kernel": kp,
               "clean_window_prelaunch_note": "see the ctx_before file in the output directory", "finished": datetime.datetime.now().astimezone().isoformat(timespec="seconds")}
        res["measurement_label"] = (f"self_check_facts · judge {meta['judge_model']} · NIM 1.13.1 · Guardrails {meta['guardrails_version']} · "
            f"SciFact abstracts（evidence=完整 abstract，⛔ 無檢索器）· N={a.N} 句 · k=0..{a.N} · 每格 n={len(docs)} · 污染由程式（numeric/invert/misattrib 輪替）· "
            f"seed {a.seed} · 校準閘 A 已過 · k1 偵測率 {curve[1]['detection_rate']} · k0 誤報率 {curve[0]['false_alarm_rate']} · k{a.N} 偵測率 {curve[a.N]['detection_rate']}")
        json.dump(res, open(os.path.join(a.out_dir, "phaseB_scan.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        with open(os.path.join(a.out_dir, "phaseB_items.raw.jsonl"), "w", encoding="utf-8") as f:
            for i in items: f.write(json.dumps(i, ensure_ascii=False) + "\n")
        print(res["measurement_label"])

if __name__ == "__main__":
    main()
