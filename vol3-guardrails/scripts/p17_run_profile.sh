#!/usr/bin/env bash
# P17 · one profile run in a fresh NIM container (cell ④ NIM stack, no Guardrails).
# usage: p17_run_profile.sh <C|S|R> [fresh128|fresh256]
#   main run: levels 1,4,16,32,64,128,256,512 (512 = one step above max_num_seqs 256)
#   freshNNN: profile R only, one level in a new container, same duration as that level in the main run
# env: NGC_ENV_FILE · NIM_CACHE_DIR · AIPERF (aiperf executable) · APY (python of the AIPerf venv) · P17_DATA (data dir with tokenizer)
set -u
cd "$(dirname "$0")/../.."
P=$1; VAR=${2:-main}
BASE=vol1b/results/p17_concurrency/$P; PRED=$BASE/prediction_$P.json
TOK="${P17_DATA:?}/tokenizer_llama31_8b"; CAL=vol1b/results/p17_concurrency/calibration/calibration_verdict.json
case $VAR in
  main) LEVELS="1,4,16,32,64,128,256,512"; OUT=$BASE/main; FIRST=60 ;;
  fresh128|fresh256)
    [ "$P" = R ] || { echo "fresh runs are for profile R only"; exit 2; }
    L=${VAR#fresh}; LEVELS=$L; OUT=$BASE/$VAR
    FIRST=$("${APY:?}" -c "import json,sys;print(next(json.loads(l)['duration_s'] for l in open('$BASE/main/levels.jsonl') if json.loads(l)['concurrency']==$L))") \
      || { echo "main run level $L not found"; exit 2; } ;;
  *) echo "usage: p17_run_profile.sh C|S|R [fresh128|fresh256]"; exit 2 ;;
esac
echo "run P17 $P $VAR · $(date +%FT%T%z)"
(cd $BASE && sha256sum -c prediction_$P.sha256) || { echo "PREDICTION-MISSING-OR-CHANGED"; exit 2; }
[ ! -f "$OUT/levels.jsonl" ] || { echo "RESULT EXISTS for $P $VAR — one run only"; exit 2; }
mkdir -p "$OUT"
bash vol1b/scripts/p17_container.sh start nim-p17-$P-$VAR "$OUT/container" || { bash vol1b/scripts/p17_container.sh stop nim-p17-$P-$VAR "$OUT/container"; exit 1; }
"$APY" vol1b/scripts/p17_sweep.py --profile $P --levels $LEVELS --out "$OUT" --aiperf "${AIPERF:?}" --tokenizer "$TOK" --data-dir "$P17_DATA" --first-duration $FIRST
rc=$?
echo "sweep rc=$rc $(date +%FT%T%z)"
bash vol1b/scripts/p17_container.sh stop nim-p17-$P-$VAR "$OUT/container"
"$APY" vol1b/scripts/p17_analyze.py "$OUT" --calibration $CAL > "$OUT/analyze.stdout.txt" 2>&1
echo "analyze rc=$? $(date +%FT%T%z)"
exit $rc
