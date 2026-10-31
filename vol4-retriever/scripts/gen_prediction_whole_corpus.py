#!/usr/bin/env python3
"""Vol.4 · writes the pre-registration of the whole-corpus quality cells, the reranking cell on their results and the
timing cell from two places, with its .sha256 file. A supplement to the pre-registrations of the first and the second
session: their rules, data, metrics and method stay as they are. Run once, before the first cell; the file is never
changed afterwards.
usage: gen_prediction_whole_corpus.py [--draft]
"""
import hashlib, json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__)); VOL = os.path.dirname(HERE); REPO = os.path.dirname(VOL)
RES = os.path.join(VOL, "results", "whole_corpus_quality")
OUT = os.path.join(RES, "prediction_whole_corpus.json")
DRAFT = "--draft" in sys.argv


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def load(*parts):
    return json.load(open(os.path.join(VOL, *parts), encoding="utf-8"))


first_pred = os.path.join(VOL, "results", "first_batch", "prediction_first_batch.json")
second_pred = os.path.join(VOL, "results", "second_batch", "prediction_second_batch.json")
fp = json.load(open(first_pred, encoding="utf-8"))
IM = {"n3": ("nvcr.io/nim/nvidia/nemotron-3-embed-1b:2.2.2", fp["P1_nim_same_task"]["image_digest"]),
      "e1b": ("nvcr.io/nim/nvidia/llama-nemotron-embed-1b-v2:1.13.0", fp["P2_other_embedding_nims"]["images"]["llama-nemotron-embed-1b-v2"]["image_digest"]),
      "e300": ("nvcr.io/nim/nvidia/llama-nemotron-embed-300m-v2:1.13.0", fp["P2_other_embedding_nims"]["images"]["llama-nemotron-embed-300m-v2"]["image_digest"]),
      "evl": ("nvcr.io/nim/nvidia/llama-nemotron-embed-vl-1b-v2:2.3.0", fp["P2_other_embedding_nims"]["images"]["llama-nemotron-embed-vl-1b-v2"]["image_digest"]),
      "rr": ("nvcr.io/nim/nvidia/llama-nemotron-rerank-1b-v2:1.10.0", fp["P3_reranking"]["images"]["llama-nemotron-rerank-1b-v2"]["image_digest"])}


def image(k):
    return {"image": IM[k][0], "image_digest_recorded_by_the_first_session": IM[k][1], "checked_again": "the step that starts the container records the digest; another digest stops the cell"}


def known(arm, dataset):
    s = load("results", "first_batch", arm, dataset, "score.json")
    return {"file": f"../first_batch/{arm}/{dataset}/score.json", "sha256": sha(os.path.join(VOL, "results", "first_batch", arm, dataset, "score.json")),
            "ndcg_cut_10": s["metrics"]["ndcg_cut_10"], "recall_100": s["metrics"]["recall_100"], "passages": s["source"]["passages"], "queries": s["source"]["queries"]}


