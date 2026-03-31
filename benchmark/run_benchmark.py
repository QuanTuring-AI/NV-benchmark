"""
NIM vs Ollama Benchmark Script — E2
QuanTuring Inc.

Metrics:
1. tokens_per_second (TPS)
2. time_to_first_token (TTFT) ms
3. total_latency ms
4. vram_usage_mb
"""

import json
import time
import requests
import subprocess
import sys
import os
from datetime import datetime

# Fix Windows console encoding for multilingual output
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# ── Configuration ────────────────────────────────────────
NIM_URL = "http://localhost:8000/v1/chat/completions"
NIM_MODEL = "meta-llama/llama-3.1-8b-instruct"
OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "llama3.1:8b"
MAX_TOKENS = 500
ROUNDS = 3
COOLDOWN = 2  # seconds between requests

QUESTIONS_FILE = os.path.join(os.path.dirname(__file__), "questions.json")
RESULTS_FILE = os.path.join(os.path.dirname(__file__), "results", "e2_nim_vs_ollama.json")
PROGRESS_FILE = os.path.join(os.path.dirname(__file__), "..", "progress.json")


def get_vram_mb():
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5
        )
        return int(result.stdout.strip())
    except Exception:
        return -1


def benchmark_nim(question: str) -> dict:
    payload = {
        "model": NIM_MODEL,
        "messages": [{"role": "user", "content": question}],
        "max_tokens": MAX_TOKENS,
        "stream": True
    }
    vram_before = get_vram_mb()
    start = time.perf_counter()
    first_token_time = None
    full_response = ""
    token_count = 0

    try:
        response = requests.post(NIM_URL, json=payload, stream=True, timeout=90)
        for line in response.iter_lines():
            if line:
                line = line.decode("utf-8")
                if line.startswith("data: ") and line != "data: [DONE]":
                    if first_token_time is None:
                        first_token_time = time.perf_counter()
                    try:
                        chunk = json.loads(line[6:])
                        delta = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                        if delta:
                            full_response += delta
                            token_count += len(delta.split())
                    except json.JSONDecodeError:
                        pass
        end = time.perf_counter()
    except Exception as e:
        return {"provider": "nim", "error": str(e)}

    vram_after = get_vram_mb()
    total_sec = end - start
    return {
        "provider": "nim",
        "ttft_ms": round((first_token_time - start) * 1000, 1) if first_token_time else None,
        "total_latency_ms": round(total_sec * 1000, 1),
        "tokens": token_count,
        "tps": round(token_count / total_sec, 1) if total_sec > 0 else 0,
        "vram_mb": vram_after,
        "response_preview": full_response[:150]
    }


def benchmark_ollama(question: str) -> dict:
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [{"role": "user", "content": question}],
        "stream": True,
        "options": {"num_predict": MAX_TOKENS}
    }
    vram_before = get_vram_mb()
    start = time.perf_counter()
    first_token_time = None
    full_response = ""
    token_count = 0

    try:
        response = requests.post(OLLAMA_URL, json=payload, stream=True, timeout=90)
        for line in response.iter_lines():
            if line:
                try:
                    chunk = json.loads(line)
                    content = chunk.get("message", {}).get("content", "")
                    if content:
                        if first_token_time is None:
                            first_token_time = time.perf_counter()
                        full_response += content
                        token_count += len(content.split())
                    if chunk.get("done"):
                        break
                except json.JSONDecodeError:
                    pass
        end = time.perf_counter()
    except Exception as e:
        return {"provider": "ollama", "error": str(e)}

    vram_after = get_vram_mb()
    total_sec = end - start
    return {
        "provider": "ollama",
        "ttft_ms": round((first_token_time - start) * 1000, 1) if first_token_time else None,
        "total_latency_ms": round(total_sec * 1000, 1),
        "tokens": token_count,
        "tps": round(token_count / total_sec, 1) if total_sec > 0 else 0,
        "vram_mb": vram_after,
        "response_preview": full_response[:150]
    }


