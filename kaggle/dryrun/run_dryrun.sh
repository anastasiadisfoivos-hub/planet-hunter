#!/usr/bin/env bash
# Dry run of kaggle/planet_hunter_nightly.ipynb in a clean Python container, the way Kaggle runs it:
#   - the notebook itself, executed top to bottom (jupyter nbconvert --execute), no Kaggle Secrets (the two
#     secrets come from the environment instead);
#   - it clones the public GitHub repository at REF and installs hunt, faint, vet, api with runner/sync-venvs.sh;
#   - it posts to the real API (api/, uvicorn on SQLite) served on this machine, which is polled every 30 s;
#   - /kaggle/working is a host folder (the "output"); /kaggle/input/<slug>/ is the previous session's output.
# Session 1 searches the star lists; session 2 loads session 1's output and gets the lists plus a few new stars
# (it must search only those); session 3 has no input and must stop at the guard without writing any output.
# Needs: Docker, uv. Usage: run_dryrun.sh <ref> <targets.csv> <faint.csv> <extra-targets.csv> <out-dir>
#        (SESSIONS="s3" runs only those sessions; KEEP_DB=1 keeps the API's database from the last dry run)
set -euo pipefail
REF="$1"; TARGETS="$2"; FAINT="$3"; EXTRA="$4"; OUT="$5"
HERE="$(cd "$(dirname "$0")" && pwd)"; REPO="$(cd "$HERE/../.." && pwd)"
PORT="${PORT:-8767}"; TOKEN=dry-token; IMAGE="${IMAGE:-python:3.11-bookworm}"
SESSION_H="${SESSION_H:-2}"; WRAP_H="${WRAP_H:-0.5}"
mkdir -p "$OUT/lists"
cp "$TARGETS" "$OUT/lists/targets.csv"; cp "$FAINT" "$OUT/lists/faint.csv"
{ cat "$TARGETS"; tail -n +2 "$EXTRA"; } > "$OUT/lists/targets_plus.csv"

# the API, on SQLite
uv sync -q --project "$REPO/api"
[[ "${KEEP_DB:-0}" == 1 ]] || rm -f "$OUT/api.db"
( cd "$REPO/api" && PH_DB_PATH="$OUT/api.db" PH_INGEST_TOKEN=$TOKEN PH_RATE_READ_PER_MIN=100000 \
  PH_RATE_INGEST_PER_MIN=100000 exec "$REPO/api/.venv/bin/python" -m uvicorn --factory api.app:create_app \
  --host 0.0.0.0 --port "$PORT" --log-level warning ) > "$OUT/api.log" 2>&1 &
API_PID=$!
POLL_PID=
trap 'kill $API_PID ${POLL_PID:-} 2>/dev/null || true' EXIT
for _ in $(seq 100); do curl -fs "http://127.0.0.1:$PORT/healthz" >/dev/null && break; sleep 0.2; done

# the monitor, as the site sees it
( while true; do
    printf '{"at":"%s","now":%s}\n' "$(date -u +%FT%TZ)" \
      "$(curl -fs --max-time 10 "http://127.0.0.1:$PORT/monitor/now" || echo null)"
    sleep 30
  done ) >> "$OUT/monitor_polls.jsonl" &
POLL_PID=$!

session() {  # name, targets file, input dir or "", expect ok|stop
  local name="$1" targets="$2" input="$3" expect="$4"
  mkdir -p "$OUT/$name/working"
  local mounts=(-v "$REPO/kaggle/planet_hunter_nightly.ipynb:/nb/planet_hunter_nightly.ipynb:ro"
                -v "$OUT/$name/working:/kaggle/working" -v "$OUT/lists:/dry:ro")
  [[ -n "$input" ]] && mounts+=(-v "$input:/kaggle/input/planet-hunter-nightly:ro")
  local allow=False; [[ "$expect" == stop ]] && allow=True  # keep the executed notebook: its log shows the STOP
  echo "== $name: $(date -u +%FT%TZ)"
  set +e
  docker run --rm --name "ph-kaggle-$name" --cpus=4 --memory=7g "${mounts[@]}" \
    -e PH_API_URL="http://host.docker.internal:$PORT" -e PH_INGEST_TOKEN=$TOKEN \
    -e PH_REPO_REF_OVERRIDE="$REF" -e PH_SESSION_HOURS_OVERRIDE="$SESSION_H" -e PH_WRAP_HOURS="$WRAP_H" \
    -e PH_TARGETS_FILE="/dry/$targets" -e PH_FAINT_FILE=/dry/faint.csv -e PH_HEARTBEAT_S=60 \
    "$IMAGE" bash -c 'pip install -q --root-user-action=ignore nbconvert ipykernel >/dev/null \
      && jupyter nbconvert --to notebook --execute --ExecutePreprocessor.timeout=-1 \
         --ExecutePreprocessor.allow_errors='"$allow"' \
         /nb/planet_hunter_nightly.ipynb --output-dir /kaggle/working --output executed.ipynb' \
    > "$OUT/$name/docker.log" 2>&1
  local code=$?
  set -e
  echo "== $name: exit $code at $(date -u +%FT%TZ)"
  if [[ "$expect" == ok && $code -ne 0 ]]; then echo "$name failed"; tail -30 "$OUT/$name/docker.log"; return 1; fi
  if [[ "$expect" == stop ]] && { [[ -e "$OUT/$name/working/ph-state" ]] \
       || ! grep -q "STOP: the restored ledger" "$OUT/$name/working/executed.ipynb"; }; then
    echo "$name should have stopped at the guard without writing output"; return 1
  fi
}

want() { [[ " ${SESSIONS:-s1 s2 s3} " == *" $1 "* ]]; }
want s1 && session s1 targets.csv "" ok
want s2 && session s2 targets_plus.csv "$OUT/s1/working" ok
want s3 && { rm -rf "$OUT/s3"; session s3 targets.csv "" stop; }
python3 "$HERE/summarize.py" "$OUT" > "$OUT/results.json"
cat "$OUT/results.json"
