#!/usr/bin/env bash
# Set up (or bring up to date) the Planet Finder search server on Ubuntu 24.04 (Oracle Cloud Ampere A1, arm64).
# Idempotent: run it again any time; every step checks before it changes anything.
#
#   sudo PH_REPO_REF=v2 bash bootstrap.sh
#
# What it does:
#   packages (git, build tools, python3, ufw, ...), uv (pinned), the service user `planethunter`,
#   a read-only HTTPS clone of the repo at /opt/planet-hunter/repo (PH_REPO_REF), one venv per package under
#   /opt/planet-hunter/venvs (hunt, faint, vet, api), data under /var/lib/planet-hunter, /etc/planet-hunter.conf
#   (settings) and an empty root-only /etc/planet-hunter.env (secrets; deploy.sh fills it), the systemd service +
#   timer, the `planet-hunter` command, journald limits, the firewall (inbound SSH only) and key-only SSH.
# It does not start the search: deploy.sh does, once the secrets are in place (or: sudo planet-hunter resume).
#
# Settings (env): PH_REPO_URL, PH_REPO_REF (v2), PH_API_URL, PH_WORKERS (4), PH_DISK_CAP_GB (150),
#   PH_SKIP_FIREWALL=1 / PH_SKIP_SSHD=1 (containers), PH_UV_VERSION.
set -euo pipefail

PH_REPO_URL="${PH_REPO_URL:-https://github.com/anastasiadisfoivos-hub/planet-hunter.git}"
PH_REPO_REF="${PH_REPO_REF:-v2}"
PH_API_URL="${PH_API_URL:-https://planet-hunter-api.onrender.com}"
PH_WORKERS="${PH_WORKERS:-4}"
PH_DISK_CAP_GB="${PH_DISK_CAP_GB:-150}"
PH_UV_VERSION="${PH_UV_VERSION:-0.12.19}"
HOME_DIR=/opt/planet-hunter
DATA_DIR=/var/lib/planet-hunter
USER_NAME=planethunter
REPO="$HOME_DIR/repo"

say() { printf '\n== %s\n' "$*"; }
as_user() { runuser -u "$USER_NAME" -- env HOME="$DATA_DIR" PH_HOME="$HOME_DIR" PH_DATA="$DATA_DIR" \
  UV_CACHE_DIR="$DATA_DIR/cache/uv" UV_PYTHON_INSTALL_DIR="$HOME_DIR/python" PATH="/usr/local/bin:/usr/bin:/bin" "$@"; }

[[ $EUID -eq 0 ]] || { echo "run as root (sudo bash bootstrap.sh)" >&2; exit 1; }
. /etc/os-release
[[ "${VERSION_ID:-}" == "24.04" ]] || echo "warning: tested on Ubuntu 24.04, this is ${PRETTY_NAME:-unknown}"
[[ "$(uname -m)" == "aarch64" ]] || echo "warning: built for arm64 (Ampere A1); this machine is $(uname -m)"

say "packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq --no-install-recommends \
  ca-certificates curl git unzip xz-utils python3 python3-venv python3-dev sqlite3 build-essential gfortran pkg-config \
  libopenblas-dev libhdf5-dev ufw unattended-upgrades sudo cron >/dev/null
systemctl enable --now unattended-upgrades >/dev/null 2>&1 || true

say "uv $PH_UV_VERSION"
if ! /usr/local/bin/uv --version 2>/dev/null | grep -q "uv $PH_UV_VERSION"; then
  curl -LsSf "https://astral.sh/uv/$PH_UV_VERSION/install.sh" \
    | env UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 INSTALLER_NO_MODIFY_PATH=1 sh >/dev/null
fi
/usr/local/bin/uv --version

say "user and folders"
id -u "$USER_NAME" >/dev/null 2>&1 || useradd --system --home-dir "$DATA_DIR" --shell /usr/sbin/nologin "$USER_NAME"
install -d -o "$USER_NAME" -g "$USER_NAME" -m 755 "$HOME_DIR" "$HOME_DIR/venvs" "$HOME_DIR/python"
install -d -o "$USER_NAME" -g "$USER_NAME" -m 750 "$DATA_DIR" "$DATA_DIR/cache" "$DATA_DIR/runs" \
  "$DATA_DIR/targets" "$DATA_DIR/state"

say "repo ($PH_REPO_REF, read-only HTTPS clone)"
if [[ ! -d "$REPO/.git" ]]; then
  as_user git clone --quiet --depth 1 --branch "$PH_REPO_REF" "$PH_REPO_URL" "$REPO"
