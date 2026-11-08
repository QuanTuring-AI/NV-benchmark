#!/usr/bin/env python3
"""Vol.5 · the two ingestion behaviours reproduced without any server, inside the images the Blueprint v2.6.2 ships:

  split    (nv-ingest 26.3.0 image) nv_ingest_api.internal.transform.split_text._split_into_chunks with the tokenizer the
           image carries (/workspace/models/llama-3.2-1b/tokenizer), on issue_repro/three_sentences.txt at the
           default chunk size and overlap of the Blueprint (512, 150) and of the schema (1024, 150), and on ten words
           with 4 and 1 (so that more than one chunk exists)
  decode   (ingestor-server 2.6.0 image) nv_ingest_client.util.file_processing.extract.detect_encoding_and_read_text_file
           on every issue_repro/*.txt: the encoding charset_normalizer picks, and whether the text equals the UTF-8 text

usage (in the image): ingest_unit_repro.py split|decode --dir DIR --out FILE
"""
import argparse, glob, io, json, os

ap = argparse.ArgumentParser(); ap.add_argument("cmd", choices=("split", "decode"))
ap.add_argument("--dir", required=True); ap.add_argument("--out", required=True)
a = ap.parse_args()
if a.cmd == "split":
    from transformers import AutoTokenizer
    from nv_ingest_api.internal.transform.split_text import _split_into_chunks
    tok = AutoTokenizer.from_pretrained("/workspace/models/llama-3.2-1b/tokenizer")
    text = open(os.path.join(a.dir, "three_sentences.txt"), encoding="utf-8").read(); ten = "one two three four five six seven eight nine ten"
    rec = {"function": "nv_ingest_api/internal/transform/split_text.py _split_into_chunks", "cases": [
        {"text": text, "chunk_size": s, "chunk_overlap": o, "chunks": _split_into_chunks(text, tok, chunk_size=s, chunk_overlap=o)} for s, o in ((512, 150), (1024, 150))]
        + [{"text": ten, "chunk_size": 4, "chunk_overlap": 1, "chunks": _split_into_chunks(ten, tok, chunk_size=4, chunk_overlap=1)}]}
else:
    import charset_normalizer
    from nv_ingest_client.util.file_processing.extract import detect_encoding_and_read_text_file
    rec = {"function": "nv_ingest_client/util/file_processing/extract.py detect_encoding_and_read_text_file", "charset_normalizer": charset_normalizer.__version__, "files": []}
    for f in sorted(glob.glob(os.path.join(a.dir, "*.txt"))):
        raw = open(f, "rb").read(); out = detect_encoding_and_read_text_file(io.BytesIO(raw))
        rec["files"].append({"file": os.path.basename(f), "encoding_picked": (charset_normalizer.detect(raw) or {}).get("encoding"),
                             "equals_utf8_text": out == raw.decode("utf-8"), "decoded": out})
json.dump(rec, open(a.out, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
print(json.dumps(rec, ensure_ascii=True)[:600])
