#!/usr/bin/env bash
# Build or refresh the venvs the runner starts its jobs in, one per package, outside the repo so the clone stays
# pristine (`git reset --hard` on update never touches them):
#   hunt   hunt/ + pipeline/                         fast and deep searches, `hunt targets`, `hunt merge`
#   faint  faint/ with its dev group (hunt, pipeline) faint searches (TGLC light curves + hunt's search)
#   vet    vet/ (Python 3.13)                        skyvet
#   api    api/ with the `finder` extra (pixels/, pipeline/)   finder_ingest
# A venv is rebuilt only when its package's pyproject.toml / uv.lock changed (stamp file). A package missing on the
# checked-out ref is skipped; the scheduler then turns its queue off and says why.
# Usage (as the service user): sync-venvs.sh [--force]
set -euo pipefail

PH_HOME="${PH_HOME:-/opt/planet-hunter}"
PH_DATA="${PH_DATA:-/var/lib/planet-hunter}"
REPO="$PH_HOME/repo"
VENVS="$PH_HOME/venvs"
UV="${UV:-$(command -v uv || echo "$PH_HOME/bin/uv")}"
export UV_CACHE_DIR="${UV_CACHE_DIR:-$PH_DATA/cache/uv}"
export UV_PYTHON_INSTALL_DIR="${UV_PYTHON_INSTALL_DIR:-$PH_HOME/python}"
export UV_LINK_MODE=copy
force="${1:-}"
cd "$PH_HOME"  # uv reads uv.toml from the working directory; never from a caller's home
# Locked packages with no Linux arm64 wheel and no sdist at the locked version: on arm64 they are left out of the
# locked install and built from source at the newest version that has an sdist. (batman-package 2.5.3, pulled in by
# transitleastsquares and triceratops, ships x86 / macOS wheels only; 2.5.2 has an sdist.) The lasting fix is in
# hunt/ and vet/: `[tool.uv] required-environments` with linux aarch64 and a batman-package pin.
ARM64_FROM_SOURCE="${ARM64_FROM_SOURCE:-batman-package==2.5.2}"
mkdir -p "$VENVS"

sync_one() {  # name, extra uv args...
  local name="$1"; shift
  local dir="$REPO/$name"
  if [[ ! -f "$dir/pyproject.toml" ]]; then
    echo "sync-venvs: $name/ is not on this ref; skipped"
    return 0
  fi
  local stamp="$VENVS/.$name.stamp" want
  want="$(cat "$dir/pyproject.toml" "$dir/uv.lock" 2>/dev/null | sha256sum | cut -c1-16)-$*"
  if [[ "$force" != "--force" && -f "$stamp" && "$(cat "$stamp")" == "$want" && -x "$VENVS/$name/bin/python" ]]; then
    echo "sync-venvs: $name unchanged"
    return 0
  fi
  echo "sync-venvs: syncing $name"
  if ! UV_PROJECT_ENVIRONMENT="$VENVS/$name" "$UV" sync --project "$dir" --frozen "$@"; then
    if [[ "$(uname -m)" == aarch64 ]] && grep -q 'name = "batman-package"' "$dir/uv.lock" 2>/dev/null; then
      echo "sync-venvs: $name: arm64: installing the lock without packages that lack arm64 wheels, then building $ARM64_FROM_SOURCE"
      local skip=() spec
      for spec in $ARM64_FROM_SOURCE; do skip+=(--no-install-package "${spec%%[=<>]*}"); done
      UV_PROJECT_ENVIRONMENT="$VENVS/$name" "$UV" sync --project "$dir" --frozen "${skip[@]}" "$@"
      # build against the numpy the venv runs (uv's isolated build would otherwise pick an older numpy's headers)
      "$VENVS/$name/bin/python" -c 'import numpy; print("numpy==" + numpy.__version__)' > "$VENVS/.$name.build-constraints"
      # --no-cache: a wheel cached from another venv's build may carry other numpy headers
      "$UV" pip install --python "$VENVS/$name/bin/python" --build-constraints "$VENVS/.$name.build-constraints" \
        --reinstall --no-cache $ARM64_FROM_SOURCE
    else
      echo "sync-venvs: $name: lock file out of date for this ref; resolving (uv sync without --frozen)"
      UV_PROJECT_ENVIRONMENT="$VENVS/$name" "$UV" sync --project "$dir" "$@"
    fi
  fi
  echo "$want" > "$stamp"
}

sync_one hunt --no-dev
sync_one faint            # skyfaint's own venv (its dev group brings in hunt): `skyfaint targets` runs here
# Faint stars are searched with DEEPHUNT's deep search, which lives in hunt's venv (faint's lock pins an older hunt
# without transitleastsquares), so skyfaint is added to hunt's venv too; installed packages are kept as locked.
if [[ -f "$REPO/faint/pyproject.toml" && -x "$VENVS/hunt/bin/python" ]] \
   && ! "$VENVS/hunt/bin/python" -c 'import skyfaint.tglc' 2>/dev/null; then
  echo "sync-venvs: adding skyfaint to hunt's venv"
  "$UV" pip install --python "$VENVS/hunt/bin/python" -e "$REPO/faint"
fi
sync_one vet --no-dev
sync_one api --no-dev --extra finder
echo "sync-venvs: done"
