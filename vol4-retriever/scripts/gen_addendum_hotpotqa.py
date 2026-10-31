#!/usr/bin/env python3
"""Vol.4 · writes the addendum to the pre-registration of the whole-corpus cells for BEIR HotpotQA (cell H: every
passage encoded, exact search, the two metrics; cell H-R: the 1b reranker on its results), with its .sha256 file.
Run once, before the first container of cell H. usage: gen_addendum_hotpotqa.py --counts COUNTS.json --n3-digest sha256:... [--draft]
       COUNTS.json: the counts file written when the data set was fetched (outside the repository)
"""
import hashlib, json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__)); VOL = os.path.dirname(HERE)
RES = os.path.join(VOL, "results", "whole_corpus_quality"); OUT = os.path.join(RES, "addendum_hotpotqa.json"); DRAFT = "--draft" in sys.argv
C = json.load(open(sys.argv[sys.argv.index("--counts") + 1], encoding="utf-8"))


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def load(*parts):
    return json.load(open(os.path.join(VOL, "results", *parts), encoding="utf-8"))


N3 = sys.argv[sys.argv.index("--n3-digest") + 1]
if not (N3.startswith("sha256:") and len(N3) == 71):
    sys.exit("give --n3-digest as sha256:<64 hex>")
known = {l: {**{k: load("whole_corpus_quality", "whole_corpus", f"miracl-{l}", "score.json")["metrics"][k] for k in ("ndcg_cut_10", "recall_100")},
             "after_the_1b_reranker": load("whole_corpus_quality", "rerank_llama-nemotron-rerank-1b-v2", f"miracl-{l}", "score_after.json")["metrics"]["ndcg_cut_10"]} for l in ("zh", "ja")}
BOUND = ["encode_corpus_resumable.py", "search_whole_corpus.py", "retrieval_datasets.py", "retrieval_metrics.py", "nim_retrieval_clients.py", "rerank_cell.py", "score_run.py", "run_step.py", "session_step.py"]
A = {
 "what": "Addendum to prediction_whole_corpus.json: BEIR HotpotQA, every passage encoded with the embedding NIM and searched exactly (cell H), and the 1b reranker on its results (cell H-R)",
 "draft": DRAFT, "written_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
 "supplements": {"file": "prediction_whole_corpus.json", "sha256": sha(os.path.join(RES, "prediction_whole_corpus.json"))},
 "why": "the two whole-corpus figures of this volume are Chinese and Japanese; this adds one English corpus of the same order of size, in its usual public packaging",
 "data": {"data_set": "HotpotQA in the BEIR packaging", "zip_sha256": C["zip_sha256"], "zip_md5_equals_the_one_in_the_beir_readme": C["md5_matches"], "corpus_passages": C["corpus_rows"],
          "split": "test", "queries_with_a_judgement": C["queries_with_a_judgement"]["test"], "judgements": C["qrels_rows_without_header"]["test"], "fetched_at": C["fetched_at"]},
 "cell_H": {
  "encoding": {"image": "nvcr.io/nim/nvidia/nemotron-3-embed-1b:2.2.2", "started": "as for the two MIRACL corpora: NIM_ENGINE_PRECISION=fp16, the model files of the image's own download mounted",
               "image_digest": N3,
               "program": "encode_corpus_resumable.py --dataset beir-hotpotqa --piece 100000 --batch 64 --dim 2048 --stop-at <08:00 +0800 of the next morning>",
               "passage_text": "as the data-set reader gives it for BEIR (title, one space, text: retrieval_datasets.passage_text), input_type passage; queries input_type query; no prefix added by the client",
               "night_only": "the encoding runs in a night stretch and stops by itself at 08:00; if the corpus is not finished, a later night continues from the last checkpoint",
               "checkpoints": "results/hotpotqa_whole_corpus/full_corpus/beir-hotpotqa/checkpoints.jsonl (counts, seconds, SHA-256; no text); the vectors stay outside the repository",
               "not_a_speed_figure": "the seconds of a piece are recorded and are not a throughput figure"},
  "search": {"program": "search_whole_corpus.py --dataset beir-hotpotqa --checkpoints ... --top 100 (cosine, exact, one piece in memory at a time)", "metrics": "nDCG@10 and Recall@100 on the test queries, by retrieval_metrics.py", "timeout_s": 3600},
  "controls": {
   "A_H (the search and the metric on this data set, computed a second way)": "the same search restricted to a fixed subset of the corpus (every passage with a test judgement and the first 100,000 passages of the file) is computed twice: "
        "by search_whole_corpus.py with its restricted mode, and by a separate short program that loads the subset's vectors into one matrix and ranks with one matrix product. nDCG@10 and Recall@100 must agree to five decimals.",
   "C_H (ids and vectors belong together)": "after the encoding, 1,000 passages spread evenly over the file are encoded again in one new request stream and compared with the stored rows found by their ids: every cosine must be at least 0.999.",
   "already_shown_for_the_programs": "the encoder against the first session's vectors (results/second_batch/full_corpus/program_check/), the search program on four reduced-corpus runs and on two restricted whole-corpus runs (cells A and C of the pre-registration)",
   "programs_of_the_two_controls": "written after this freeze; their SHA-256 values are recorded in the results folder before their first use"},
  "public_value": "none for this model on this data set: the public MTEB results folder of the open weights (read 2026-10-03, MODEL_CARD_CLAIMS.json) holds no HotpotQA file, and the model card gives HotpotQA only inside a four-set average. "
                  "The result is reported with the sentence 'no public value for this model'."},
 "cell_H-R": {"what": "as cell D: llama-nemotron-rerank-1b-v2 1.10.0 on the 100 results per query of cell H, one call per query; quality, then the duration of every call in two passes", "only_if": "cell H is complete and both controls passed",
              "limits_s": {"rerank": 7200, "timed passes": 7200}},
 "known_before": {"whole MIRACL corpora with this NIM": known},
 "expectations": {
  "encoding": "between 400 and 1,000 passages per second (the passages are shorter than MIRACL's); the corpus is finished in one night stretch of about 10 hours or less",
  "H": "nDCG@10 between 0.66 and 0.82 and Recall@100 between 0.85 and 0.97 (a prior from figures published for other text-embedding models of this size, not looked up again for this file; there is no figure for this model)",
  "controls": "both pass", "H-R": "nDCG@10 rises by 0.02 to 0.08; Recall@100 equal before and after",
  "confidence": "low for the quality range (no reference for this model), moderate for the rest"},
 "branches_decided_in_advance": {"a control fails": "no figure of cell H is reported; the failure is the result", "the corpus is not finished at 08:00": "the checkpoint file says where it stopped; nothing is searched until it is finished",
                                 "the result lies outside the expected range": "reported as measured, with the controls; no setting is changed to move it"},
 "harness_sha256": {f: sha(os.path.join(HERE, f)) for f in BOUND},
}
if os.path.exists(OUT) and not json.load(open(OUT, encoding="utf-8")).get("draft"):
    sys.exit("refused: a frozen addendum exists")
json.dump(A, open(OUT, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
if not DRAFT:
    open(os.path.splitext(OUT)[0] + ".sha256", "w", encoding="utf-8", newline="\n").write(f"{sha(OUT)} *{os.path.basename(OUT)}\n")
print(("DRAFT " if DRAFT else "FROZEN ") + A["written_at"], sha(OUT))
