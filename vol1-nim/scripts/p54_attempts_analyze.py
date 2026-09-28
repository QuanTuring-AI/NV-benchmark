#!/usr/bin/env python3
"""Vol.1-A revisit, item B (p54_engine.py attempts) · summary. Rules frozen in prediction_p54_engine.json.

Per arm, from attempts.jsonl: the number of start attempts up to and including the first one that is READY and serves
the probe; the settings passed on that attempt (count and list); every failed attempt with its settings and its first
error line verbatim; seconds per attempt (listed, not summed into a conclusion: a second walk of a known ladder is
always faster than a first, so time is not a product property). From v_args.json: the settings each arm carries in the
measured configuration, counted the same way (a NIM variable = 1; a vLLM option = 1 whatever its value; the model
path is not counted, both arms need one; arm V's two usage-statistics variables and its cache-parity mount and variable
are listed apart, they are not needed to start).
usage: p54_attempts_analyze.py <run_dir> [--out FILE] | --self-test
"""
import json, os, sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def count_options(args):
    return sum(1 for t in args if t.startswith("--"))


def count_settings(flags):
    """A NIM or engine variable ('NAME=value') = 1; a vLLM option = 1 whatever its value (the value token is not counted)."""
    return sum(1 for f in flags if f.startswith("--") or ("=" in f and not f.startswith("-")))


def summarise(rows, vargs):
    out = {"arms": {}}
    dr = [r for r in rows if r.get("kind") == "dryrun"]
    out["n_profile_pin_needed"] = dr[0].get("profile_pin_needed") if dr else None
    out["n_auto_selected_profile"] = dr[0].get("selected_profile") if dr else None
    for arm in ("N", "V"):
        st = [r for r in rows if r.get("kind") == "start" and r.get("arm") == arm]
        first = next((i for i, r in enumerate(st) if r.get("result") == "READY"), None)
        out["arms"][arm] = {
            "attempts_total": len(st),
            "attempts_to_first_ready": (first + 1) if first is not None else None,
            "reached_ready": first is not None,
            "settings_at_first_ready": st[first]["flags"] if first is not None else None,
            "settings_count_at_first_ready": count_settings(st[first]["flags"]) if first is not None else None,
            "failed_attempts": [{"step": r.get("step"), "settings": r.get("flags"), "result": r.get("result"), "reason": r.get("reason"),
                                 "first_error_line": r.get("first_error_line")} for r in st if r.get("result") != "READY"],
            "seconds_per_attempt": [r.get("seconds") for r in st],
        }
    if vargs:
        n_env = vargs.get("n_env") or {}
        v_env = vargs.get("v_env") or {}
        v_args = vargs.get("v_args") or []
        out["measured_configuration"] = {
            "N": {"settings": [f"{k}={v}" for k, v in n_env.items()], "count": len(n_env)},
            "V": {"settings": [f"{k}={v}" for k, v in v_env.items()] + v_args, "count": len(v_env) + count_options(v_args),
                  "not_counted_usage_statistics_off": vargs.get("v_privacy_env"), "not_counted_cache_parity": vargs.get("v_parity_env")},
            "V_derivation": "NIM's own vLLM argument list (nim-serve --dry-run of N's measured configuration), model path and port edited only",
            "V_edits": vargs.get("v_edits"),
        }
    return out


def self_test():
    rows = [{"kind": "dryrun", "arm": "N", "selected_profile": "p", "profile_pin_needed": False},
            {"kind": "start", "arm": "N", "step": 0, "flags": [], "flag_count": 0, "result": "failed", "first_error_line": "ValueError: x", "seconds": 60},
            {"kind": "start", "arm": "N", "step": 1, "flags": ["NIM_MAX_MODEL_LEN=8192"], "flag_count": 1, "result": "READY", "seconds": 120},
            {"kind": "start", "arm": "V", "step": 0, "flags": [], "flag_count": 0, "result": "READY", "seconds": 90}]
    rows_v2 = rows[:3] + [{"kind": "start", "arm": "V", "step": 2, "flags": ["VLLM_USE_V2_MODEL_RUNNER=0", "--max-model-len", "8192"], "flag_count": 3, "result": "READY", "seconds": 90}]
    va = {"n_env": {"NIM_MODEL_PROFILE": "p", "NIM_MAX_MODEL_LEN": "8192"}, "v_env": {"VLLM_USE_V2_MODEL_RUNNER": "0"},
          "v_args": ["--served-model-name", "m", "--max-model-len", "8192", "--enable-prefix-caching"], "v_privacy_env": {"VLLM_NO_USAGE_STATS": "1"}}
    s = summarise(rows, va)
    cases = [("N took 2 attempts", s["arms"]["N"]["attempts_to_first_ready"] == 2),
             ("N one setting at READY", s["arms"]["N"]["settings_count_at_first_ready"] == 1),
             ("N failure listed with its error line", s["arms"]["N"]["failed_attempts"][0]["first_error_line"] == "ValueError: x"),
             ("V first attempt", s["arms"]["V"]["attempts_to_first_ready"] == 1 and s["arms"]["V"]["settings_count_at_first_ready"] == 0),
             ("measured N count 2", s["measured_configuration"]["N"]["count"] == 2),
             ("measured V count = 1 env + 3 options", s["measured_configuration"]["V"]["count"] == 4)]
    cases.append(("an option and its value count once", summarise(rows_v2, va)["arms"]["V"]["settings_count_at_first_ready"] == 2))
    rows2 = [r for r in rows if not (r.get("arm") == "N" and r.get("step") == 1)]
    cases.append(("no READY -> None, not a count", summarise(rows2, va)["arms"]["N"]["attempts_to_first_ready"] is None))
    for n, ok in cases:
        print(("PASS " if ok else "FAIL ") + n)
    return 0 if all(ok for _, ok in cases) else 1


def main():
    if sys.argv[1:] == ["--self-test"]:
        return self_test()
    d = sys.argv[1]
    rows = [json.loads(l) for l in open(os.path.join(d, "attempts.jsonl"), encoding="utf-8")]
    vp = os.path.join(d, "v_args.json")
    s = summarise(rows, json.load(open(vp, encoding="utf-8")) if os.path.exists(vp) else None)
    out = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else os.path.join(d, "attempts_summary.json")
    json.dump(s, open(out, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    print(json.dumps(s, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
