"""List tags and digests of an NGC container repository from inside a container.

Run with the NGC key supplied only through `docker run --env-file <path>`; this script never prints it.
Output: JSON with every tag and, for tags given in ONLY_DIGESTS (comma-separated, or 'all'),
the index digest (Docker-Content-Digest of the manifest list / OCI index) and the linux/amd64 manifest digest.
"""
import base64, json, os, sys, urllib.request, urllib.error

REPO = os.environ.get("REPO", "nim/meta/llama-3.1-8b-instruct")
ONLY = os.environ.get("ONLY_DIGESTS", "")
key = os.environ.get("NGC_API_KEY")
if not key:
    print(json.dumps({"error": "NGC_API_KEY not present in container env"})); sys.exit(2)

auth = base64.b64encode(("$oauthtoken:" + key).encode()).decode()
del key
# realm taken from the registry's own WWW-Authenticate header (unauthenticated request to nvcr.io/v2/)
req = urllib.request.Request(f"https://nvcr.io/proxy_auth?scope=repository:{REPO}:pull",
                             headers={"Authorization": "Basic " + auth})
token = json.load(urllib.request.urlopen(req, timeout=60))["token"]


def get(url, accept=None, method="GET"):
    h = {"Authorization": "Bearer " + token}
    if accept:
        h["Accept"] = accept
    r = urllib.request.urlopen(urllib.request.Request(url, headers=h, method=method), timeout=60)
    return r.headers, (r.read() if method == "GET" else b"")


tags, url = [], f"https://nvcr.io/v2/{REPO}/tags/list?n=1000"
while url:
    hdr, body = get(url)
    tags += json.loads(body).get("tags") or []
    link = hdr.get("Link")
    url = ("https://nvcr.io" + link.split(";")[0].strip("<> ")) if link else None

out = {"repo": REPO, "n_tags": len(tags), "tags": sorted(set(tags)), "digests": {}}
want = tags if ONLY == "all" else [t for t in ONLY.split(",") if t]
IDX = "application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json"
MAN = "application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json"
for t in want:
    try:
        hdr, body = get(f"https://nvcr.io/v2/{REPO}/manifests/{t}", accept=IDX + ", " + MAN)
        d = {"top_digest": hdr.get("Docker-Content-Digest"), "top_media_type": hdr.get("Content-Type")}
        j = json.loads(body)
        amd = [m for m in j.get("manifests", []) if (m.get("platform") or {}).get("architecture") == "amd64"]
        d["amd64_manifest_digest"] = amd[0]["digest"] if amd else (d["top_digest"] if "manifests" not in j else None)
        d["platforms"] = [f"{(m.get('platform') or {}).get('os')}/{(m.get('platform') or {}).get('architecture')}" for m in j.get("manifests", [])]
        if d["amd64_manifest_digest"]:
            _, mb = get(f"https://nvcr.io/v2/{REPO}/manifests/{d['amd64_manifest_digest']}", accept=MAN)
            mj = json.loads(mb)
            d["amd64_compressed_bytes"] = sum(l.get("size", 0) for l in mj.get("layers", []))
            cfg = mj["config"]["digest"]
            _, cb = get(f"https://nvcr.io/v2/{REPO}/blobs/{cfg}")
            c = json.loads(cb)
            env = {e.split("=", 1)[0]: e.split("=", 1)[1] for e in (c.get("config") or {}).get("Env", []) if "=" in e}
            d["created"] = c.get("created")
            d["labels"] = {k: v for k, v in ((c.get("config") or {}).get("Labels") or {}).items() if "version" in k.lower() or "created" in k.lower()}
            d["env_versions"] = {k: v for k, v in env.items() if any(s in k for s in ("NIM_VERSION", "VLLM_IMAGE_TAG", "BACKEND_TYPE", "CUDA_VERSION", "NIM_MODEL_NAME"))}
        out["digests"][t] = d
    except urllib.error.HTTPError as e:
        out["digests"][t] = {"error": f"HTTP {e.code}"}
print(json.dumps(out, indent=1))
