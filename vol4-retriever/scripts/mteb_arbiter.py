#!/usr/bin/env python3
"""Vol.4 · the arbiter of the reference arm: MTEB itself (source tag 2.14.3) on one language of
MIRACLRetrievalHardNegatives, with the same weights and the same loader arguments as the published result's metadata.

Written after the pre-registration was frozen; the pre-registration names this run (branch b of the reference arm)
but not this file. Its SHA-256 is written to the events file before its first use.

The model is not in the registry of MTEB 2.14.3, so it is built the way the published model_meta.json describes:
loader SentenceTransformerEncoderWrapper, loader_kwargs {processor_kwargs: {model_max_length: 4096}, device: cuda}.
Nothing else is set; prompts, pooling and normalisation are the model's own. batch_size is passed as encode_kwargs.

usage: mteb_arbiter.py --model-path DIR --subset zh --batch 16 --out FILE.json [--cache DIR]
"""
import argparse, hashlib, json, os, sys, time


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-path", required=True); ap.add_argument("--subset", default="zh"); ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--out", required=True); ap.add_argument("--cache", required=True)
    a = ap.parse_args()
    if os.path.exists(a.out):
        raise SystemExit(f"refused: {a.out} exists")
    import datasets, mteb, sentence_transformers, torch, transformers
    from mteb.cache import ResultCache
    from mteb.models.sentence_transformer_wrapper import SentenceTransformerEncoderWrapper
    start = time.strftime("%Y-%m-%dT%H:%M:%S%z"); t0 = time.perf_counter()
    model = SentenceTransformerEncoderWrapper(model=a.model_path, revision=None, device="cuda", processor_kwargs={"model_max_length": 4096})
    st = model.model; p = next(st.parameters())
    task = mteb.get_task("MIRACLRetrievalHardNegatives", hf_subsets=[a.subset])
    res = mteb.evaluate(model, [task], encode_kwargs={"batch_size": a.batch}, cache=ResultCache(cache_path=a.cache), overwrite_strategy="always", show_progress_bar=False)
    tr = res.task_results[0]
    rows = tr.scores["dev"]
    row = next(r for r in rows if r["hf_subset"] == a.subset)
    out = {"what": "MTEB itself on one language, as the arbiter between this repository's path and the published value", "start": start, "end": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
           "seconds": round(time.perf_counter() - t0, 1), "task": tr.task_name, "subset": a.subset, "split": "dev", "dataset_revision": tr.dataset_revision, "mteb_version_in_result": tr.mteb_version,
           "versions": {"mteb": mteb.__version__, "torch": torch.__version__, "sentence-transformers": sentence_transformers.__version__, "transformers": transformers.__version__, "datasets": datasets.__version__},
           "loader": "SentenceTransformerEncoderWrapper(model=<path>, revision=None, device='cuda', processor_kwargs={'model_max_length': 4096})", "encode_kwargs": {"batch_size": a.batch},
           "model": {"safetensors_sha256": sha256_file(os.path.join(a.model_path, "model.safetensors")), "parameter_dtype": str(p.dtype), "max_seq_length": st.max_seq_length, "prompts": dict(st.prompts),
                     "gpu": torch.cuda.get_device_name(0)},
           "scores": {k: row[k] for k in ("main_score", "ndcg_at_10", "ndcg_at_5", "recall_at_5", "recall_at_10", "recall_at_100", "recall_at_1000", "mrr_at_10") if k in row},
           "program": {"file": "mteb_arbiter.py", "sha256": sha256_file(os.path.abspath(__file__))}}
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump(out, open(a.out, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    print(json.dumps(out["scores"]))


if __name__ == "__main__":
    sys.exit(main())
