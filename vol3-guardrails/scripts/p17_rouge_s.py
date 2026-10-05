"""P17 profile S · descriptive ROUGE on the summaries AIPerf recorded (not an accuracy gate).
usage: p17_rouge_s.py <S main dir> <out json> [level dirs, default c0001 c0004]
References: CNN-DailyMail 3.0.0 validation `highlights`, matched to each request by its exact prompt text.
Scores: rouge_score 0.1.2, use_stemmer=True; rougeLsum with sentences split on end punctuation followed by whitespace
(MLPerf splits with nltk; not reproduced here). Profiling-phase records only; warm-up records excluded."""
import json, os, re, statistics, sys
import datasets
from rouge_score import rouge_scorer

main_dir, out = sys.argv[1], sys.argv[2]
levels = sys.argv[3:] or ["c0001", "c0004"]
TEMPLATE_HEAD = "Summarize the following news article in 128 tokens. Please output the summary only, without any other text.\n\nArticle:\n"
ds = datasets.load_dataset("abisee/cnn_dailymail", "3.0.0", split="validation")
ref = {a: h for a, h in zip(ds["article"], ds["highlights"])}
split = lambda t: "\n".join(s for s in re.split(r"(?<=[.!?])\s+", t.strip()) if s)
sc = rouge_scorer.RougeScorer(["rouge1", "rouge2", "rougeL", "rougeLsum"], use_stemmer=True)


def text_of(rec):
    parts = []
    for r in rec.get("responses") or []:  # AIPerf raw export: each response holds SSE packets {name, value}
        for pk in r.get("packets") or []:
            if pk.get("name") != "data" or (pk.get("value") or "").strip() == "[DONE]":
                continue
            try:
                ch = json.loads(pk["value"])
            except ValueError:
                continue
            for c in ch.get("choices") or []:
                parts.append((c.get("delta") or {}).get("content") or "")
    return "".join(parts)


result = {"levels": {}, "note": "descriptive only; a small subset of the 13,368-article set; not comparable to MLPerf accuracy targets"}
for lv in levels:
    scores, unmatched, empty, n = [], 0, 0, 0
    for line in open(os.path.join(main_dir, lv, "profile_export_raw.jsonl"), encoding="utf-8"):
        rec = json.loads(line)
        if (rec.get("metadata") or {}).get("benchmark_phase") != "profiling":
            continue
        n += 1
        user = [m["content"] for m in rec["payload"]["messages"] if m["role"] == "user"][0]
        art = user[len(TEMPLATE_HEAD):-len("\n\nSummary:")] if user.startswith(TEMPLATE_HEAD) else None
        if art not in ref:
            unmatched += 1; continue
        gen = text_of(rec)
        if not gen:
            empty += 1; continue
        s = sc.score(split(ref[art]), split(gen))
        scores.append({k: v.fmeasure for k, v in s.items()})
    agg = {k: round(100 * statistics.mean(x[k] for x in scores), 2) for k in ("rouge1", "rouge2", "rougeL", "rougeLsum")} if scores else None
    result["levels"][lv] = {"profiling_records": n, "scored": len(scores), "unmatched_prompt": unmatched, "empty_output": empty, "rouge_f1_x100": agg}
json.dump(result, open(out, "w", encoding="utf-8"), indent=1)
print(json.dumps(result, indent=1))
