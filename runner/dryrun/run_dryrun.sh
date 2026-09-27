#!/usr/bin/env bash
# Dry run of the whole install on a local Ubuntu 24.04 arm64 container (systemd + SSH), 4 CPUs like the Ampere A1:
#   deploy.sh -> bootstrap.sh -> systemd timer + service -> scheduler -> real TESS stars -> the real API (local,
#   on Postgres) -> finder_ingest into the same Postgres. The monitor is polled from outside while it runs.
# Needs: Docker; a local API on :8766 (PH_INGEST_TOKEN=dry-token, PH_DATABASE_URL=the Postgres below); the repo
# served by `git daemon` on :9418 with a ref that has runner/ (and hunt/deephunt, vet/, faint/); Postgres on :5433.
# Usage: run_dryrun.sh <ref> <targets.csv> <faint.csv> <out-dir>
set -euo pipefail
REF="$1"; TARGETS="$2"; FAINT="$3"; OUT="$4"
HERE="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$OUT"
[[ -f "$OUT/key" ]] || ssh-keygen -q -t ed25519 -N "" -f "$OUT/key"
cp "$OUT/key.pub" "$HERE/authorized_keys"
docker build -q -t ph-dryrun-ubuntu "$HERE" >/dev/null
rm -f "$HERE/authorized_keys"
docker rm -f ph-dryrun >/dev/null 2>&1 || true
docker run -d --name ph-dryrun --hostname ph-dryrun --privileged --cgroupns=host \
  -v /sys/fs/cgroup:/sys/fs/cgroup:rw --cpus=4 --memory=7g -p 2222:22 ph-dryrun-ubuntu >/dev/null
for _ in $(seq 60); do ssh -q -i "$OUT/key" -p 2222 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
  ubuntu@127.0.0.1 true 2>/dev/null && break; sleep 2; done
ssh-keygen -R "[127.0.0.1]:2222" >/dev/null 2>&1 || true

# The dry-run lists (20 stars) go in before the first run starts: deploy with --no-start, add them, then start.
printf 'dry-token\npostgresql://postgres:dry@host.docker.internal:5433/ph\n' | \
  PH_SKIP_FIREWALL="${PH_SKIP_FIREWALL:-0}" "$HERE/../deploy.sh" 127.0.0.1 "$OUT/key" --port 2222 --ref "$REF" \
  --repo-url git://host.docker.internal/planet-hunter.git --api-url http://host.docker.internal:8766 --no-start \
  2>&1 | tee "$OUT/deploy.log"
SSH=(ssh -i "$OUT/key" -p 2222 -o StrictHostKeyChecking=accept-new ubuntu@127.0.0.1)
scp -q -P 2222 -i "$OUT/key" "$TARGETS" "$FAINT" ubuntu@127.0.0.1:/tmp/
"${SSH[@]}" "sudo install -o planethunter -m 644 /tmp/$(basename "$TARGETS") /var/lib/planet-hunter/targets/dryrun_targets.csv \
  && sudo install -o planethunter -m 644 /tmp/$(basename "$FAINT") /var/lib/planet-hunter/targets/dryrun_faint.csv \
  && printf 'PH_TARGETS_FILE=/var/lib/planet-hunter/targets/dryrun_targets.csv\nPH_FAINT_FILE=/var/lib/planet-hunter/targets/dryrun_faint.csv\nPH_HEARTBEAT_S=60\n' | sudo tee -a /etc/planet-hunter.conf >/dev/null \
  && sudo systemctl enable --now planet-hunter.timer && sudo systemctl start --no-block planet-hunter.service"
echo "started: $(date -u +%FT%TZ)"
