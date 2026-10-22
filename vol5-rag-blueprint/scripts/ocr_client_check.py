#!/usr/bin/env python3
"""Vol.5 · one question, asked from inside the ingestion library's own container: can the OCR client of NV-Ingest 26.3.0
(the version the RAG Blueprint v2.6.2 pins) talk to an OCR service at a given HTTP address — here the newer OCR NIM's
/v1/ocr — and read its answer?

The Blueprint's ingestion reaches its OCR service only after the page-elements service has found a region to read
(EXTRACTION_NIMS_ON_WSL2.md, section 9), and that service does not start on this host. This program leaves that step
out: it builds the library's OCR client the way the library's table extractor does (the same interface class, the same
factory, the same arguments of `infer`) and hands it one image. Nothing of the library is changed or patched.

  client     nv_ingest_api.util.nim.create_inference_client((None, <endpoint>), NemoRetrieverOCRModelInterface(),
             auth_token=None, infer_protocol="http")
  call       client.infer(data={"base64_images": [...]}, model_name=<name>, input_names, output_names, dtypes,
             merge_level="word", max_batch_size=2)       (table_extractor.py, the branch for the model name `pipeline`)
  recorded   whether the call returned, the type and first line of an exception if it did not, the number of text
             pieces, the characters returned, and against the image's known text how many of its CJK characters and of
             its Latin letters and digits were found (multiset, white space ignored). Of the text itself only the first
             --show characters are written; the test image is public text made for this repository.

Run it with the library's own Python, in a container of the NV-Ingest image on the Docker network of the OCR service.
usage: ocr_client_check.py --endpoint http://HOST:8000/v1/ocr --image FILE.png --out FILE.json [--expected FILE.txt]
                           [--model-name pipeline] [--calls 2] [--show 50]
"""
import argparse, base64, collections, hashlib, importlib.metadata as md, json, os, sys, time, traceback


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def bag(text, kind):
    if kind == "cjk":
        return collections.Counter(c for c in text if "一" <= c <= "鿿")
    return collections.Counter(c.lower() for c in text if c.isascii() and c.isalnum())


def found(expected, got, kind):
    e, g = bag(expected, kind), bag(got, kind)
    return {"expected": sum(e.values()), "found": sum((e & g).values()), "returned": sum(g.values())}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--endpoint", required=True); ap.add_argument("--image", required=True); ap.add_argument("--out", required=True); ap.add_argument("--expected")
    ap.add_argument("--model-name", default=os.environ.get("OCR_MODEL_NAME", "pipeline")); ap.add_argument("--calls", type=int, default=2); ap.add_argument("--show", type=int, default=50)
    a = ap.parse_args()
    if os.path.exists(a.out):
        raise SystemExit(f"refused: {a.out} exists")
    raw = open(a.image, "rb").read()
    rec = {"what": "the OCR client of the ingestion library against one HTTP address, one image per call", "at": now(), "endpoint": a.endpoint, "protocol": "http",
           "model_name_passed": a.model_name, "image": {"file": os.path.basename(a.image), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)},
           "library": {}, "calls": []}
    for p in ("nv-ingest-api", "nv-ingest", "nv-ingest-client", "tritonclient", "requests"):
        try:
            rec["library"][p] = md.version(p)
        except Exception:
            rec["library"][p] = None
    rec["library"]["python"] = sys.version.split()[0]
    expected = open(a.expected, encoding="utf-8").read() if a.expected else None
    try:
        from nv_ingest_api.internal.primitives.nim.model_interface.ocr import NemoRetrieverOCRModelInterface
        from nv_ingest_api.util.nim import create_inference_client
        iface = NemoRetrieverOCRModelInterface()
        client = create_inference_client((None, a.endpoint), iface, auth_token=None, infer_protocol="http")
        rec["client"] = {"interface": type(iface).__name__, "client_class": type(client).__name__, "protocol_of_the_client": getattr(client, "protocol", None), "built": True}
    except Exception as e:
        rec["client"] = {"built": False, "exception": type(e).__name__, "message": str(e)[:400], "last_frames": traceback.format_exc().strip().splitlines()[-3:]}
        client = None
    b64 = base64.b64encode(raw).decode()
    for _ in range(a.calls if client is not None else 0):
        t = time.perf_counter(); c = {"start": now()}
        try:
            out = client.infer(data={"base64_images": [b64]}, model_name=a.model_name, input_names=["INPUT_IMAGE_URLS", "MERGE_LEVELS"], output_names=["OUTPUT"],
                               dtypes=["BYTES", "BYTES"], merge_level="word", max_batch_size=2)
            c["seconds"] = round(time.perf_counter() - t, 3); c["returned"] = True
            first = out[0] if isinstance(out, (list, tuple)) and out else out
            texts = []
            if isinstance(first, (list, tuple)) and len(first) >= 2 and isinstance(first[1], (list, tuple)):
                texts = [str(x) for x in first[1]]
            c["shape_of_the_result"] = {"outer": type(out).__name__, "outer_len": len(out) if hasattr(out, "__len__") else None, "first": type(first).__name__,
                                        "first_len": len(first) if hasattr(first, "__len__") else None}
            joined = "".join(texts)
            c.update({"text_pieces": len(texts), "characters": len(joined), "text_sha256": hashlib.sha256(joined.encode("utf-8")).hexdigest(), "first_characters": joined[: a.show]})
            if expected is not None:
                c["against_the_known_text"] = {"cjk": found(expected, joined, "cjk"), "latin_letters_and_digits": found(expected, joined, "latin")}
        except Exception as e:
            c.update({"seconds": round(time.perf_counter() - t, 3), "returned": False, "exception": type(e).__name__, "message": str(e)[:400],
                      "last_frames": traceback.format_exc().strip().splitlines()[-3:]})
        rec["calls"].append(c)
    rec["all_calls_returned_text"] = bool(rec["calls"]) and all(c.get("returned") and c.get("text_pieces", 0) > 0 for c in rec["calls"])
    rec["program"] = {"file": "ocr_client_check.py", "sha256": hashlib.sha256(open(os.path.abspath(__file__), "rb").read()).hexdigest()}
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump(rec, open(a.out, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    print(json.dumps({"client_built": rec["client"].get("built"), "all_calls_returned_text": rec["all_calls_returned_text"],
                      "calls": [{k: c.get(k) for k in ("returned", "seconds", "text_pieces", "characters", "exception", "against_the_known_text")} for c in rec["calls"]]}, ensure_ascii=False))
    return 0 if rec["all_calls_returned_text"] else 3


if __name__ == "__main__":
    sys.exit(main())
