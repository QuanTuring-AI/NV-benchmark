#!/usr/bin/env python3
"""Vol.5 · C4: the card's used memory (nvidia-smi, as recorded in the cell's event file) for every configuration at
two moments: when the answer model reported ready, and when the configuration was complete (60 s later and after one
call to each service). Copies values from results/c4/events.jsonl; computes nothing but the difference.
usage: c4_card_used.py      writes results/c4/card_used.json
"""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__)); C4 = os.path.join(os.path.dirname(HERE), "results", "c4")
out, cur, total = {}, None, set()
for line in open(os.path.join(C4, "events.jsonl"), encoding="utf-8"):
    e = json.loads(line)
    if e.get("card"):
        total.add(e["card"]["total_mib"])
    if e["kind"] == "config_start":
        cur = e["name"]; out[cur] = {"started_at": e["at"], "embedder": e.get("embed") or "vl", "answer_model_setting": e.get("llm")}
    elif cur and e["kind"] == "service_verdict" and e.get("service") == "llm":
        out[cur]["at_answer_model_ready_mib"] = e["card_used_after_mib"]; out[cur]["ready_at"] = e["at"]
    elif cur and e["kind"] == "config_complete":
        out[cur]["at_configuration_complete_mib"] = e["card"]["used_mib"]; out[cur]["complete_at"] = e["at"]
        out[cur]["difference_mib"] = out[cur]["at_configuration_complete_mib"] - out[cur]["at_answer_model_ready_mib"]; cur = None
rec = {"what": "card used memory (nvidia-smi memory.used) per configuration, at the answer model's ready and at the configuration's completion",
       "source": "results/c4/events.jsonl (service_verdict of the answer model: card_used_after_mib; config_complete: card.used_mib)",
       "card_total_mib": total.pop() if len(total) == 1 else sorted(total), "configurations": out}
json.dump(rec, open(os.path.join(C4, "card_used.json"), "w", encoding="utf-8", newline="\n"), indent=1)
print(json.dumps({k: (v.get("at_answer_model_ready_mib"), v.get("at_configuration_complete_mib")) for k, v in out.items()}))
