#!/usr/bin/env bash
# Install (or update) the Planet Finder search on the Oracle server, from your Mac.
#
#   runner/deploy.sh <ip> <ssh-key-path> [--ref v2] [--user ubuntu] [--port 22] [--api-url URL] [--repo-url URL]
#                    [--keep-secrets] [--no-start]
#
# 1. checks it can SSH in (key only);
# 2. copies bootstrap.sh and runs it with sudo (packages, uv, repo clone, venvs, systemd, firewall);
# 3. asks for the secrets here, without echoing them: PH_INGEST_TOKEN (the API's ingest token) and
#    PH_DATABASE_URL (the Postgres URL finder_ingest writes candidates to). They go over SSH on stdin straight into
#    /etc/planet-hunter.env (root, chmod 600): never on a command line, never in a file on this Mac, never in git;
# 4. enables the daily timer and starts today's run, then shows the status.
# Running it again updates everything and (with --keep-secrets, or answering "y") keeps the secrets.
# Works with macOS's bash 3.2.
set -euo pipefail

usage() { sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }
[[ $# -ge 2 ]] || usage
IP="$1"; KEY="$2"; shift 2
REF="v2"; SSH_USER="ubuntu"; PORT=22; API_URL="https://planet-hunter-api.onrender.com"; KEEP=""; START=1
REPO_URL="https://github.com/anastasiadisfoivos-hub/planet-hunter.git"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --ref) REF="$2"; shift 2 ;;
    --user) SSH_USER="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    --repo-url) REPO_URL="$2"; shift 2 ;;
    --api-url) API_URL="$2"; shift 2 ;;
    --keep-secrets) KEEP=1; shift ;;
    --no-start) START=0; shift ;;
    -h|--help) usage ;;
    *) echo "unknown option $1" >&2; usage ;;
  esac
done
[[ -f "$KEY" ]] || { echo "no SSH key at $KEY" >&2; exit 1; }
HERE="$(cd "$(dirname "$0")" && pwd)"
SSH_OPTS=(-i "$KEY" -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new -o ServerAliveInterval=30
          -o ConnectTimeout=15)
remote() { ssh -n -p "$PORT" "${SSH_OPTS[@]}" "$SSH_USER@$IP" "$@"; }         # never reads this script's stdin
remote_stdin() { ssh -p "$PORT" "${SSH_OPTS[@]}" "$SSH_USER@$IP" "$@"; }    # only for the secrets

echo "== connecting to $SSH_USER@$IP"
remote 'echo "   $(. /etc/os-release; echo $PRETTY_NAME), $(uname -m), $(nproc) cores, $(free -g | awk "/Mem/{print \$2}") GB RAM, $(df -h / | awk "NR==2{print \$4}") free on /"'

echo "== bootstrap (ref $REF)"
scp -q -P "$PORT" "${SSH_OPTS[@]}" "$HERE/bootstrap.sh" "$SSH_USER@$IP:/tmp/planet-hunter-bootstrap.sh"
remote "sudo env PH_REPO_REF='$REF' PH_REPO_URL='$REPO_URL' PH_API_URL='$API_URL' \
  PH_SKIP_FIREWALL='${PH_SKIP_FIREWALL:-0}' PH_SKIP_SSHD='${PH_SKIP_SSHD:-0}' bash /tmp/planet-hunter-bootstrap.sh"

has_secrets="$(remote 'sudo test -s /etc/planet-hunter.env && echo yes || echo no')"
if [[ "$has_secrets" == yes && -z "$KEEP" ]]; then
  read -r -p "Secrets are already on the server. Keep them? [Y/n] " ans
  [[ "$ans" =~ ^[Nn] ]] || KEEP=1
fi
if [[ "$has_secrets" != yes || -z "$KEEP" ]]; then
  echo "== secrets (typed input is not shown)"
  TOKEN=""; DBURL=""
  while [[ -z "$TOKEN" ]]; do read -r -s -p "PH_INGEST_TOKEN (the API's ingest token): " TOKEN; echo; done
  while [[ -z "$DBURL" ]]; do read -r -s -p "PH_DATABASE_URL (postgresql://...): " DBURL; echo; done
  case "$DBURL" in postgres://*|postgresql://*) ;; *) echo "that does not look like a Postgres URL" >&2; exit 1 ;; esac
  echo "   token: ${#TOKEN} characters; database URL: ${#DBURL} characters"
  # printf is a shell builtin: the values never appear in a process list; they travel inside the SSH session.
  printf 'PH_INGEST_TOKEN=%s\nPH_DATABASE_URL=%s\n' "$TOKEN" "$DBURL" \
    | remote_stdin 'sudo install -m 600 -o root -g root /dev/stdin /etc/planet-hunter.env'
  unset TOKEN DBURL
fi

echo "== checking the server can reach the API"
remote "curl -fsS --max-time 60 '$API_URL/healthz' && echo" || echo "   warning: $API_URL/healthz did not answer (Render may be waking up)"

if [[ "$START" == 1 ]]; then
  echo "== starting: daily timer (00:15 UTC and at boot) and today's run now"
  remote 'sudo systemctl enable --now planet-hunter.timer >/dev/null && sudo systemctl start --no-block planet-hunter.service'
  sleep 20
  remote 'sudo planet-hunter status; echo; sudo journalctl -u planet-hunter -n 15 --no-pager'
fi
cat <<EOF

Done. On the server (ssh -i $KEY -p $PORT $SSH_USER@$IP):
  planet-hunter status      is it running, tonight's progress, the last run, disk
  planet-hunter logs        follow the log (journald)
  sudo planet-hunter pause  stop now and keep it stopped (timer off);  sudo planet-hunter resume  to restart
EOF
