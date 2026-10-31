#!/usr/bin/env python3
"""Vol.4 · writes an addendum to the pre-registration of the whole-corpus cells, with its .sha256 file: a second
reranking NIM on the same whole-corpus results (cell D2), and timed passes of the reference arm on the reduced MIRACL ja
corpus with a smaller batch. The frozen file is not changed; the programs are the bound ones. Run once, before the
first container of these cells. usage: gen_addendum_second_reranker.py
"""
import hashlib, json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__)); VOL = os.path.dirname(HERE)
RES = os.path.join(VOL, "results", "whole_corpus_quality"); OUT = os.path.join(RES, "addendum_second_reranker.json")


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def load(*parts):
    return json.load(open(os.path.join(VOL, "results", *parts), encoding="utf-8"))


first = json.load(open(os.path.join(VOL, "results", "first_batch", "prediction_first_batch.json"), encoding="utf-8"))
arm = "rerank_llama-nemotron-rerank-500m-v2_auto"
reduced = {d: {"after": load("first_batch", arm, d, "score_after.json")["metrics"]["ndcg_cut_10"], "pairs_per_s": load("first_batch", arm, d, "throughput.json")["pairs_per_s_median"]} for d in ("miracl-hn-zh", "miracl-hn-ja")}
whole = {l: {"before": load("whole_corpus_quality", "whole_corpus", f"miracl-{l}", "score.json")["metrics"],
             "after_with_the_1b_reranker": load("whole_corpus_quality", "rerank_llama-nemotron-rerank-1b-v2", f"miracl-{l}", "score_after.json")["metrics"]["ndcg_cut_10"]} for l in ("zh", "ja")}
if os.path.exists(OUT):
    sys.exit("refused: the addendum exists")
A = {
 "what": "Addendum to prediction_whole_corpus.json: cell D2 (a second reranking NIM on the whole-corpus results) and timed passes of the reference arm on miracl-hn-ja",
 "written_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
 "supplements": {"file": "prediction_whole_corpus.json", "sha256": sha(os.path.join(RES, "prediction_whole_corpus.json"))},
 "host": "one RTX 5090, graphics driver 610.88 (as cells D and E of 2026-10-06)",
 "cell_D2": {
  "what": "cell D again with the other reranking NIM of the first session: the 100 whole-corpus results per query of cell B, one call per query",
  "image": "nvcr.io/nim/nvidia/llama-nemotron-rerank-500m-v2:1.10.0", "image_digest_recorded_by_the_first_session": first["P3_reranking"]["images"]["llama-nemotron-rerank-500m-v2"]["image_digest"],
  "start": "as in the first session: no profile set", "programs": "as cell D: rerank_cell.py (smoke, rerank), score_run.py --rerank-from, rerank_latency.py --where container --passes 2; the driver and its limits are those of cell D",
  "reported": "per language nDCG@10 before and after, Recall@100 before and after (must be equal), and per pass the p50 / p90 / p99 of a call; in one table with cell D, each reranker's own values side by side "
              "(no per-query result of one reranker is read together with the other's)",
  "known_before": {"this reranker on the reduced corpora (first session)": reduced, "whole corpus": whole},
  "expectation": {"ndcg": "rises on both languages, by less than with the 1b reranker: +0.005 to +0.02 (on the reduced corpora it added 0.011 for zh and 0.008 for ja, the 1b reranker 0.024 and 0.028)",
                  "recall_100": "equal before and after", "call_ms_p50": "75 to 110 ms (zh) and 80 to 115 ms (ja), from the first session's 1,120 and 1,040 pairs per second; p99 below 400 ms; the second pass within 5% of the first"}},
 "reference_arm_ja_throughput": {
  "what": "the open weights through Sentence Transformers (the reference arm of the first session) on the first 4,096 passages of miracl-hn-ja, three timed passes after one discarded pass",
  "why": "the first session has no timed passes for this arm on ja: at 64 per batch the step filled the card's memory (Sentence Transformers puts the longest passages of the sample into one batch) and was stopped",
  "command": "scripts/embed_cell.py throughput --backend st --dataset miracl-hn-ja --batch 16 --n 4096 --reps 3", "limit_s": 600,
  "note": "batch 16 is the batch this arm encoded the ja corpus with. Its zh figure (368.7) was timed at 64 per batch and the NIM cells send 64 passages per request, so this figure is not set beside either as a comparison of speed",
  "expectation": "it completes; between 200 and 350 passages per second (the untimed encoding of the whole reduced ja corpus at batch 16 ran at about 254). If it does not complete within the limit, that is written as it happened."},
 "not_in_this_file": "the HotpotQA whole-corpus cells: they get their own addendum before their first container",
}
json.dump(A, open(OUT, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
open(os.path.splitext(OUT)[0] + ".sha256", "w", encoding="utf-8", newline="\n").write(f"{sha(OUT)} *{os.path.basename(OUT)}\n")
print("written", A["written_at"], sha(OUT))
