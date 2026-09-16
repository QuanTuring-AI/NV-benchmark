#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
reranker 評測 harness（公開資料集版）

這支的唯一變數是 **reranker 的有無**。第一階段檢索固定，不做任何調校。

🔴 紅線
--------------------------------------------------------------------
* **只吃公開資料集**。非公開資料不由本檔讀取。
  這條不是靠記性 —— `--dataset` 只接受下方 PUBLIC 註冊表裡的名字，
  要用別的路徑必須明確加 `--i-confirm-dataset-is-public`，且該路徑會被寫進輸出 JSON。
* **不含任何調校參數**：只有 top-K1 / top-K2 這種介面層參數。
* reranker 用**公開模型**，不用任何微調權重。

🔴 陽性對照 —— 這支存在的核心理由
--------------------------------------------------------------------
「加了 reranker 沒有提升」在沒有陽性對照時，**無法區分**：
  (a) reranker 真的沒用
  (b) 這支 harness 根本測不出差異
所以 `--positive-control shuffle` 會把第一階段的 top-K1 **順序打亂**，
此時 reranker **必須**把指標拉回來。拉不回來 → harness 壞了，
輸出的 `status` 會標成 **invalid**，該次數字不得寫進任何報告。

⚠️ 打亂序那一輪是**真的重跑一次 reranker**，不是重用同一份分數。
   重用 = 恆真式 = 永遠通過 = 沒有檢查力。

關於 `--runs` 與信賴區間（與工單字面的一處差異，已在回報中說明）
--------------------------------------------------------------------
固定 seed 下，檢索與 rerank 都是**決定性**的 —— 跑 5 次得到 5 個一模一樣的品質數字，
拿它們算出來的區間寬度是 **0**，那是假的。所以：
  * `--runs N` 真的跑 N 次，但它量的是**延遲分布**，並且充當**決定性檢查**
    （品質若在跑次之間漂移 = 有非決定性來源，必須先解釋再談結論）
  * 品質的 `ci95` 一律**對題目取**：比例型指標用 Wilson，非比例型（MRR / nDCG）用 bootstrap

用法
----
    python scripts/bench_reranker.py --dataset scifact \
        --reranker BAAI/bge-reranker-v2-m3 \
        --topk-first-stage 50 --topk-final 5 --runs 5 \
        --positive-control shuffle \
        --out results/e8/scifact_bge-reranker-v2-m3.json
