#!/usr/bin/env python3
"""Vol.5 · adapter: the answers of the NVIDIA RAG Blueprint's RAG server (v2.6.2) in the scorer's neutral format.

What the server returns about its sources (src/nvidia_rag/rag_server/response_generator.py at tag v2.6.2: classes
Citations, SourceResult, SourceMetadata, lines 143 to 246): the first stream event carries
    citations.total_results
    citations.results[i].document_name       the file's base name
    citations.results[i].content             the chunk's text (for image, table and chart chunks a base64 image; the
                                             chunk's text is then in metadata.description)
    citations.results[i].document_type       text | image | table | chart | audio
    citations.results[i].score               the relevance score
    citations.results[i].metadata.page_number, .location (a box, image and structured chunks only), .content_metadata
There is no chunk id (document_id is empty) and there are no character offsets: a passage is identified by its file
and its text. The results are the passages the server gave to the model, in its order; the server does not say which
of them the answer used, and it has no field for "no answer": a refusal is whatever the model wrote.

Mapping to the scorer's output record:
    retrieved[i] = {"file_id": document_name without its extension, "text": content (or metadata.description when the
                    chunk is not a text chunk)}                       in the order of citations.results
    answer       = the concatenated answer text
    refused      = null (the scorer's pattern decides)                cited = null (not known)
Input: JSON lines {"id", "answer", "citations"} as rag_probe.py writes them to its --raw file (outside the
repository). Output: JSON lines for rag_eval.py --outputs (they contain passage text: keep them outside as well).
usage: blueprint_adapter.py RAW.jsonl OUTPUTS.jsonl
"""
import json, os, sys


def to_output(rec):
    results = ((rec.get("citations") or {}).get("results")) or []
    retrieved = []
    for c in results:
        text = c.get("content") or ""
        if c.get("document_type") not in (None, "text", "audio"):
            text = ((c.get("metadata") or {}).get("description")) or ""
        retrieved.append({"file_id": os.path.splitext(c.get("document_name") or "")[0], "text": text, "page": (c.get("metadata") or {}).get("page_number"), "score": c.get("score"), "type": c.get("document_type")})
    return {"id": rec["id"], "retrieved": retrieved, "answer": rec.get("answer") or "", "refused": None, "cited": None, "judged_correct": None}


def main():
    src, dst = sys.argv[1], sys.argv[2]
    with open(dst, "w", encoding="utf-8", newline="\n") as out:
        n = 0
        for line in open(src, encoding="utf-8"):
            if line.strip():
                out.write(json.dumps(to_output(json.loads(line)), ensure_ascii=False) + "\n"); n += 1
    print(json.dumps({"records": n}))


if __name__ == "__main__":
    main()