else
  as_user git -C "$REPO" remote set-url origin "$PH_REPO_URL"
  as_user git -C "$REPO" fetch --quiet --depth 1 origin "+refs/heads/$PH_REPO_REF:refs/remotes/origin/$PH_REPO_REF"
  as_user git -C "$REPO" reset --quiet --hard "origin/$PH_REPO_REF"
fi
as_user git -C "$REPO" log -1 --format='%h %s'
[[ -f "$REPO/runner/scheduler/run.py" ]] || {
  echo "error: ref $PH_REPO_REF has no runner/; deploy with a ref that includes it (e.g. --ref runner)" >&2; exit 1; }

say "settings (/etc/planet-hunter.conf) and secrets file (/etc/planet-hunter.env, root only)"
conf=/etc/planet-hunter.conf
touch "$conf"
setconf() {  # key value: set once; a value the owner edited by hand is kept unless PH_FORCE_CONF=1
  if grep -q "^$1=" "$conf"; then
    if [[ "${PH_FORCE_CONF:-0}" == 1 || "$1" == PH_REPO_REF || "$1" == PH_REPO_URL ]]; then
      sed -i "s|^$1=.*|$1=$2|" "$conf"
    fi
  else
    echo "$1=$2" >> "$conf"
  fi
}
setconf PH_REPO_URL "$PH_REPO_URL"
setconf PH_REPO_REF "$PH_REPO_REF"
setconf PH_API_URL "$PH_API_URL"
setconf PH_WORKERS "$PH_WORKERS"
setconf PH_DISK_CAP_GB "$PH_DISK_CAP_GB"
setconf PH_AUTO_UPDATE 1
chmod 644 "$conf"
[[ -f /etc/planet-hunter.env ]] || install -m 600 -o root -g root /dev/null /etc/planet-hunter.env
chown root:root /etc/planet-hunter.env && chmod 600 /etc/planet-hunter.env

say "venvs (hunt, faint, vet, api)"
as_user bash "$REPO/runner/sync-venvs.sh"

say "systemd"
install -m 644 "$REPO/runner/systemd/planet-hunter.service" /etc/systemd/system/planet-hunter.service
install -m 644 "$REPO/runner/systemd/planet-hunter.timer" /etc/systemd/system/planet-hunter.timer
install -m 755 "$REPO/runner/bin/planet-hunter" /usr/local/bin/planet-hunter
install -d /etc/systemd/journald.conf.d
printf '[Journal]\nStorage=persistent\nSystemMaxUse=2G\n' > /etc/systemd/journald.conf.d/60-planet-hunter.conf
systemctl daemon-reload
systemctl restart systemd-journald || true

if [[ "${PH_SKIP_SSHD:-0}" != 1 && -d /etc/ssh/sshd_config.d ]]; then
  say "ssh: keys only"
  printf 'PasswordAuthentication no\nKbdInteractiveAuthentication no\nPermitRootLogin no\n' \
    > /etc/ssh/sshd_config.d/60-planet-hunter.conf
  if sshd -t 2>/dev/null; then systemctl reload ssh 2>/dev/null || systemctl reload sshd 2>/dev/null || true
  else rm -f /etc/ssh/sshd_config.d/60-planet-hunter.conf; echo "sshd -t failed; left sshd unchanged"; fi
fi

if [[ "${PH_SKIP_FIREWALL:-0}" != 1 ]]; then
  say "firewall: inbound SSH only"
  # Oracle's Ubuntu image ships iptables-persistent rules that already allow only SSH; ufw replaces them with the
  # same policy (the VCN security list in the Oracle console should also allow only TCP 22).
  ufw --force default deny incoming >/dev/null
  ufw --force default allow outgoing >/dev/null
  ufw allow 22/tcp >/dev/null
  ufw --force enable >/dev/null
  ufw status verbose | sed -n 1,12p
fi

say "done"
echo "Repo:     $REPO ($(as_user git -C "$REPO" rev-parse --short HEAD) on $PH_REPO_REF)"
echo "Settings: /etc/planet-hunter.conf    Secrets: /etc/planet-hunter.env (root, 600)"
if [[ -s /etc/planet-hunter.env ]]; then
  echo "Start:    sudo planet-hunter resume   (timer: 00:15 UTC daily and at boot)"
else
  echo "Secrets are empty: run deploy.sh from your Mac (it asks for them), then it starts the timer."
fi
