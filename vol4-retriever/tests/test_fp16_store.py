"""fp16_store.py: a 16-bit copy of stored vectors that still proves the 32-bit files it came from. A tiny made-up corpus
on disk with a checkpoint file as the encoder writes it; no data set, no model and no card."""
import argparse, hashlib, io, json, os, sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import fp16_store as F  # noqa: E402


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def exact(rows, seed):
    """float32 values that are exactly 16-bit floats."""
    return np.random.default_rng(seed).uniform(-0.1, 0.1, size=(rows, 8)).astype(np.float16).astype(np.float32)


def corpus(tmp_path, pieces=(exact(5, 1), exact(3, 2))):
    src = tmp_path / "src"; src.mkdir(); lines = []; first = 0
    for k, a in enumerate(pieces):
        vf, idf = f"corpus-{k:05d}.npy", f"ids-{k:05d}.json"
        np.save(src / vf, a); (src / idf).write_text(json.dumps([f"p{first + i}" for i in range(a.shape[0])]), encoding="utf-8")
        lines.append({"kind": "piece", "piece": k, "first": first, "passages": int(a.shape[0]), "vectors_file": vf, "vectors_sha256": sha(src / vf), "ids_file": idf, "ids_sha256": sha(src / idf)}); first += a.shape[0]
    np.save(src / "queries.npy", exact(2, 9)); (src / "query_ids.json").write_text(json.dumps(["q1", "q2"]), encoding="utf-8")
    lines += [{"kind": "queries", "queries_sha256": sha(src / "queries.npy")}, {"kind": "finished", "passages": first}]
    ck = tmp_path / "checkpoints.jsonl"; ck.write_text("\n".join(json.dumps(l) for l in lines) + "\n", encoding="utf-8")
    return str(src), str(ck)


def args(src, ck, tmp_path, min_free=0.0):
    return argparse.Namespace(emb_dir=src, checkpoints=ck, out_dir=str(tmp_path / "fp16"), list=str(tmp_path / "list" / "pieces.jsonl"), min_free_gib=min_free)


def test_sixteen_bits_and_back():
    a = exact(4, 3); h, ok = F.to_fp16(a)
    assert ok and h.dtype == np.float16
    b = a.copy(); b[2, 5] = np.float32(0.1)                                   # 0.1 is not a 16-bit float
    assert F.to_fp16(b)[1] is False


def test_the_rebuilt_file_is_the_original_file_byte_for_byte(tmp_path):
    a = exact(6, 4); p = tmp_path / "a.npy"; np.save(p, a)
    assert F.rebuilt_bytes(a.astype(np.float16)) == p.read_bytes()
    other = a.copy(); other[0, 0] += np.float32(0.25)
    assert F.rebuilt_bytes(other.astype(np.float16)) != p.read_bytes()


def test_convert_then_verify_from_the_copy_alone(tmp_path):
    src, ck = corpus(tmp_path); a = args(src, ck, tmp_path)
    before = {f: sha(os.path.join(src, f)) for f in os.listdir(src)}
    assert F.convert(a) == 0
    assert {f: sha(os.path.join(src, f)) for f in os.listdir(src)} == before                     # the source is only read
    rows = [json.loads(l) for l in open(a.list, encoding="utf-8")]
    assert [r["kind"] for r in rows] == ["start", "piece", "piece", "finished"]
    for r in rows[1:3]:
        f = os.path.join(a.out_dir, r["vectors_file"])
        assert np.load(f).dtype == np.float16 and r["sha256_of_the_16_bit_file"] == sha(f) and r["sha256_of_the_32_bit_file"] == before[r["vectors_file"]]
        assert r["values_equal_read_back_from_disk"] and r["rebuilt_32_bit_file_has_the_recorded_sha256"] and r["bytes_of_the_16_bit_file"] < r["bytes_of_the_32_bit_file"]
        assert sha(os.path.join(a.out_dir, r["ids_file"])) == before[r["ids_file"]]
    assert rows[3]["pieces"] == 2 and rows[3]["passages"] == 8 and sha(os.path.join(a.out_dir, "queries.npy")) == before["queries.npy"]
    assert F.verify(argparse.Namespace(fp16_dir=a.out_dir, checkpoints=ck)) == 0
    v, _ = F.piece_from_fp16(os.path.join(a.out_dir, "corpus-00000.npy"), before["corpus-00000.npy"])
    assert v.dtype == np.float32 and np.array_equal(v, np.load(os.path.join(src, "corpus-00000.npy")))


