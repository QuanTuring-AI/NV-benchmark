"""Tests of the pure parts of scripts/safety_guard_nim_rail.py: the class of an item from its own rail decision and its
own verdict, the second reading of the worker's lines in the JSON shape, and the refusals. No server and no model:
what a real NIM answers is settled by the prechecks of each arm."""
import hashlib, json, os, sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import safety_guard_nim_rail as rail  # noqa: E402


def sha(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


@pytest.mark.parametrize("rail_decision,verdict,status,want", [
    ("block", "unsafe", "ok", "agree"), ("allow", "safe", "ok", "agree"),
    ("block", "safe", "ok", "block_but_verdict_safe"), ("allow", "unsafe", "ok", "allow_but_verdict_unsafe"),
    ("block:failed", "unsafe", "ok", "agree"), ("block", None, "truncated", "block_and_no_verdict_truncated"),
    ("allow", None, "unreadable", "allow_and_no_verdict_unreadable"), ("raise:ValueError", None, "unreadable", "raise_and_no_verdict_unreadable"),
    ("raise:ValueError", "safe", "ok", "raise_but_verdict_safe"), ("raise:ValueError", "unsafe", "ok", "raise_but_verdict_unsafe"),
    (None, "safe", "ok", "other_but_verdict_safe"),
])
def test_class_of_one_call(rail_decision, verdict, status, want):
    assert rail.same_call(rail_decision, verdict, status) == want


def lines(tmp_path, rows, raw):
    rp, wp = str(tmp_path / "rows.jsonl"), str(tmp_path / "raw.jsonl")
    open(rp, "w", encoding="utf-8").write("".join(json.dumps(r) + "\n" for r in rows))
    open(wp, "w", encoding="utf-8").write("".join(json.dumps(r) + "\n" for r in raw))
    return rp, wp


def test_verdicts_are_read_again_in_the_json_shape(tmp_path):
    full = '{"User Safety": "unsafe", "Safety Categories": "Violence"}'
    cut = '{"User Safety": "safe", "Response Safety": "safe", "Safety Categories": "Needs Caution, Oth'
    both = '{"User Safety": "unsafe", "Response Safety": "safe"}'
    rows = [{"item_id": "a", "rail": "block", "verdict": None, "status": "unreadable", "finish_reason": "stop", "completion_sha256": sha(full)},      # the worker read it in another shape
            {"item_id": "b", "rail": "block", "verdict": None, "status": "truncated", "finish_reason": "length", "completion_sha256": sha(cut)},
            {"item_id": "c", "rail": "allow", "verdict": None, "status": "unreadable", "finish_reason": "stop", "completion_sha256": sha("I cannot say.")}]
    raw = [{"item_id": "a", "content": full, "reasoning": ""}, {"item_id": "b", "content": cut, "reasoning": ""}, {"item_id": "c", "content": "I cannot say.", "reasoning": ""}]
    rp, wp = lines(tmp_path, rows, raw)
    got = {r["item_id"]: r for r in rail.reread(rp, wp, "input")}
    assert (got["a"]["verdict"], got["a"]["status"], got["a"]["same_call"]) == ("unsafe", "ok", "agree")
    assert (got["b"]["verdict"], got["b"]["status"], got["b"]["same_call"]) == ("safe", "ok", "block_but_verdict_safe")    # a cut answer the library cannot parse
    assert (got["c"]["verdict"], got["c"]["status"], got["c"]["same_call"]) == (None, "unreadable", "allow_and_no_verdict_unreadable")
    assert all(r["verdict_read_as"] == "json" for r in got.values())
    out = {r["item_id"]: r for r in rail.reread(*lines(tmp_path, [dict(rows[0], rail="allow", completion_sha256=sha(both))], [{"item_id": "a", "content": both, "reasoning": ""}]), "output")}
    assert out["a"]["verdict"] == "safe" and out["a"]["same_call"] == "agree"        # the output track reads the response's field


def test_a_stored_completion_that_is_not_the_hashed_one_is_refused(tmp_path):
    rp, wp = lines(tmp_path, [{"item_id": "a", "rail": "block", "finish_reason": "stop", "completion_sha256": sha("one")}], [{"item_id": "a", "content": "another", "reasoning": ""}])
    with pytest.raises(SystemExit):
        rail.reread(rp, wp, "input")


def test_a_line_without_a_completion_is_an_error_and_never_a_verdict(tmp_path):
    rp, wp = lines(tmp_path, [{"item_id": "a", "rail": "raise:RuntimeError", "verdict": None, "status": "error"},
                              {"item_id": "b", "rail": "allow", "verdict": "safe", "status": "ok", "completion_sha256": "0" * 64}], [])      # a verdict without a stored completion
    r, q = rail.reread(rp, wp, "input")
    assert r["verdict"] is None and r["status"] == "error" and r["same_call"] == "raise_and_no_verdict_error"
    assert q["verdict"] is None and q["status"] == "error" and q["same_call"] == "allow_and_no_verdict_error"


def test_the_prompts_file_must_be_the_one_named(tmp_path):
    good = hashlib.sha256(open(rail.PROMPTS, "rb").read()).hexdigest()
    rec = rail.write_config("some/model", str(tmp_path / "cfg"), {"guardrails": {"prompts_sha256": good}})
    assert rec["files"]["prompts.yml"] == good and rec["engine"] == "nim" and rec["max_tokens_in_prompts"] == 50
    cfg = open(tmp_path / "cfg" / "config.yml", encoding="utf-8").read()
    assert cfg.count("model: some/model") == 2 and "model_name" not in cfg and cfg.count("engine: nim") == 2
    assert open(tmp_path / "cfg" / "prompts.yml", "rb").read() == open(rail.PROMPTS, "rb").read()
    with pytest.raises(SystemExit):
        rail.write_config("some/model", str(tmp_path / "cfg2"), {"guardrails": {"prompts_sha256": "0" * 64}})
