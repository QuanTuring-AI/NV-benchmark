# Known caveat · E9 (Nemotron Nano 9B v2 × NeMo Guardrails 0.23.0)

The Guardrails arm of this result was produced by a harness that created and closed a new asyncio event loop for every request.
In a later mock test (Vol.1-B bridge, 2026-09-15), NeMo Guardrails 0.23.0 logged a stale-event-loop retry on every request under that pattern
(0.21.0 did not), roughly doubling its latency against the same server. E9 did not record retry counts, so whether this happened here cannot be
confirmed retrospectively. The 0.23.0 overhead figures in `e9_analysis.json` and `e9_vs_0210_bootstrap.json` may therefore be overstated.
If they are, the true 0.23.0 overhead on this model is lower than reported, not higher. The result is not re-run; the harness used for later
Guardrails measurements keeps one persistent loop per process (`vol1b/scripts/gr_worker.py`).
