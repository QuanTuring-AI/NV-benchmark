# Llama Guard 3 timing cells, repeated on a quiet host: written before the run

Written at: 2026-10-04T03:59:44+0800
Card at this moment: 1151 MiB, 3 %, 31.98 W (memory in use, utilization, power); running containers: 0
Harness and pre-registration: unchanged from the first run (prediction SHA-256 59c3a03055b6f62688c031ab090f57b9cf76b1b167719b4b9e3fab56437317cf); repository HEAD d3e869f on vol3-wip

## Why

In the first run (2026-10-03, 23:00:18 to 23:02:26) the four timed cells of the Llama Guard 3 arm overlapped with short commands
this session started on the same host (web requests to other sites, small file reads, a listing of containers). None was a request
to the model server. Their effect on the durations was not measured.

## What is run

The step `lg3` of `p102_run.py`, twice, each time with a newly started container: per track the precheck, the c=1 cell (200 items)
and the c=16 cell (whole track). Same image digest, same weights, same items, same request shape, same idle-card gate.
Results go to `quiet_run_1/` and `quiet_run_2/` in this folder. Nothing in the committed results is overwritten.

Host rule for both runs: from the launch of the script to its exit, this session starts no command at all.
The owner of the machine said before the launch that the game was closed and the card was free for this.

## What is compared, and what was fixed before looking

One arm only (LG3). Three runs of the same four cells: the first run (host not left alone) and two quiet runs.

- Reported side by side for each run: c=1 p50 and p99 per verdict, c=16 verdicts per second, c=16 p50 and p99, per track.
- The two quiet runs give the only spread there is between two containers on a quiet host. Reading rule, fixed now:
  a figure of the first run that lies **inside** the interval spanned by the two quiet runs, or within 5% of its nearer end, is
  reported as "not distinguishable from a quiet run with these three runs"; one that lies further out is reported as
  "outside the two quiet runs", with the direction. Two runs are a thin spread, and that is said with the numbers.
- Expected if the host commands mattered: the first run's c=1 p50 and p99 are higher, and its c=16 verdicts per second lower,
  than both quiet runs. Expected if they did not: the first run lies inside or near the quiet interval.
- Verdicts: temperature 0.0. Per track, the share of items with the same outcome in each quiet c=16 cell as in the first run's
  c=16 cell is counted (the same arm judged again; no other arm is involved). Expected: all, or all but a handful.
- Positive control of the comparison itself: the c=16 cell must be several times faster in verdicts per second than the c=1 cell
  in every run (the first run: 98.1 against 16.8 on the input track); a comparison program that cannot show that difference
  cannot be trusted to show a smaller one.
- No figure of this repeat replaces a pre-registered figure. Whether any of it goes into the repository is not decided here.
