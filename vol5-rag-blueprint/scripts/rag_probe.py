#!/usr/bin/env python3
"""Vol.5 · probes of the answering path of the NVIDIA RAG Blueprint: each question is sent once to the RAG server's
/generate endpoint (streamed), and what came back is described. Probes show that the path works end to end; they are
not a question set and nothing here is a quality figure.

Per probe, recorded: HTTP status, seconds to the first piece of answer text, seconds to the end, number of stream
events, finish reason, token usage if the server reports it, the answer's length and SHA-256, whether it reads as a
refusal (the patterns of eval/rag_eval.py), whether it carries a think tag, and the citations of the first event that
has any: how many, and for each the document name, type, score, page number, and the length and SHA-256 of its content.
If the probe names files it expects among the citations, whether each is there. The answer text and the passages go
to --raw (a file outside the repository) and nowhere else.

usage: rag_probe.py --url http://127.0.0.1:8081 --collection NAME --probes PROBES.json --out FILE.json --raw FILE.jsonl
       PROBES.json: [{"id", "question", "lang", "expected_file_names": [..] | null, "expected": "answer" | "refusal"}, ...]
"""
import argparse, hashlib, json, os, sys, time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "eval"))
from rag_eval import refused_by_pattern  # noqa: E402


def sha(text):
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True); ap.add_argument("--collection", required=True); ap.add_argument("--probes", required=True); ap.add_argument("--out", required=True); ap.add_argument("--raw", required=True)
    ap.add_argument("--timeout", type=int, default=600)
    a = ap.parse_args()
    if os.path.exists(a.out):
        raise SystemExit(f"refused: {a.out} exists")
    probes = json.load(open(a.probes, encoding="utf-8")); base = a.url.rstrip("/")
    out = {"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "what": "probes of the answering path; lengths, digests, counts and seconds only", "endpoint": "POST /generate (streamed)", "collection": a.collection,
           "request": "one user message, use_knowledge_base true, collection_names [the collection], enable_citations true; every other field at the server's default", "health": None, "probes": []}
    try:
        h = requests.get(base + "/health", params={"check_dependencies": "true"}, timeout=120); out["health"] = {"status": h.status_code, "characters": len(h.text)}
    except Exception as e:
        out["health"] = {"error": f"{type(e).__name__}: {e}"[:200]}
    os.makedirs(os.path.dirname(os.path.abspath(a.raw)), exist_ok=True); raw = open(a.raw, "a", encoding="utf-8", newline="\n")
    for p in probes:
        body = {"messages": [{"role": "user", "content": p["question"]}], "use_knowledge_base": True, "collection_names": [a.collection], "enable_citations": True}
        rec = {"id": p["id"], "lang": p.get("lang"), "expected": p.get("expected"), "question_sha256": sha(p["question"]), "at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
        t0 = time.perf_counter(); answer = []; reasoning = 0; events = 0; first = None; cites = None; finish = None; usage = None
        try:
            with requests.post(base + "/generate", json=body, stream=True, timeout=a.timeout) as r:
                rec["status"] = r.status_code
                if r.status_code != 200:
                    rec["body"] = r.text[:600]
                else:
                    for line in r.iter_lines(decode_unicode=True):
                        if not line or not line.startswith("data:"):
                            continue
                        payload = line[5:].strip()
                        if payload == "[DONE]":
                            break
                        try:
                            d = json.loads(payload)
                        except ValueError:
                            continue
                        events += 1; ch = (d.get("choices") or [{}])[0]; msg = ch.get("message") or ch.get("delta") or {}
                        piece = msg.get("content") or ""; reasoning += len(msg.get("reasoning_content") or "")
                        if piece:
                            if first is None:
                                first = time.perf_counter() - t0
                            answer.append(piece)
                        if cites is None and ((d.get("citations") or {}).get("results")):
                            cites = d["citations"]
                        finish = ch.get("finish_reason") or finish; usage = d.get("usage") or usage
        except Exception as e:
            rec["error"] = f"{type(e).__name__}: {e}"[:300]
        text = "".join(answer); results = (cites or {}).get("results") or []
        names = [c.get("document_name") for c in results]
        rec.update({"seconds_to_first_answer_text": None if first is None else round(first, 3), "seconds_total": round(time.perf_counter() - t0, 3), "stream_events": events, "finish_reason": finish, "usage": usage,
                    "answer": {"characters": len(text), "sha256": sha(text), "reads_as_a_refusal": refused_by_pattern(text), "has_a_think_tag": "</think>" in text or "<think>" in text, "reasoning_characters_in_their_own_field": reasoning},
                    "citations": {"total_results_reported": (cites or {}).get("total_results"), "results": len(results), "keys_of_a_result": sorted(results[0].keys()) if results else None,
                                  "keys_of_its_metadata": sorted((results[0].get("metadata") or {}).keys()) if results else None,
                                  "list": [{"document_name": c.get("document_name"), "document_type": c.get("document_type"), "score": c.get("score"), "page_number": (c.get("metadata") or {}).get("page_number"),
                                            "content_characters": len(c.get("content") or ""), "content_sha256": sha(c.get("content"))} for c in results]},
                    "expected_files_among_the_citations": None if not p.get("expected_file_names") else {n: n in names for n in p["expected_file_names"]}})
        raw.write(json.dumps({"id": p["id"], "answer": text, "citations": cites}, ensure_ascii=False) + "\n"); raw.flush()
        out["probes"].append(rec)
        print(json.dumps({k: rec.get(k) for k in ("id", "status", "seconds_to_first_answer_text", "seconds_total", "finish_reason", "error")} | {"answer_characters": len(text), "refusal": rec["answer"]["reads_as_a_refusal"],
                          "citations": len(results), "expected": rec["expected_files_among_the_citations"]}, ensure_ascii=False), flush=True)
    out["program_sha256"] = hashlib.sha256(open(os.path.abspath(__file__), "rb").read()).hexdigest()
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump(out, open(a.out, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    return 0 if all(p.get("status") == 200 for p in out["probes"]) else 4


if __name__ == "__main__":
    sys.exit(main())
