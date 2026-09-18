"""P17 input files. usage: p17_build_datasets.py <tokenizer_dir> <data_dir> <summary_json>
S: CNN-DailyMail 3.0.0 validation (13,368 articles, the MLPerf Inference Llama 3.1-8B datacenter set), each article wrapped in
   the MLPerf instruction template. Written as an AIPerf single_turn JSONL ({"text": ...}); the chat endpoint then applies
   the model's chat template on the server (MLPerf sends the raw prompt to a completions endpoint; listed as a deviation).
CAL: 10 fixed prompts for the instrument check, the same file for AIPerf and for the requests client.
Token counts use the Llama 3.1 8B tokenizer files from the NIM model cache (no network)."""
import hashlib, json, os, statistics, sys
import datasets
from transformers import AutoTokenizer

tok_dir, data_dir, summary_path = sys.argv[1:4]
os.makedirs(data_dir, exist_ok=True)
tok = AutoTokenizer.from_pretrained(tok_dir)
TEMPLATE = ("Summarize the following news article in 128 tokens. Please output the summary only, without any other text."
            "\n\nArticle:\n{input}\n\nSummary:")


def pct(v, p):
    s = sorted(v); return s[min(len(s) - 1, int(round(p / 100 * (len(s) - 1))))]


def write(name, texts):
    path = os.path.join(data_dir, name)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for t in texts:
            f.write(json.dumps({"text": t}, ensure_ascii=False) + "\n")
    return path, hashlib.sha256(open(path, "rb").read()).hexdigest()


ds = datasets.load_dataset("abisee/cnn_dailymail", "3.0.0", split="validation")
s_texts = [TEMPLATE.format(input=a) for a in ds["article"]]
raw = [len(tok.encode(t, add_special_tokens=True)) for t in s_texts]
chat = [len(tok.encode(tok.apply_chat_template([{"role": "user", "content": t}], add_generation_prompt=True, tokenize=False),
                       add_special_tokens=False)) for t in s_texts]
s_path, s_sha = write("S_cnn_dailymail_validation_mlperf_template.jsonl", s_texts)

qs = json.load(open("benchmark/questions.json", encoding="utf-8"))
cal_texts = [q["text"] for q in qs[:10]]
c_path, c_sha = write("CAL_questions_first10.jsonl", cal_texts)

summary = {
    "S": {"source": "HuggingFace abisee/cnn_dailymail, config 3.0.0, split validation", "rows": len(s_texts),
          "dataset_fingerprint": ds._fingerprint, "template": TEMPLATE, "file": os.path.basename(s_path), "sha256": s_sha,
          "isl_raw_prompt_tokens": {"avg": round(statistics.mean(raw), 1), "p50": pct(raw, 50), "p99": pct(raw, 99), "max": max(raw)},
          "isl_with_chat_template_tokens": {"avg": round(statistics.mean(chat), 1), "p50": pct(chat, 50), "p99": pct(chat, 99), "max": max(chat)},
          "note": "MLPerf reports mean ISL 778 for its preprocessed set; the averages above are our own count over all 13,368 "
                  "validation articles with no filtering or truncation. No articles are dropped to match 778."},
    "CAL": {"source": "benchmark/questions.json first 10 questions", "file": os.path.basename(c_path), "sha256": c_sha},
    "tokenizer_dir_files_sha256": {fn: hashlib.sha256(open(os.path.join(tok_dir, fn), "rb").read()).hexdigest()
                                   for fn in ("tokenizer.json", "tokenizer_config.json") if os.path.exists(os.path.join(tok_dir, fn))},
}
json.dump(summary, open(summary_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps(summary, ensure_ascii=False, indent=1))
