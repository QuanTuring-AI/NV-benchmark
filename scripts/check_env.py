"""
NIM Benchmark 環境驗證腳本
檢查 GPU、CUDA、Docker、Python 套件是否就緒
"""

import subprocess
import sys
import shutil


def check(name, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))
    return passed


def main():
    results = []
    print("=" * 60)
    print("  NIM Benchmark 環境檢查")
    print("=" * 60)

    # 1. nvidia-smi
    print("\n--- GPU ---")
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,driver_version",
             "--format=csv,noheader"],
            capture_output=True, text=True, timeout=10,
        )
        if out.returncode == 0:
            info = out.stdout.strip()
            results.append(check("nvidia-smi", True, info))
        else:
            results.append(check("nvidia-smi", False, out.stderr.strip()))
    except FileNotFoundError:
        results.append(check("nvidia-smi", False, "not found in PATH"))

    # 2. PyTorch CUDA
    print("\n--- PyTorch / CUDA ---")
    try:
        import torch
        cuda_ok = torch.cuda.is_available()
        if cuda_ok:
            gpu_name = torch.cuda.get_device_name(0)
            cuda_ver = torch.version.cuda
            results.append(check("torch.cuda", True,
                                 f"{gpu_name}, CUDA {cuda_ver}, torch {torch.__version__}"))
        else:
            results.append(check("torch.cuda", False,
                                 f"torch {torch.__version__} (CPU only?)"))
    except ImportError:
        results.append(check("torch.cuda", False, "torch not installed"))

    # 3. Key Python packages
    print("\n--- Python Packages ---")
    packages = [
        "requests", "aiohttp", "chromadb", "sentence_transformers",
        "fitz", "pandas", "matplotlib", "tqdm", "tabulate",
        "psutil", "dotenv",
    ]
    for pkg in packages:
        try:
            mod = __import__(pkg)
            ver = getattr(mod, "__version__", "ok")
            results.append(check(pkg, True, ver))
        except ImportError:
            results.append(check(pkg, False, "not installed"))

    # nemoguardrails (optional at E1 stage)
    try:
        import nemoguardrails
        ver = getattr(nemoguardrails, "__version__", "ok")
        results.append(check("nemoguardrails", True, ver))
    except ImportError:
        results.append(check("nemoguardrails", False, "not installed (needed for E3)"))

    # 4. Docker
    print("\n--- Docker ---")
    docker_path = shutil.which("docker")
    if docker_path:
        try:
            out = subprocess.run(["docker", "info"], capture_output=True,
                                 text=True, timeout=15)
            if out.returncode == 0:
                results.append(check("Docker", True, "daemon running"))
            else:
                results.append(check("Docker", False, "daemon not running?"))
        except Exception as e:
            results.append(check("Docker", False, str(e)))
    else:
        results.append(check("Docker", False, "not found in PATH"))

    # Docker GPU support
    try:
        out = subprocess.run(
            ["docker", "run", "--rm", "--gpus", "all",
             "nvidia/cuda:12.4.0-base-ubuntu22.04", "nvidia-smi"],
            capture_output=True, text=True, timeout=60,
        )
        if out.returncode == 0:
            results.append(check("Docker GPU (nvidia-container-toolkit)", True))
        else:
            results.append(check("Docker GPU (nvidia-container-toolkit)", False,
                                 out.stderr.strip()[:120]))
    except Exception as e:
        results.append(check("Docker GPU (nvidia-container-toolkit)", False, str(e)))

    # 5. Ollama
    print("\n--- Ollama ---")
    ollama_path = shutil.which("ollama")
    if ollama_path:
        results.append(check("Ollama binary", True, ollama_path))
    else:
        results.append(check("Ollama binary", False, "not found in PATH"))

    # Summary
    passed = sum(results)
    total = len(results)
    print("\n" + "=" * 60)
    print(f"  Result: {passed}/{total} checks passed")
    print("=" * 60)

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
