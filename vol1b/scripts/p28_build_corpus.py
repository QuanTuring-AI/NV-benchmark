#!/usr/bin/env python3
"""P28 · build the judge-isolation input set from the P19 run, and list what cannot be in it.

Input  : vol1b/results/p19_cell5/rows.jsonl (warm-up rows excluded)
Corpus : every distinct answer text whose FULL text was stored — that is, the nim-only arm's answers and the
         Guardrails arms' answers that were not blocked. Deduplicated by SHA-256 of the text.
Excluded: rows blocked by a rail. When the output rail blocks, `rails.generate_async` returns the canned refusal,
         so the answer that triggered the block survives only as the 200-character head in `llm_calls`. Those
         segments cannot be judged again on the same text and are listed, per row, with the reason.
usage: p28_build_corpus.py <p19 rows.jsonl> <out corpus.json> <out excluded_segments.json>"""
import hashlib, json, sys

rows = [json.loads(l) for l in open(sys.argv[1], encoding="utf-8") if l.strip()]
rows = [r for r in rows if not r.get("warmup")]
corpus, excluded = {}, []
for r in rows:
    tag = f"{r['arm']}:{r['question_id']}#{r['round']}"
    blocked = r["arm"] != "A" and r.get("was_blocked")
    if blocked:
        gen = [c for c in r.get("llm_calls", []) if c.get("task") == "general"]
        excluded.append({"row": tag, "question_id": r["question_id"], "arm": r["arm"], "round": r["round"],
                         "rail_inferred_from_calls": "output" if gen else "input",
                         "block_reason_as_recorded": r.get("block_reason"),
                         "recorded_reason_note": "gr_worker.py labels every refusal-phrase match as output_self_check, so this field "
                                                 "says output_self_check even for input-rail blocks; the reliable signal is whether a "
                                                 "`general` LLM call exists in the row",
                         "answer_generated": bool(gen),
                         "head_only_chars": len(gen[0].get("completion_head") or "") if gen else 0,
                         "head": (gen[0].get("completion_head") or "")[:200] if gen else None,
                         "why_no_full_text": ("the output rail blocked the answer; generate_async returns the canned refusal, so the "
                                              "answer text survives only as the 200-character head recorded by rails.explain()")
                         if gen else "the input rail blocked the question; no answer was generated"})
        continue
    t = r.get("response_full") or ""
    if not t:
        continue
    h = hashlib.sha256(t.encode("utf-8")).hexdigest()
    e = corpus.setdefault(h, {"sha256": h, "len": len(t), "text": t, "sources": []})
    e["sources"].append(tag)
items = sorted(corpus.values(), key=lambda x: (-x["len"], x["sha256"]))
json.dump(items, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, indent=0)
by_q = {}
for e in excluded:
    by_q.setdefault(e["question_id"], []).append(e["row"])
json.dump({"note": "segments that cannot be re-judged on the same text, and why", "count": len(excluded),
           "with_generated_answer_head_only": sum(1 for e in excluded if e["answer_generated"]),
           "input_rail_blocked_no_answer": sum(1 for e in excluded if not e["answer_generated"]),
           "rows_by_question": by_q, "segments": excluded},
          open(sys.argv[3], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"corpus texts {len(items)} · chars {sum(x['len'] for x in items)} · excluded rows {len(excluded)}")
