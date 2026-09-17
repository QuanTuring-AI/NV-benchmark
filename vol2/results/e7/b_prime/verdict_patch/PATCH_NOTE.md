# Post-run patch to bprime_verdict.py · written 2026-09-14T11:59:12+0800

- The registered script (sha256 recorded in prediction_bprime.json → harness_sha256) is kept unchanged as `bprime_verdict_as_registered.py.txt` in this directory; its hash was re-checked and matches the registration.
- The run itself (bprime_cohabit.py, gpu_counters.ps1, run_bprime.sh) was **not** changed. Measurement finished with harness rc=0.
- The registered verdict script **crashed before writing any verdict** (traceback in logs/bprime_20260914T113205/verdict.stderr.txt): the sampler writes timestamps with 7 fractional-second digits (PowerShell "o" format) and Python 3.10 `fromisoformat` rejects them.
- Patch (`patch.diff`, 9 changed lines): truncate the fraction to 6 digits before parsing, and make the self-test generate timestamps in the sampler's real 7-digit format. **No verdict rule, threshold, or matrix is changed; all rules are read from the frozen prediction file.**
- Checks after patching: self-test passes; removing the truncation makes 4 self-test cases fail with the original ValueError; a real sampler row parses.
- Why the tests missed it: the mock run never identified a NIM process, so it returned before the sampler-timestamp code; the self-test built timestamps with Python's own isoformat (6 digits).
