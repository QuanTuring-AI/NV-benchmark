#!/usr/bin/env python3
"""Vol.4 · which transformers releases recognise the rope key `apply_yarn_scaling`, and where the code that computes the
YaRN parameters of the Ministral3 model class changed. Reads three source files of each release tag from GitHub; nothing
is installed and no GPU is used.

For every tag: is the model class present, does the key name occur in any of the three files, and the SHA-256 of
  - the function _compute_yarn_parameters with comments, docstring and blank lines removed,
  - the classes Ministral3RotaryEmbedding and Ministral3Attention,
  - the whole file modeling_ministral3.py.
Equal hashes in two releases mean equal code for that part.

usage: transformers_rope_scan.py --out FILE.json [--tags 5.0.0,5.1.0,...]
"""
import argparse, hashlib, json, re, sys, time, urllib.request

TAGS = ("4.57.6 5.0.0 5.1.0 5.2.0 5.3.0 5.4.0 5.5.0 5.5.1 5.5.4 5.6.0 5.7.0 5.8.0 5.8.1 5.9.0 5.10.1 5.11.0 5.12.0 5.12.1 "
        "5.13.0 5.13.1 5.14.0 5.15.0 5.16.0 5.17.0 5.18.0").split()
FILES = {"rope": "modeling_rope_utils.py", "model": "models/ministral3/modeling_ministral3.py", "config": "models/ministral3/configuration_ministral3.py"}
BASE = "https://raw.githubusercontent.com/huggingface/transformers/v{tag}/src/transformers/{path}"
KEY = "apply_yarn_scaling"


def fetch(tag, path):
    try:
        with urllib.request.urlopen(BASE.format(tag=tag, path=path), timeout=60) as r:
            return r.read().decode("utf-8")
    except Exception as e:   # a file that does not exist at a tag answers 404
        if "404" in str(e):
            return None
        sys.exit(f"error: {tag} {path}: {e}")


def h(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16] if text else None


def code_only(src, name):
    m = re.search(r"^def %s\(.*?(?=^def |\Z)" % name, src or "", re.S | re.M)
    if not m:
        return None
    body = re.sub(r'"""(.*?)"""', "", m.group(0), flags=re.S)
    return "\n".join(l.split("#")[0].rstrip() for l in body.splitlines() if l.split("#")[0].strip())


def klass(src, name):
    m = re.search(r"^class %s\b.*?(?=^class |\Z)" % name, src or "", re.S | re.M)
    return m.group(0) if m else None


ap = argparse.ArgumentParser(); ap.add_argument("--out", required=True); ap.add_argument("--tags")
a = ap.parse_args()
rows = []
for tag in (a.tags.split(",") if a.tags else TAGS):
    src = {k: fetch(tag, p) for k, p in FILES.items()}
    rows.append({"tag": tag, "model_class_present": bool(src["model"] and "Ministral3" in src["model"]),
                 "key_name_occurs": any(KEY in (s or "") for s in src.values()),
                 "yarn_function_code_sha256_16": h(code_only(src["rope"], "_compute_yarn_parameters")),
                 "rotary_class_sha256_16": h(klass(src["model"], "Ministral3RotaryEmbedding")),
                 "attention_class_sha256_16": h(klass(src["model"], "Ministral3Attention")),
                 "model_file_sha256_16": h(src["model"]), "config_file_sha256_16": h(src["config"])})
    print(rows[-1]["tag"], rows[-1]["key_name_occurs"], rows[-1]["yarn_function_code_sha256_16"], rows[-1]["model_file_sha256_16"], flush=True)
out = {"what": "source of transformers release tags, read from GitHub", "read_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "source": BASE, "key": KEY, "files": FILES,
       "tags_where_the_key_name_occurs": [r["tag"] for r in rows if r["key_name_occurs"]], "tags": rows}
json.dump(out, open(a.out, "w", encoding="utf-8", newline="\n"), indent=1)
