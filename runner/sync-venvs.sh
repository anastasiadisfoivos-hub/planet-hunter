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
    echo "sync-venvs: $name: lock file out of date for this ref; resolving (uv sync without --frozen)"
    UV_PROJECT_ENVIRONMENT="$VENVS/$name" "$UV" sync --project "$dir" "$@"
  fi
  echo "$want" > "$stamp"
}

sync_one hunt --no-dev
sync_one faint            # its dev group is what brings in hunt
sync_one vet --no-dev
sync_one api --no-dev --extra finder
echo "sync-venvs: done"