def checkpoints(dataset):
    p = os.path.join(VOL, "results", "second_batch", "full_corpus", dataset, "checkpoints.jsonl")
    recs = [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
    fin = next(r for r in recs if r["kind"] == "finished"); q = next(r for r in recs if r["kind"] == "queries")
    return {"file": f"../second_batch/full_corpus/{dataset}/checkpoints.jsonl", "sha256": sha(p), "passages": fin["passages"], "pieces": sum(r["kind"] == "piece" for r in recs),
            "queries": q["queries"], "queries_sha256": q["queries_sha256"], "query_ids_sha256": q["query_ids_sha256"]}


def timing(arm, dataset="miracl-hn-zh"):
    t = load("results", "first_batch", arm, dataset, "throughput.json")
    return {"file": f"../first_batch/{arm}/{dataset}/throughput.json", "passages_per_s_median": t["passages_per_s_median"], "passes": [p["passages_per_s"] for p in t["passes"]]}


before = os.path.join(RES, "before_the_run")
sci = json.load(open(os.path.join(before, "program_check_scifact_score.json"), encoding="utf-8"))
sci_first = load("results", "first_batch", "nim_nemotron-3-embed-1b_auto", "beir-scifact", "score.json")
two = [json.loads(l) for l in open(os.path.join(before, "program_check_two_pieces_progress.jsonl"), encoding="utf-8") if l.strip()]
per_piece = [round(r["read_and_hash_s"] + r["search_s"], 2) for r in two if r["kind"] == "piece"]
method_host = load("results", "first_batch", "method_host_vs_container", "host_kept_batch64.json")
method_cont = load("results", "first_batch", "method_host_vs_container", "container_kept_batch64.json")
NEW = ["scripts/search_whole_corpus.py", "scripts/rerank_latency.py"]
USED = ["scripts/embed_cell.py", "scripts/score_run.py", "scripts/rerank_cell.py", "scripts/run_step.py", "scripts/session_step.py", "scripts/method_cell.py",
        "scripts/retrieval_datasets.py", "scripts/retrieval_metrics.py", "scripts/nim_retrieval_clients.py", "client/Dockerfile"]
Z, J = known("nim_nemotron-3-embed-1b_auto", "miracl-hn-zh"), known("nim_nemotron-3-embed-1b_auto", "miracl-hn-ja")

pred = {
 "what": "Pre-registration of the Vol.4 cells on the whole MIRACL zh and ja corpora (quality by exact search), of the reranking cell on their results and of a timing cell from two places; a supplement to prediction_first_batch.json and prediction_second_batch.json",
 "draft": DRAFT, "written_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
 "supplements": [{"file": "../first_batch/prediction_first_batch.json", "sha256": sha(first_pred)}, {"file": "../second_batch/prediction_second_batch.json", "sha256": sha(second_pred)}],
 "kept_from_them": "the rules (timed and untimed parts, the gate before a timed part, one variable per comparison, raw output outside the repository, a limit on every measuring command), the data sets, the two metrics and their program, and the method (client in a container on the NIM's Docker network, one kept connection)",
 "host": {"card": "one RTX 5090 (32 GB), Windows 11 + Docker Desktop (WSL2)", "cpu": "Intel Core i7-14700, 20 cores, 28 threads", "memory_gib": 63.7,
          "memory_free_gib_when_measured": 45.2, "measured_at": "2026-10-05, about 20:30 (+0800), Docker Desktop not running", "disk": "one NVMe SSD; the vectors are on it"},

 "vectors_used": {
  "whole_corpus": {"encoder": "nvcr.io/nim/nvidia/nemotron-3-embed-1b:2.2.2 pinned to fp16 (second session, cell 6)", "size": 2048, "storage": "float32, pieces of 100,000 passages, outside the repository",
                   "miracl-zh": checkpoints("miracl-zh"), "miracl-ja": checkpoints("miracl-ja")},
  "queries": "the query vectors stored with each corpus: encoded by the same container at the start of that corpus's run, input_type query, no prefix added by the client (the checkpoint files' `queries` lines carry their SHA-256). They are not encoded again: the work order's first GPU step is therefore not needed, and cells A to C need no card and no container.",
  "reduced_corpus": {"zh": {"reference arm (open weights)": known("reference_bf16", "miracl-hn-zh"), "the same NIM image, no precision set": Z},
                     "ja": {"reference arm (open weights)": known("reference_bf16", "miracl-hn-ja"), "the same NIM image, no precision set": J},
                     "note": "the second session showed that this image offers one pipeline on this card (fp16); with the precision pinned it gave the same nDCG@10 and Recall@100 on miracl-hn-zh as with nothing set"}},

 "facts_measured_before_this_file": {
  "queries_and_judgements": "the reduced task (MIRACLRetrievalHardNegatives) and MIRACL dev have the same query ids, the same query texts and the same judgements: zh 393 queries, 3,928 judgements, 994 of them relevant; ja 860 queries, 8,354 judgements, 1,790 relevant. Compared with the readers of this volume on the files in hand.",
  "relevant_passages": "every relevant passage of the judgements is in the reduced corpus (zh 966 of 966 ids, ja 1,728 of 1,728). Of the passages judged at all, the reduced corpus holds 3,369 of 3,786 (zh) and 7,285 of 8,066 (ja): the rest are passages judged not relevant.",
  "what_follows": "with the same vectors, adding passages to a corpus that already holds every relevant passage can only push relevant passages down or leave them where they are. nDCG@10 and Recall@100 on the whole corpus are therefore at most the values on the reduced corpus. The vectors are not bit for bit the same (another call, other batches; the second session measured a smallest cosine of 0.999999998 on 512 passages), so a difference in the fourth decimal in either direction is possible; more is not.",
  "program_checks": {
   "why": "the search program is new. Both checks ran before this file was frozen; neither is one of the cells below and neither gives a figure about a whole corpus.",
   "one_file_layout": {"what": "beir-scifact, the first session's stored vectors of the same NIM, cut into pieces of 1,000 rows", "file": "before_the_run/program_check_scifact_score.json",
                       "ndcg_cut_10": sci["metrics"]["ndcg_cut_10"], "first_session": sci_first["metrics"]["ndcg_cut_10"],
                       "per_query_values_identical": sci["per_query"] == sci_first["per_query"]},
   "pieces_layout": {"what": "the first two pieces of MIRACL zh, then stopped (no ranking, no metric): the calling form, the comparison of each file with its recorded SHA-256, and the seconds per piece",
                     "file": "before_the_run/program_check_two_pieces_progress.jsonl", "seconds_per_piece": per_piece},
   "tests": "tests/test_search_whole_corpus.py (23) and tests/test_rerank_latency.py (4); each rule the tests guard was broken once in a copy of the program and the tests failed each time (18 and 6 changes)"}},

 "memory_budget_of_the_search": {
  "piece_file_mib": round((100000 * 2048 * 4 + 128) / 2**20, 1), "pieces_in_memory_at_once": 1,
  "per_piece_in_memory_mib": {"the file's bytes, used in place": 781, "the same vectors divided by their length": 781, "products of 64 queries with the piece": 24,
                              "products of all queries with the piece (zh 393 / ja 860)": [150, 328], "ids of the piece": "about 10"},
  "kept_between_pieces": "per query the 100 best scores and passage numbers, and the ids of those passages: below 2 MiB",
  "peak_estimate_gib": 2.2, "share_of_free_memory": "about 5%", "no_part_of_a_corpus_is_held_beyond_its_piece": True,
  "state_file": "rewritten after every piece outside the repository; one line per piece in search_progress.jsonl inside it"},

 "cell_A_check_of_the_search_program": {
  "what": "the search program on the reduced corpora, whose results exist: the first session's stored vectors, cut into pieces of 10,000 rows so that the merging across pieces runs",
  "runs": [{"dataset": d, "vectors": arm, "must_equal": known(arm, d)} for d in ("miracl-hn-zh", "miracl-hn-ja") for arm in ("reference_bf16", "nim_nemotron-3-embed-1b_auto")],
  "command": {"program": "scripts/search_whole_corpus.py --piece-rows 10000 --top 100", "timeout_s": 300},
  "pass": "nDCG@10 and Recall@100 equal to the first session's when both are rounded to five decimals, in all four runs. The first session kept 1,000 results per query and this program keeps 100; neither metric looks beyond 100.",
  "if_not": "no figure about a whole corpus is produced; the difference is reported",
  "expectation": "equal, also without rounding, and the per-query values identical (as in the program check on beir-scifact)",
  "note_on_the_work_order": "the work order names 0.66313 and 0.74383 as the values to reproduce. Those are the reference arm's (open weights). The whole-corpus vectors come from the NIM, whose values on the reduced corpora are 0.66199 and 0.74371; both pairs are checked, and the NIM's pair is the one set beside the whole-corpus values."},

 "cell_C_ids_and_vectors_belong_together": {
  "what": "the stored vectors of the whole corpus, searched with only the passages whose id is in the reduced corpus taking part (--only-ids-of). This is the reduced task again, computed from the whole-corpus files: it fails if ids and vectors of a piece are shifted against each other, if a piece is missing or doubled, or if the stored query vectors are not those of the queries.",
  "runs": [{"dataset": "miracl-zh", "ids_of": "the reduced corpus of miracl-hn-zh", "ids": Z["passages"], "compared_with": Z["ndcg_cut_10"]},
           {"dataset": "miracl-ja", "ids_of": "the reduced corpus of miracl-hn-ja", "ids": J["passages"], "compared_with": J["ndcg_cut_10"]}],
  "command": {"program": "scripts/search_whole_corpus.py --checkpoints ... --only-ids-of <the first session's folder of the same NIM>", "timeout_s": 1800},
  "pass": "every id of the reduced corpus is found in the whole corpus, and nDCG@10 is within 0.001 and Recall@100 within 0.002 of the NIM's values on the reduced corpus",
  "if_not": "the whole-corpus figures of cell B are not reported until the cause is known",
  "expectation": "passes; the two nDCG@10 values agree to four decimals"},

 "cell_B_whole_corpus": {
  "what": "exact search of the dev queries over every passage of MIRACL zh and of MIRACL ja; nDCG@10 and Recall@100 against the public dev judgements",
  "runs": ["miracl-zh (4,934,368 passages, 393 queries)", "miracl-ja (6,953,614 passages, 860 queries)"],
  "command": {"program": "scripts/search_whole_corpus.py --checkpoints ... --top 100", "timeout_s": 1800},
  "search": "cosine, every query against every passage, no index of any kind; 100 results per query",
  "reported": "per language one line: nDCG@10, Recall@100, queries, passages, the wall time of the search on the host CPU (stated as that, not as a speed of the NIM), and beside it the same NIM's values on the reduced corpus",
  "sentence_for_the_two_values": "the reduced corpus is the condition of the published model-card figure; the whole corpus is the condition of a deployment",
  "branches_decided_in_advance": {
   "lower_or_equal": "the whole-corpus value is reported beside the reduced-corpus value with the sentence above",
   "higher_by_more_than_0.001": "not reported: by the fact above it cannot be higher with the same vectors. The alignment of ids and judgements is examined first (cell C, the count of judged ids found in the corpus)."},
  "alignment_recorded": "how many of the judged passage ids and of the relevant ones are among the ids of the corpus; all must be found",
  "expectation": {"zh": {"ndcg_cut_10": "between 0.630 and 0.662", "recall_100": "between 0.945 and 0.988"}, "ja": {"ndcg_cut_10": "between 0.710 and 0.744", "recall_100": "between 0.955 and 0.992"},
                  "reason": "the reduced corpus was built from the passages three retrievers ranked highest per query, so most passages that can displace a relevant one are in it already; the whole corpus adds about 60 times (zh) and 37 times (ja) as many passages, nearly all of them never judged",
                  "confidence": "moderate for the direction and the upper end, low for the lower end",
                  "seconds": f"from the program check ({per_piece} s for two pieces): about 1.5 minutes for zh and 2.5 for ja"}},

 "cell_D_reranking_the_whole_corpus_results": {
  "what": "the 100 results per query of cell B, scored again by the reranking NIM of the first session, one call per query",
  **image("rr"), "start": "as in the first session: no profile set (the image selected a TensorRT fp8 profile on this card)",
  "needs": "cell B's run files; the card, after the go-ahead for a GPU session",
  "quality": {"commands": [{"what": "start and wait for ready", "program": "scripts/session_step.py nim-start --kind 1x --wait 600", "timeout_s": 720},
                           {"what": "smoke: three queries", "program": "scripts/rerank_cell.py smoke --dataset miracl-zh", "timeout_s": 900},
                           {"what": "rerank every query (untimed); zh, then ja", "program": "scripts/rerank_cell.py rerank --depth 100", "timeout_s": [1200, 2400]},
                           {"what": "score", "program": "scripts/score_run.py --rerank-from", "timeout_s": 300}],
              "reported": "per language nDCG@10 before and after; Recall@100 before and after, which must be equal because the 100 passages of a query are the same ones in another order",
              "if_recall_differs": "the two run files do not hold the same passages per query: reported as a fault of the cell, the nDCG@10 pair is not used",
              "expectation": "nDCG@10 rises on both languages by 0.015 to 0.04 (on the reduced corpora the same reranker gave +0.024 for zh and +0.028 for ja); Recall@100 equal to the last decimal",
              "note": "the limits of the first three commands include reading the whole corpus once to collect the texts of the passages asked for (4.9 and 7.0 million lines)"},
  "durations": {"program": "scripts/rerank_latency.py --where container --passes 2 --depth 100",
                "what": "every query of the run file, one call each with its 100 passages, one after the other on one kept connection, from a container on the NIM's Docker network; two passes; the duration of every call is kept",
                "conditions": "the gate with --timed right before each run; no game launcher running; one blocking command per run and no other command from this session while it runs",
                "commands": [{"what": "zh, two passes", "timeout_s": 1200}, {"what": "ja, two passes", "timeout_s": 2400}],
                "reported": "per language and pass: calls, p50, p90 and p99 of the call duration in ms (nearest rank), min, max, pairs per second; the passes side by side, not pooled",
                "expectation": {"zh_p50_ms": "130 to 190", "ja_p50_ms": "140 to 200", "p99": "below 600 ms on both", "second_pass": "p50 within 5% of the first pass's",
                                "reason": "the first session's rates on the reduced corpora were 655.5 (zh) and 611.1 (ja) pairs per second over 40 queries, which is about 153 and 164 ms per call of 100 passages"},
                "not_claimed": "one stream of calls only: nothing about concurrent calls; a duration measured in the client, on this host"}},

 "cell_E_timing_from_two_places": {
  "why": "the work order asks for the four embedding cells' speed 'again with the client in a container, beside the host-side values of the first session'. The first session's four cells were already measured from a container (that is the method of this volume); a host-side value exists for one NIM only, from the method cell: "
         f"{method_host['passages_per_s_median']} passages per second from the host against {method_cont['passages_per_s_median']} from the container. This cell therefore measures both places for each of the four NIMs on another day.",
  "data": "miracl-hn-zh, the first 4,096 passages, 64 per request, one kept connection, one discarded pass over the first 4 requests, three timed passes (the sample and request of every timed cell of this volume)",
  "per_nim": ["container: scripts/embed_cell.py throughput (the program of the first session's cells)", "host through the published port: scripts/method_cell.py --where host --batch 64",
              "container once more: scripts/embed_cell.py throughput"],
  "why_the_third_run": "with two runs in a fixed order a drift over the minutes of a container's life could not be told from the place of the client; the second container run shows the drift",
  "nims": {"nemotron-3-embed-1b": {**image("n3"), "start": "NIM_ENGINE_PRECISION=fp16", "first_session": timing("nim_nemotron-3-embed-1b_auto"), "second_session_fp16": 230.3},
           "llama-nemotron-embed-1b-v2": {**image("e1b"), "start": "no profile set (fp8, selected by the image)", "first_session": timing("nim_llama-nemotron-embed-1b-v2_auto"), "second_session_same_start": 498.4},
           "llama-nemotron-embed-300m-v2": {**image("e300"), "start": "no profile set", "first_session": timing("nim_llama-nemotron-embed-300m-v2_auto")},
           "llama-nemotron-embed-vl-1b-v2": {**image("evl"), "start": "no profile set", "first_session": timing("nim_llama-nemotron-embed-vl-1b-v2_auto")}},
  "commands_per_nim": [{"what": "start", "timeout_s": "1020 (2.x images) / 720 (1.13.0 images)"}, {"what": "smoke", "program": "scripts/embed_cell.py smoke", "timeout_s": 300},
                       {"what": "each of the three timed runs, the gate with --timed right before", "timeout_s": 600}, {"what": "stop", "timeout_s": 300}],
  "reported": "per NIM one line: passages per second from the container (both runs, all passes), from the host, the host's difference from the mean of the two container runs in percent, and the first session's container value beside them",
  "expectation": {"container_against_the_first_session": "each NIM's first container run within 6% of its first-session value",
                  "host_against_container": "the host is slower for every NIM, by 5% to 15% for the two 1b text encoders and the vl encoder, and by more for the 300m encoder (15% to 30%): its requests are the shortest, so a fixed cost per request is a larger share",
                  "two_container_runs": "within 3% of each other",
                  "confidence": "moderate; one earlier comparison on one NIM is all there is"},
  "not_claimed": "host-side values of the first session for the other three NIMs: there are none"},

 "order": ["A (no card)", "C (no card)", "B (no card)", "D (card; after the go-ahead)", "E (card)"],
 "stops": "A not passed: C and B are not run. C not passed: B's figures are not reported. D needs B. A cell whose container does not report ready is reported as not run with its last log lines.",
 "not_in_this_file": ["the two Vol.5 cells of the same work order: they have their own file in the Vol.5 directory", "a search with an index", "any other data set or split", "the reranker on more than 100 results"],
 "harness_sha256": {f: sha(os.path.join(VOL, f)) for f in NEW + USED} | {"tools/g8_gate.py": sha(os.path.join(REPO, "tools", "g8_gate.py"))},
 "programs_written_after_the_freeze": "none planned; if one is needed, its SHA-256 is written to the events file before its first use",
}
if os.path.exists(OUT) and not json.load(open(OUT, encoding="utf-8")).get("draft"):
    sys.exit("refused: a frozen pre-registration exists")
json.dump(pred, open(OUT, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
if not DRAFT:
    open(os.path.splitext(OUT)[0] + ".sha256", "w", encoding="utf-8", newline="\n").write(f"{sha(OUT)} *{os.path.basename(OUT)}\n")
print(("DRAFT " if DRAFT else "FROZEN ") + pred["written_at"], sha(OUT))
