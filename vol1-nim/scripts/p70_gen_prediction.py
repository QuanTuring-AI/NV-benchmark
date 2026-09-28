#!/usr/bin/env python3
"""Vol.1 (renewed), P70 · write prediction_p70.json once, before the first measured cell.
Paths are derived from this file's location and from the imported modules' own files; no volume directory name is written
here. usage: p70_gen_prediction.py <written_at>"""
import glob, hashlib, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
import p59_nim_value as H  # noqa: E402  (imports the P53 profile definitions it uses)
import p59_analyze as A  # noqa: E402


def find(name):
    hits = [p for p in glob.glob(os.path.join(REPO, "*", "scripts", name)) if "_internal" not in p]
    assert len(hits) == 1, (name, hits)
    return hits[0]


sys.path.insert(0, os.path.dirname(find("prediction_guard.py")))
from prediction_guard import check_prediction  # noqa: E402

rel = lambda p: os.path.relpath(os.path.abspath(p), REPO).replace(os.sep, "/")
h = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
OUT = os.path.join(HERE, "..", "results", "p70_clean_recheck")
P59 = os.path.join(HERE, "..", "results", "p59_nim_value")
p59a = json.load(open(os.path.join(P59, "analysis.json"), encoding="utf-8"))
v = lambda arm, n: p59a["levels"][f"{arm}|C|main"][str(n)]["total_tps"]
harness = [os.path.join(HERE, f) for f in ("p70_clean_recheck.py", "p70_analyze.py", "run_p70.sh")] + [
    H.__file__, A.__file__, sys.modules["p53_concurrency"].__file__, find("p54_engine.py"), find("prediction_guard.py"),
    os.path.join(REPO, "tools", "g8_gate.py"), os.path.join(REPO, "tools", "overwrite_gate.py")]