def print_summary(results: dict):
    print("\n" + "=" * 60)
    print(f"  SUMMARY")
    print("=" * 60)
    for provider in ["nim", "ollama"]:
        data = [r for r in results[provider] if "error" not in r]
        if not data:
            print(f"  {provider.upper()}: no valid results")
            continue
        avg_tps = sum(d["tps"] for d in data) / len(data)
        ttft_data = [d["ttft_ms"] for d in data if d.get("ttft_ms")]
        avg_ttft = sum(ttft_data) / len(ttft_data) if ttft_data else 0
        avg_lat = sum(d["total_latency_ms"] for d in data) / len(data)
        avg_vram = sum(d["vram_mb"] for d in data if d["vram_mb"] > 0) / max(1, len(data))
        print(f"\n  {provider.upper()}")
        print(f"    Avg TPS:      {avg_tps:.1f} tok/s")
        print(f"    Avg TTFT:     {avg_ttft:.0f} ms")
        print(f"    Avg Latency:  {avg_lat:.0f} ms")
        print(f"    Avg VRAM:     {avg_vram:.0f} MB")
    print("=" * 60)
    if results["nim"] and results["ollama"]:
        nim_tps = sum(r["tps"] for r in results["nim"] if "error" not in r) / max(1, len([r for r in results["nim"] if "error" not in r]))
        oll_tps = sum(r["tps"] for r in results["ollama"] if "error" not in r) / max(1, len([r for r in results["ollama"] if "error" not in r]))
        if oll_tps > 0:
            print(f"\n  NIM speedup vs Ollama: {nim_tps/oll_tps:.2f}x TPS")


def run_full_benchmark():
    with open(QUESTIONS_FILE, encoding="utf-8") as f:
        questions = json.load(f)

    results = {
        "nim": [],
        "ollama": [],
        "metadata": {
            "gpu": "RTX 5090",
            "vram_total_mb": 32607,
            "nim_model": NIM_MODEL,
            "ollama_model": OLLAMA_MODEL,
            "rounds": ROUNDS,
            "max_tokens": MAX_TOKENS,
            "started": datetime.now().isoformat(),
            "completed": None
        }
    }

    # Load existing results if resuming
    if os.path.exists(RESULTS_FILE):
        try:
            with open(RESULTS_FILE, encoding="utf-8") as f:
                existing = json.load(f)
            results["nim"] = existing.get("nim", [])
            results["ollama"] = existing.get("ollama", [])
            print(f"Resuming: {len(results['nim'])} NIM, {len(results['ollama'])} Ollama results loaded")
        except Exception:
            pass

    completed_nim = {(r["question_id"], r["round"]) for r in results["nim"] if "question_id" in r}
    completed_ollama = {(r["question_id"], r["round"]) for r in results["ollama"] if "question_id" in r}

    total = len(questions) * ROUNDS
    done = 0

    for round_num in range(1, ROUNDS + 1):
        print(f"\n{'='*50}\n=== Round {round_num}/{ROUNDS} ===\n{'='*50}")
        for q in questions:
            done += 1
            pct = done / total * 100
            print(f"[{pct:.0f}%] Q{q['id']} ({q['category']}) R{round_num}: {q['text'][:60]}...")

            # NIM
            if (q["id"], round_num) not in completed_nim:
                nim_r = benchmark_nim(q["text"])
                nim_r["question_id"] = q["id"]
                nim_r["category"] = q["category"]
                nim_r["round"] = round_num
                results["nim"].append(nim_r)
                status = f"TPS={nim_r.get('tps','ERR')} TTFT={nim_r.get('ttft_ms','ERR')}ms"
                print(f"  NIM:    {status}")
                time.sleep(COOLDOWN)
            else:
                print(f"  NIM:    [skipped — already done]")

            # Ollama
            if (q["id"], round_num) not in completed_ollama:
                oll_r = benchmark_ollama(q["text"])
                oll_r["question_id"] = q["id"]
                oll_r["category"] = q["category"]
                oll_r["round"] = round_num
                results["ollama"].append(oll_r)
                status = f"TPS={oll_r.get('tps','ERR')} TTFT={oll_r.get('ttft_ms','ERR')}ms"
                print(f"  Ollama: {status}")
                time.sleep(COOLDOWN)
            else:
                print(f"  Ollama: [skipped — already done]")

            # Save progress after each question
            with open(RESULTS_FILE, "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2, ensure_ascii=False)

    results["metadata"]["completed"] = datetime.now().isoformat()
    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print_summary(results)
    print(f"\nResults saved to: {RESULTS_FILE}")
    return results


if __name__ == "__main__":
    run_full_benchmark()