def test_a_second_call_goes_on_and_writes_nothing_twice(tmp_path):
    src, ck = corpus(tmp_path); a = args(src, ck, tmp_path)
    assert F.convert(a) == 0 and F.convert(a) == 0
    kinds = [json.loads(l)["kind"] for l in open(a.list, encoding="utf-8")]
    assert kinds.count("piece") == 2 and kinds.count("start") == 1


def test_a_value_that_is_not_sixteen_bits_stops_the_piece(tmp_path, capsys):
    bad = exact(3, 2); bad[1, 1] = np.float32(0.1)
    src, ck = corpus(tmp_path, pieces=(exact(5, 1), bad)); a = args(src, ck, tmp_path)
    with pytest.raises(SystemExit) as e:
        F.convert(a)
    assert e.value.code == 2 and os.path.isfile(os.path.join(a.out_dir, "corpus-00000.npy")) and not os.path.exists(os.path.join(a.out_dir, "corpus-00001.npy"))
    assert [json.loads(l)["kind"] for l in open(a.list, encoding="utf-8")] == ["start", "piece"]
    err = capsys.readouterr().err
    assert "nothing was written for this piece" in err and "was removed" not in err          # stopped before the write, not by the check after it


def test_a_changed_source_piece_is_refused(tmp_path, capsys):
    src, ck = corpus(tmp_path); np.save(os.path.join(src, "corpus-00000.npy"), exact(5, 77))
    with pytest.raises(SystemExit):
        F.convert(args(src, ck, tmp_path))
    assert not os.path.exists(os.path.join(str(tmp_path / "fp16"), "corpus-00000.npy"))
    assert "was removed" not in capsys.readouterr().err                                      # refused at the source, before anything was written


def test_a_changed_id_file_is_refused(tmp_path):
    src, ck = corpus(tmp_path)
    with open(os.path.join(src, "ids-00001.json"), "w", encoding="utf-8") as f:
        json.dump(["x", "y", "z"], f)
    with pytest.raises(SystemExit):
        F.convert(args(src, ck, tmp_path))


def test_a_changed_copy_fails_the_proof(tmp_path):
    src, ck = corpus(tmp_path); a = args(src, ck, tmp_path); assert F.convert(a) == 0
    f = os.path.join(a.out_dir, "corpus-00001.npy"); h = np.load(f); h[0, 0] = np.float16(float(h[0, 0]) + 0.25); np.save(f, h)
    with pytest.raises(SystemExit):
        F.verify(argparse.Namespace(fp16_dir=a.out_dir, checkpoints=ck))


def test_a_32_bit_file_in_the_16_bit_folder_is_refused(tmp_path):
    src, ck = corpus(tmp_path)
    with pytest.raises(SystemExit):
        F.read_fp16(os.path.join(src, "corpus-00000.npy"))


def test_too_little_free_space_stops_before_a_piece_is_written(tmp_path):
    src, ck = corpus(tmp_path); a = args(src, ck, tmp_path, min_free=1e9)
    assert F.convert(a) == 6 and not os.path.exists(os.path.join(a.out_dir, "corpus-00000.npy"))
    assert [json.loads(l)["kind"] for l in open(a.list, encoding="utf-8")] == ["start", "stopped"]


def test_the_copy_must_not_go_into_the_source_folder(tmp_path):
    src, ck = corpus(tmp_path); a = args(src, ck, tmp_path); a.out_dir = src
    with pytest.raises(SystemExit):
        F.convert(a)


def test_same_ranking_counts_order_and_missing_queries():
    ref = {"q1": ["a", "b", "c"], "q2": ["a", "b", "c"], "q3": ["a", "b", "c"], "q4": ["a", "b", "c"]}
    mine = {"q1": ["a", "b", "c"], "q2": ["b", "a", "c"], "q3": ["a", "b"]}
    r = F.same_ranking(ref, mine)
    assert r["queries"] == 4 and r["queries_with_the_same_passages_in_the_same_order"] == 1 and r["first_query_that_differs"] == "q2"


def test_read_run_orders_by_rank(tmp_path):
    f = tmp_path / "run.trec"; f.write_text("q1 Q0 b 2 0.5 t\nq1 Q0 a 1 0.9 t\n", encoding="utf-8")
    assert F.read_run(str(f)) == {"q1": ["a", "b"]}