p = {
 "experiment": "Vol.1 (renewed), P70 · the 128-request headline re-checked in a window with no other GPU load: Llama 3.1 8B Instruct on one RTX 5090, P59's four configurations (NIM 2.0.12 bf16 and fp8, Ollama 4-bit and fp16), profile C (200 / 200 tokens), 1, 32 and 128 concurrent requests.",
 "written_at": sys.argv[1],
 "written_before": "the first measured cell. run_p70.sh refuses to start if this file or its .sha256 is missing or changed, or if levels.jsonl exists.",
 "why": ("P59, the source of the Vol.1 headline (128 concurrent requests: NIM bf16 5,458 tok/s against the 4-bit Ollama build's 741, 7.4x), ran on "
         "2026-09-25 from 02:32 to 06:44 with other load on the desktop GPU: its levels ended at 3-23% utilization (median 5) and 45-70 W before "
         "they started, where a window with no other load ends at 0% (tools/g8_gate.py). The arms ran one after another, 30-60 minutes apart, so "
         "the background need not have been the same for both, nor have cost both the same share. The decision to re-measure is made from that "
         "fingerprint, before any clean number is seen."),
 "scope": "Profile C only, three levels, main containers. P59's harness is imported unchanged. This run changes no published file.",
 "stack": {"nim_image": "nvcr.io/nim/meta/llama-3.1-8b-instruct:2.0.12, image id sha256:d2c94c1d654c3e80b8bc08cc83298d2ba4e219dff41d1092555795edb93c6545 (as P59)",
           "ollama_image": "ollama/ollama:latest, image id sha256:8262851b2846b87c649eddf3e76beb270c52f4d1bc94559f47efde16b0841551 (as P59), Ollama 0.34.4",
           "nim_profiles": {"N-BF16": H.ARMS["N-BF16"]["profile"], "N-FP8": H.ARMS["N-FP8"]["profile"]},
           "ollama_models": {"O-Q4": H.ARMS["O-Q4"]["model"], "O-FP16": H.ARMS["O-FP16"]["model"]},
           "ollama_num_parallel": {"O-Q4": 16, "O-FP16": 8, "source": "P59's fitted values (events_public.jsonl container_start env), set directly instead of re-fitting"},
           "context": 8192, "nim_env": H.NIM_ENV, "driver": "591.86", "aiperf": "0.11.0"},
 "design": {"order": "one container per configuration: N-BF16 -> O-Q4 -> N-FP8 -> O-FP16, each running c = 1, 32, 128 in turn",
            "why_not_interleaved_by_c": "interleaving by c needs twelve container starts (six NIM loads of several minutes each) instead of four; every cell is gated by G8 immediately before it, which is what interleaving would protect against",
            "per_container": "isolation check, prefix-cache detector, discarded 120 s warm-up at c=1 (seed 20260925 + 9000), calibration (20 requests), as P59",
            "per_cell": "G8 (10 s at 1 Hz; util p50 <= 2 % and power p50 <= 45 W; retry every 60 s up to 15 min, else the cell is null); AIPerf C profile, 60 s, seed 20260925 + c, as P59; then the no-overwrite check (tools/overwrite_gate.py): tracked files unchanged and new files only under this run's directory, else the run stops and the cell is void",
            "g8_positive_control": "once, in the first NIM container after calibration: G8 sampled while 4 streams decode on the engine; it must not pass",
            "differences_from_p59_by_cell": "in P59 each container ran 1, 8, 16, 32, 64, 128 (and profile R after C); here 1, 32, 128. The Ollama slot counts are set to P59's fitted values instead of being re-fitted. Nothing else differs (images, profiles, models, context, AIPerf command, seeds, durations)."},
 "gates": {"arm": "P59's (p59_analyze.py): residency (Ollama 100% GPU; NIM CUDA graphs captured) and health (decode rate at c=1 x bytes per token / 1,792 GB/s >= 0.40)",
           "cell": "P59's cell checks plus G8 passed before it and the no-overwrite check passed after it"},
 "p59_values": {"total_tps_at_128": {a: v(a, 128) for a in ("N-BF16", "O-Q4", "N-FP8", "O-FP16")},
                "N-BF16/O-Q4_at_128": round(v("N-BF16", 128) / v("O-Q4", 128), 3), "N-FP8/O-Q4_at_128": round(v("N-FP8", 128) / v("O-Q4", 128), 3),
                "N-BF16/O-FP16_at_128": round(v("N-BF16", 128) / v("O-FP16", 128), 3), "N-BF16/O-Q4_at_1": round(v("N-BF16", 1) / v("O-Q4", 1), 3),
                "source": rel(os.path.join(P59, "analysis.json"))},
 "predictions": {
   "R1": "N-BF16 / O-Q4 total tok/s at 128 within 6.7-8.1 (7.4 +- 10%)",
   "R2": "N-FP8 / O-Q4 and N-BF16 / O-FP16 at 128 each within P59's value +- 10%",
   "R3": "at 1 request the 4-bit build is still faster than NIM bf16 (P59: N-BF16 / O-Q4 = 0.505)",
   "R4": "each cell's total tok/s is reported beside P59's same cell; no statement of the form 'the background slowed X by Y%' is made",
   "reading_of_predictions": "a failed prediction is reported as failed; nothing is re-run to chase a result"},
 "analysis_rules": {"program": f"{rel(os.path.join(HERE, 'p70_analyze.py'))} (10 self-test cases; each of 8 mutations -- the band, the tolerance, the G8, overwrite, arm-gate and P59 cell-check joins, a ratio's direction, R3's direction -- makes at least one fail), reading only the published files and P59's analysis.json"},
 "harness_sha256": {rel(f): h(f) for f in harness},
 "fixed_inputs_sha256": {rel(os.path.join(P59, "analysis.json")): h(os.path.join(P59, "analysis.json"))},
}
check_prediction(p)
path = os.path.join(OUT, "prediction_p70.json")
if os.path.exists(path):
    sys.exit("prediction exists -- a pre-registration is written once")
os.makedirs(OUT, exist_ok=True)
json.dump(p, open(path, "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=2)
print("written", os.path.relpath(path, REPO)); print(json.dumps(p["p59_values"])); print(list(p["harness_sha256"]))
