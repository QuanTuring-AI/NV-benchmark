#!/usr/bin/env python3
"""Vol.4 · what the installed transformers does with the rotary-position settings of the open weights. CPU only: the
configuration is read and the rotary module is built; no weights are loaded and nothing is put on the card.

Why: while loading nvidia/Nemotron-3-Embed-1B-BF16, transformers prints that one key of the model's rope_parameters
(apply_yarn_scaling) is not recognised. This program shows what is computed nevertheless: how many of the rotary
frequencies differ from plain RoPE (that is, whether the YaRN interpolation is applied) and the factor applied to the
cos/sin tables (the YaRN magnitude correction; 1.0 means none).

usage: rope_check.py --model-path DIR --out FILE.json      (run it once per environment)
"""
import argparse, hashlib, io, json, logging, math, os

ap = argparse.ArgumentParser(); ap.add_argument("--model-path", required=True); ap.add_argument("--out", required=True)
a = ap.parse_args()
os.environ["CUDA_VISIBLE_DEVICES"] = ""          # nothing here needs the card
import torch, transformers  # noqa: E402
from transformers import AutoConfig  # noqa: E402
from transformers.models.ministral3.modeling_ministral3 import Ministral3RotaryEmbedding  # noqa: E402

buf = io.StringIO(); logging.getLogger("transformers").addHandler(logging.StreamHandler(buf))
cfg = AutoConfig.from_pretrained(a.model_path)
rot = Ministral3RotaryEmbedding(cfg)
head_dim = getattr(cfg, "head_dim", None) or cfg.hidden_size // cfg.num_attention_heads
plain = 1.0 / (cfg.rope_parameters["rope_theta"] ** (torch.arange(0, head_dim, 2, dtype=torch.int64).float() / head_dim))
ratio = rot.inv_freq / plain
factor = cfg.rope_parameters["factor"]
out = {"what": "the rotary-position parameters the installed transformers computes for this model's configuration (CPU, no weights loaded)",
       "versions": {"transformers": transformers.__version__, "torch": torch.__version__},
       "config_sha256": hashlib.sha256(open(os.path.join(a.model_path, "config.json"), "rb").read()).hexdigest(),
       "transformers_version_in_the_model_config": getattr(cfg, "transformers_version", None),
       "warning_lines_while_loading": sorted(set(l.strip() for l in buf.getvalue().splitlines() if l.strip())),
       "rope_parameters_as_loaded": {k: cfg.rope_parameters[k] for k in sorted(cfg.rope_parameters)},
       "frequencies": int(ratio.numel()), "equal_to_plain_rope": int((ratio - 1).abs().lt(1e-6).sum()),
       "divided_by_the_full_factor": int((ratio - 1 / factor).abs().lt(1e-6).sum()),
       "in_between": int(((ratio - 1).abs().ge(1e-6) & (ratio - 1 / factor).abs().ge(1e-6)).sum()),
       "factor_applied_to_cos_and_sin": float(rot.attention_scaling),
       "the_factor_yarn_would_apply_as_magnitude_correction": round(0.1 * math.log(factor) + 1, 6),
       "frequencies_sha256_of_float32_bytes": hashlib.sha256(rot.inv_freq.float().numpy().tobytes()).hexdigest()}
os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
json.dump(out, open(a.out, "w", encoding="utf-8", newline="\n"), indent=1)
print(json.dumps({k: out[k] for k in ("versions", "equal_to_plain_rope", "divided_by_the_full_factor", "in_between", "factor_applied_to_cos_and_sin", "warning_lines_while_loading")}))