"""

from __future__ import annotations

import argparse
import json
import platform
import time
from pathlib import Path

import numpy as np

# ── stdout 編碼防呆（Windows cp950 會在工作完成後才炸，害離開碼變 1）──────
import sys as _sys
try:
    _sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


# ─────────────────────────────────────────────────────────────────────
# 公開資料集註冊表 —— BEIR 格式（corpus.jsonl / queries.jsonl / qrels/<split>.tsv）
# 全部是 HuggingFace 上的公開 dataset repo，無授權疑慮，可在平台上直接下載。
# ─────────────────────────────────────────────────────────────────────
PUBLIC = {
    "scifact":    dict(repo="mteb/scifact",    n_docs=5183,   note="科學論斷驗證 · 小 · 適合冒煙"),
    "nfcorpus":   dict(repo="mteb/nfcorpus",   n_docs=3633,   note="醫療資訊檢索 · 小"),
    "fiqa":       dict(repo="mteb/fiqa",       n_docs=57638,  note="金融問答 · 中"),
    "trec-covid": dict(repo="mteb/trec-covid", n_docs=171332, note="COVID 文獻 · 大"),
}


def load_beir(name: str, split: str, allow_local: bool) -> tuple:
    """回傳 (docs, queries, qrels, source_desc)。docs/queries 為 list[dict]。"""
    if name in PUBLIC:
        from huggingface_hub import hf_hub_download
        repo = PUBLIC[name]["repo"]
        get = lambda f: hf_hub_download(repo, f, repo_type="dataset")
        corpus_p, queries_p = get("corpus.jsonl"), get("queries.jsonl")
        qrels_p = get(f"qrels/{split}.tsv")
        source = f"HuggingFace dataset {repo} (public) · split={split}"
    else:
        if not allow_local:
            raise SystemExit(
                f"❌ '{name}' 不在公開資料集註冊表中：{sorted(PUBLIC)}\n"
                "   本 harness 預設拒絕非註冊路徑（只吃公開資料集）。\n"
                "   確定該路徑是公開資料集才加 --i-confirm-dataset-is-public。")
        d = Path(name)
        corpus_p, queries_p = d / "corpus.jsonl", d / "queries.jsonl"
        qrels_p = d / "qrels" / f"{split}.tsv"
        source = f"local path {d} (使用者自行聲明為公開) · split={split}"

    docs = [json.loads(l) for l in Path(corpus_p).open(encoding="utf-8")]
    queries = [json.loads(l) for l in Path(queries_p).open(encoding="utf-8")]

    qrels: dict = {}
    with Path(qrels_p).open(encoding="utf-8") as fh:
        header = fh.readline()          # query-id  corpus-id  score
        if "query-id" not in header:
            fh.seek(0)
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 3:
                continue
            qid, did, score = parts[0], parts[1], int(parts[2])
            if score > 0:
                qrels.setdefault(qid, {})[did] = score
    return docs, queries, qrels, source


# ── 指標 ──────────────────────────────────────────────────────────────
def hit_at_k(ranked: list, rel: dict, k: int) -> float:
    return 1.0 if any(d in rel for d in ranked[:k]) else 0.0


def rr(ranked: list, rel: dict) -> float:
    for i, d in enumerate(ranked, 1):
        if d in rel:
            return 1.0 / i
    return 0.0


def ndcg_at_k(ranked: list, rel: dict, k: int) -> float:
    dcg = sum(rel.get(d, 0) / np.log2(i + 1) for i, d in enumerate(ranked[:k], 1))
    ideal = sorted(rel.values(), reverse=True)[:k]
    idcg = sum(g / np.log2(i + 1) for i, g in enumerate(ideal, 1))
    return float(dcg / idcg) if idcg > 0 else 0.0


def wilson(p: float, n: int, z: float = 1.96) -> list:
    if n == 0:
        return [0.0, 0.0]
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5)
    return [(c - m) / d, (c + m) / d]


def boot_ci(vals: list, seed: int, iters: int = 2000) -> list:
    """非比例型指標（MRR / nDCG）的 95% bootstrap 百分位區間。對題目重抽。"""
    a = np.asarray(vals, dtype=float)
    if len(a) == 0:
        return [0.0, 0.0]
    rng = np.random.default_rng(seed)
    means = a[rng.integers(0, len(a), size=(iters, len(a)))].mean(axis=1)
    return [float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))]


def pctl(xs: list, q: float) -> float:
    return float(np.percentile(np.asarray(xs, dtype=float), q)) if xs else 0.0


def load_env(snapshot: str | None) -> dict:
    """優先吃 verify_env.py 的快照；沒有就現場抓，並誠實標明來源。"""
    if snapshot and Path(snapshot).exists():
        snap = json.loads(Path(snapshot).read_text(encoding="utf-8"))
        keep = ("torch_version", "torch", "cuda_available",
                "device_name", "device_count", "vram_gb", "python", "host")
        env = {k: snap[k] for k in keep if k in snap}
        env["source"] = f"verify_env.py snapshot: {snapshot}"
        return env
    import torch
    env = dict(
        torch_version=torch.__version__,
        cuda_available=bool(torch.cuda.is_available()),
        python=platform.python_version(),
        host=platform.platform(),
        source=("live capture —— 沒有給 --env-snapshot，"
                "環境未經 verify_env.py 驗證，請勿把此數字當成受控環境下的結果"),
    )
    if torch.cuda.is_available():
        env["device_name"] = torch.cuda.get_device_name(0)
        env["device_count"] = torch.cuda.device_count()
        env["vram_gb"] = round(
            torch.cuda.get_device_properties(0).total_memory / 1024 ** 3, 1)
    return env


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="scifact",
                    help=f"公開資料集名稱 {sorted(PUBLIC)} 或 BEIR 格式目錄")
    ap.add_argument("--split", default="test")
    ap.add_argument("--i-confirm-dataset-is-public", action="store_true",
                    dest="allow_local",
                    help="使用註冊表以外的路徑時必須明示（紅線防呆）")
    ap.add_argument("--dense", default="sentence-transformers/all-MiniLM-L6-v2",
                    help="第一階段檢索模型（公開模型；本 harness 不調校它）")
    ap.add_argument("--reranker", default="BAAI/bge-reranker-v2-m3")
    ap.add_argument("--device", default=None)
    ap.add_argument("--fp16", action="store_true",
                    help="reranker 以 fp16 推論（快很多，但近似分數的排序可能不同，會記進 label）")
    ap.add_argument("--batch-size", type=int, default=64)
    ap.add_argument("--rerank-batch-size", type=int, default=50)
    ap.add_argument("--max-length", type=int, default=512)
    ap.add_argument("--topk-first-stage", type=int, default=50)
    ap.add_argument("--topk-final", type=int, default=5)
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--positive-control", choices=["shuffle", "none"], default="shuffle")
    ap.add_argument("--query-prefix", default="",
                    help='E5 系列第一階段請用 "query: "')
    ap.add_argument("--passage-prefix", default="",
                    help='E5 系列第一階段請用 "passage: "')
    ap.add_argument("--max-queries", type=int, default=0,
                    help="只跑前 N 題（冒煙用）。非 0 時會寫進量測邊界，不會被藏起來")
    ap.add_argument("--env-snapshot", default=None, help="optional environment snapshot JSON; when omitted the label records the live environment only")
    ap.add_argument("--out", default="results/e8/bench.json")
    ap.add_argument("--seed", type=int, default=1508)
    a = ap.parse_args()

    from sentence_transformers import SentenceTransformer, CrossEncoder
    import torch

    K1, K2 = a.topk_first_stage, a.topk_final
    dev = a.device or ("cuda" if torch.cuda.is_available() else "cpu")

    docs, queries, qrels, source = load_beir(a.dataset, a.split, a.allow_local)
    qs = [q for q in queries if q["_id"] in qrels]          # 只留有標註的題
    qs.sort(key=lambda q: q["_id"])
    if a.max_queries:
        qs = qs[:a.max_queries]
    doc_ids = [d["_id"] for d in docs]
    doc_txt = [(d.get("title", "") + " " + d.get("text", "")).strip() for d in docs]
    print(f"dataset={a.dataset}  docs={len(docs)}  queries(with qrels)={len(qs)}")

    # ── 第一階段（固定，不調校）─────────────────────────────────────
    # 🔴 用法閘：controls/status 證明的是「harness 沒壞」，
    #    證明不了「模型被正確使用」——兩者都通過才是 citable。
    usage_issues: list = []
    if "e5" in a.dense.lower() and not (a.query_prefix or a.passage_prefix):
        usage_issues.append(
            "E5 prefix missing on first stage (--query-prefix / --passage-prefix): "
            "tested outside its designed usage; not comparable across models.")
    for _m in usage_issues:
        print(f"[usage-warning] {_m}")
    usage_valid = not usage_issues

    dense = SentenceTransformer(a.dense, device=dev)
    D = dense.encode([a.passage_prefix + t for t in doc_txt], batch_size=a.batch_size,
                     normalize_embeddings=True,
                     show_progress_bar=False, convert_to_numpy=True)
    Q = dense.encode([a.query_prefix + q["text"] for q in qs], batch_size=a.batch_size,
                     normalize_embeddings=True, show_progress_bar=False,
                     convert_to_numpy=True)

    ce = CrossEncoder(a.reranker, device=dev, max_length=a.max_length)
    if a.fp16:
        ce.model.half()

    def dense_stage():
        """回傳 (每題 top-K1 的 doc index, 每題耗時 ms)。逐題計時 = 單題延遲。"""
        cands, lat = [], []
        for i in range(len(qs)):
            if dev == "cuda":
                torch.cuda.synchronize()
            t0 = time.perf_counter()
            s = Q[i] @ D.T
            top = np.argpartition(-s, K1)[:K1]
            top = top[np.argsort(-s[top])]
            if dev == "cuda":
                torch.cuda.synchronize()
            lat.append((time.perf_counter() - t0) * 1000.0)
            cands.append(top)
        return cands, lat

    def rerank_stage(cands):
        """回傳 (每題重排後的 doc index 序, 每題 rerank 階段耗時 ms)。"""
        orders, lat = [], []
        for i, q in enumerate(qs):
            ids = list(cands[i])
            pairs = [(q["text"], doc_txt[j]) for j in ids]
            if dev == "cuda":
                torch.cuda.synchronize()
            t0 = time.perf_counter()
            sc = ce.predict(pairs, batch_size=a.rerank_batch_size,
                            show_progress_bar=False)
            if dev == "cuda":
                torch.cuda.synchronize()
            lat.append((time.perf_counter() - t0) * 1000.0)
            orders.append([ids[k] for k in np.argsort(-np.asarray(sc), kind="stable")])
        return orders, lat

    def score(order_rows) -> dict:
        """逐題指標，回傳三個 list（供 CI 與平均使用）。"""
        h, m, n = [], [], []
        for i, q in enumerate(qs):
            rel = qrels[q["_id"]]
            ranked = [doc_ids[j] for j in order_rows[i]]
            h.append(hit_at_k(ranked, rel, K2))
            m.append(rr(ranked, rel))
            n.append(ndcg_at_k(ranked, rel, K2))
        return dict(hit=h, mrr=m, ndcg=n)

    # ── 主體：跑 N 次 ────────────────────────────────────────────────
    per_run, lat_dense_all, lat_rr_all = [], [], []
    base_last = rr_last = None
    for r in range(a.runs):
        cands, ld = dense_stage()
        orders, lr = rerank_stage(cands)
        base, rrk = score(cands), score(orders)
        per_run.append(dict(
            run=r + 1,
            baseline=dict(hit_at_5=float(np.mean(base["hit"])),
                          mrr=float(np.mean(base["mrr"])),
                          ndcg_at_5=float(np.mean(base["ndcg"]))),
            reranked=dict(hit_at_5=float(np.mean(rrk["hit"])),
                          mrr=float(np.mean(rrk["mrr"])),
                          ndcg_at_5=float(np.mean(rrk["ndcg"]))),
            rerank_p50_ms=pctl(lr, 50), rerank_p95_ms=pctl(lr, 95),
        ))
        lat_dense_all += ld
        lat_rr_all += lr
        base_last, rr_last, cands_last = base, rrk, cands
        print(f"  run {r+1}/{a.runs}  baseline hit@{K2}={np.mean(base['hit'])*100:.1f}%  "
              f"reranked hit@{K2}={np.mean(rrk['hit'])*100:.1f}%  "
              f"rerank p50={pctl(lr,50):.0f}ms")

    # 決定性檢查：品質在跑次之間必須完全一致
    q_keys = [(p["baseline"]["hit_at_5"], p["reranked"]["hit_at_5"],
               p["baseline"]["mrr"], p["reranked"]["mrr"]) for p in per_run]
    deterministic = all(k == q_keys[0] for k in q_keys)

    recall_k1 = float(np.mean([
        1.0 if any(doc_ids[j] in qrels[q["_id"]] for j in cands_last[i]) else 0.0
        for i, q in enumerate(qs)]))

    # ── 陽性對照 ─────────────────────────────────────────────────────
    pc: dict = {"mode": a.positive_control}
    if a.positive_control == "shuffle":
        rng = np.random.default_rng(a.seed)
        cands_shuf = [rng.permutation(np.asarray(c)) for c in cands_last]
        shuf = score(cands_shuf)
        orders_shuf, _ = rerank_stage(cands_shuf)      # 🔴 真的重跑，不重用分數
        rr_shuf = score(orders_shuf)
        # oracle：把一個相關文件放到第一名 → hit@K2 必須 = 100%（計分邏輯自檢）
        oracle_rows = []
        for i, q in enumerate(qs):
            rel = set(qrels[q["_id"]])
            gold = next((j for j in range(len(doc_ids)) if doc_ids[j] in rel), None)
            row = list(cands_last[i])
            if gold is not None:
                row = [gold] + [x for x in row if x != gold]
            oracle_rows.append(row)
        oracle = score(oracle_rows)

        chance = K2 / K1
        b_hit = float(np.mean(base_last["hit"]))
        s_hit = float(np.mean(shuf["hit"]))
        rs_hit = float(np.mean(rr_shuf["hit"]))
        r_hit = float(np.mean(rr_last["hit"]))
        pc["checks"] = {
            "oracle_perfect": abs(float(np.mean(oracle["hit"])) - 1.0) < 1e-9,
            "shuffled_collapsed": s_hit <= chance * 2,
            "rerank_recovers_shuffled": rs_hit > s_hit * 3,
            "order_invariant": abs(r_hit - rs_hit) <= 0.01,
        }
        pc["numbers"] = dict(
            baseline_hit_at_5=b_hit, shuffled_hit_at_5=s_hit,
            reranked_from_shuffled_hit_at_5=rs_hit, reranked_hit_at_5=r_hit,
            oracle_hit_at_5=float(np.mean(oracle["hit"])), chance_level=chance)
        pc["note"] = ("打亂序那一輪是重新跑一次 reranker，不是重用分數 —— "
                      "重用會讓 order_invariant 變成恆真式。")
    else:
        pc["checks"] = {}
        pc["note"] = ("🔴 --positive-control none：本次沒有陽性對照。"
                      "任何『reranker 沒有提升』的陰性結論在此模式下不成立。")
    pc["passed"] = bool(pc["checks"]) and all(pc["checks"].values())

    status = "valid" if (pc["passed"] and usage_valid) else "invalid"

    # ── 彙整 ─────────────────────────────────────────────────────────
    mean = lambda xs: float(np.mean(xs))
    n_q = len(qs)
    out = dict(
        measurement_label="",           # 下面填
        status=status,
        citable=(status == "valid"),
        controls_ok=pc["passed"],
        usage_valid=usage_valid, usage_issues=usage_issues,
        query_prefix=a.query_prefix, passage_prefix=a.passage_prefix,
        dataset=dict(name=a.dataset, source=source, split=a.split,
                     n_docs=len(docs), n_queries=n_q,
                     is_public_registry=a.dataset in PUBLIC,
                     max_queries_cap=a.max_queries or None),
        models=dict(first_stage=a.dense, reranker=a.reranker,
                    reranker_dtype="fp16" if a.fp16 else "fp32"),
        config=dict(topk_first_stage=K1, topk_final=K2, max_length=a.max_length,
                    rerank_batch_size=a.rerank_batch_size, seed=a.seed,
                    l3_tuning="none —— 本 harness 不含任何調校參數"),
        recall_at_first_stage=recall_k1,
        hit_at_5=dict(baseline=mean(base_last["hit"]), reranked=mean(rr_last["hit"]),
                      delta=mean(rr_last["hit"]) - mean(base_last["hit"])),
        mrr=dict(baseline=mean(base_last["mrr"]), reranked=mean(rr_last["mrr"]),
                 delta=mean(rr_last["mrr"]) - mean(base_last["mrr"])),
        ndcg_at_5=dict(baseline=mean(base_last["ndcg"]), reranked=mean(rr_last["ndcg"]),
                       delta=mean(rr_last["ndcg"]) - mean(base_last["ndcg"])),
        ci95=dict(
            hit_at_5=dict(baseline=wilson(mean(base_last["hit"]), n_q),
                          reranked=wilson(mean(rr_last["hit"]), n_q)),
            mrr=dict(baseline=boot_ci(base_last["mrr"], a.seed),
                     reranked=boot_ci(rr_last["mrr"], a.seed)),
            ndcg_at_5=dict(baseline=boot_ci(base_last["ndcg"], a.seed),
                           reranked=boot_ci(rr_last["ndcg"], a.seed)),
            method=("hit@5 = Wilson（比例型，n = 題數）· MRR / nDCG@5 = bootstrap 百分位"
                    "（2000 次，對題目重抽）。🔴 不是對 runs 取區間 —— 固定 seed 下"
                    "品質是決定性的，跑次之間的離散度是 0，拿它算區間會得到假的 0 寬度。"),
        ),
        positive_control=pc,
        latency_ms=dict(
            rerank_stage=dict(p50=pctl(lat_rr_all, 50), p95=pctl(lat_rr_all, 95),
                              p99=pctl(lat_rr_all, 99), mean=mean(lat_rr_all),
                              n=len(lat_rr_all)),
            dense_stage=dict(p50=pctl(lat_dense_all, 50), p95=pctl(lat_dense_all, 95),
                             mean=mean(lat_dense_all), n=len(lat_dense_all)),
            note=(f"rerank_stage = 加上 reranker 所**額外**付出的延遲（每題 {K1} pairs，"
                  "含 CUDA 同步）。dense_stage 為第一階段本身。兩者皆為單題延遲，"
                  "不是批次吞吐 —— 兩種數字不可互換引用。"),
        ),
        runs=dict(n=a.runs, quality_deterministic=deterministic, per_run=per_run,
                  note=("runs 量的是延遲分布並充當決定性檢查；"
                        "quality_deterministic=false 代表有非決定性來源，需先解釋再談結論。")),
        env=load_env(a.env_snapshot),
    )

    out["measurement_label"] = (
        f"{a.dataset} ({source}) · {n_q}Q / {len(docs)} docs · "
        f"first stage={a.dense} · reranker={a.reranker} ({out['models']['reranker_dtype']}) · "
        f"top-{K1} -> top-{K2} · max_len={a.max_length} · device={dev} · runs={a.runs} · "
        f"Hit@{K2} {out['hit_at_5']['baseline']*100:.1f}% -> {out['hit_at_5']['reranked']*100:.1f}% "
        f"(Wilson 95% CI {out['ci95']['hit_at_5']['reranked'][0]*100:.1f}–"
        f"{out['ci95']['hit_at_5']['reranked'][1]*100:.1f}%) · "
        f"nDCG@{K2} {out['ndcg_at_5']['baseline']:.3f} -> {out['ndcg_at_5']['reranked']:.3f} · "
        f"rerank 額外延遲 p50={out['latency_ms']['rerank_stage']['p50']:.1f}ms "
        f"p95={out['latency_ms']['rerank_stage']['p95']:.1f}ms · "
        f"陽性對照({a.positive_control}) {'通過' if pc['passed'] else '未通過'} · "
        f"status={status}"
        + (f" · ⚠️ 只跑前 {a.max_queries} 題" if a.max_queries else ""))

    outp = Path(a.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print()
    print(f"  recall@{K1}（第一階段天花板）= {recall_k1*100:.1f}%")
    for m in ("hit_at_5", "mrr", "ndcg_at_5"):
        v = out[m]
        lo, hi = out["ci95"][m]["reranked"]
        print(f"  {m:10s} baseline={v['baseline']:.4f}  reranked={v['reranked']:.4f}  "
              f"Δ={v['delta']:+.4f}   [reranked 95% CI {lo:.4f}–{hi:.4f}]")
    L = out["latency_ms"]
    print(f"  rerank 額外延遲  p50={L['rerank_stage']['p50']:.1f}ms  "
          f"p95={L['rerank_stage']['p95']:.1f}ms   "
          f"(dense 階段 p50={L['dense_stage']['p50']:.1f}ms)")
    print(f"  跑次品質決定性：{'一致' if deterministic else '🔴 不一致'}")
    print("  ── 陽性對照 ──")
    for k, v in pc["checks"].items():
        print(f"    {'[ok]  ' if v else '[FAIL]'} {k}")
    if pc.get("numbers"):
        n = pc["numbers"]
        print(f"    baseline {n['baseline_hit_at_5']*100:.1f}% → 打亂 "
              f"{n['shuffled_hit_at_5']*100:.1f}% → rerank 拉回 "
              f"{n['reranked_from_shuffled_hit_at_5']*100:.1f}%  "
              f"(隨機水準 {n['chance_level']*100:.1f}%)")
    print(f"    {'[ok]  ' if usage_valid else '[FAIL]'} usage_valid")
    print(f"status={status}  citable={str(out['citable']).lower()}")
    print(f"量測邊界：{out['measurement_label']}")
    print(f"→ {outp}")
    return 0 if status == "valid" else 1


if __name__ == "__main__":
    raise SystemExit(main())
