#!/usr/bin/env python3
"""Vol.5 · runs the ingestor server's own text-file reader (nv_ingest_client.util.file_processing.extract,
detect_encoding_and_read_text_file: charset_normalizer.detect, then decode) on uploaded passage files, inside the
ingestor-server image, and reports the encoding it picks and whether the decoded text equals the file's UTF-8 text.
usage (in the image): charset_recheck.py --staged DIR --ids FILE(json {"garbled": [...], "non_ascii_intact_sample": [...]}) --out FILE
"""
import argparse, collections, io, json, os
from nv_ingest_client.util.file_processing.extract import detect_encoding_and_read_text_file
import charset_normalizer

ap = argparse.ArgumentParser()
for x in ("--staged", "--ids", "--out"):
    ap.add_argument(x, required=True)
a = ap.parse_args()
ids = json.load(open(a.ids, encoding="utf-8")); rec = {"charset_normalizer": charset_normalizer.__version__}
for group, pids in ids.items():
    enc = collections.Counter(); same = 0
    for p in pids:
        raw = open(os.path.join(a.staged, p + ".txt"), "rb").read()
        enc[(charset_normalizer.detect(raw) or {}).get("encoding")] += 1
        same += detect_encoding_and_read_text_file(io.BytesIO(raw)) == raw.decode("utf-8")
    rec[group] = {"files": len(pids), "decoded_equal_to_utf8": same, "encoding_picked": dict(enc.most_common())}
json.dump(rec, open(a.out, "w", encoding="utf-8", newline="\n"), indent=1)
print(json.dumps(rec))
