#!/usr/bin/env python3
"""Vol.5 · the spill rule of the co-residence cell C4 (it replaces the 256 MiB rule of the second night, which the
reranker's own pinned host memory crossed with nothing paged out).

Before the set: each service alone on the idle card, its Windows 'GPU Adapter Memory' Shared Usage once it is ready and
steady (S_i: the median of the samples from 20 s after ready to the end of the alone run) and the change of the card's
used memory that its start caused (D_i, nvidia-smi).
In the set, a configuration has spilled if either holds:
  (1) the shared value rises above sum(S_i over the services started so far) + 512 MiB at any sample, or
  (2) a service's own start changes the card's used memory by less than half of its D_i (its allocation went to
      system memory instead of the card).
Both conditions are evaluated and written, whichever decides.

usage (importable): judge(alone, steps, shared) -> record
  alone   {service: {"shared_mib": S_i, "card_delta_mib": D_i}}
  steps   [{"service": name, "card_delta_mib": change at its start, "at_sample": index into shared}] in start order
  shared  [MiB, ...] the shared samples of the configuration, in time order
"""
import statistics

MARGIN_MIB, FRACTION = 512, 0.5


def steady_shared(samples, ready_index, skip=10):
    """S_i: the median of the samples from `skip` samples after ready (about 20 s at one sample per 2 s) to the end."""
    tail = samples[ready_index + skip:]
    if not tail:
        raise ValueError("no samples after the service became steady")
    return statistics.median(tail)


def judge(alone, steps, shared, margin=MARGIN_MIB, fraction=FRACTION):
    rise, started = [], []
    for k, step in enumerate(steps):
        started.append(step["service"])
        end = steps[k + 1]["at_sample"] if k + 1 < len(steps) else len(shared)
        allowed = sum(alone[s]["shared_mib"] for s in started) + margin
        window = shared[step["at_sample"]:end]
        if window and max(window) > allowed:
            rise.append({"after": step["service"], "allowed_mib": allowed, "peak_mib": max(window)})
    short = [{"service": st["service"], "card_delta_mib": st["card_delta_mib"], "alone_mib": alone[st["service"]]["card_delta_mib"]}
             for st in steps if st["card_delta_mib"] < fraction * alone[st["service"]]["card_delta_mib"]]
    return {"rule": f"spilled if shared > sum(S_i of the services started) + {margin} MiB, or a start changes the card by less than {fraction:.0%} of the same start alone",
            "shared_above_allowed": rise, "starts_below_half": short, "spilled": bool(rise or short)}
