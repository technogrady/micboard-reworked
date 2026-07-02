#!/usr/bin/env bash
#
# micboard updater: git pull, reinstall dependencies and rebuild the
# frontend when needed, then restart the systemd service.
#
# Usage:
#   ./update.sh            pull and update only what changed
#   ./update.sh --force    rebuild and reinstall everything regardless
#
# Output is mirrored to update.log next to this script.

set -Eeuo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="$REPO_DIR/update.log"
VENV_DIR="$REPO_DIR/.venv"
SERVICE_NAME="micboard"
FORCE=0

for arg in "$@"; do
  case "$arg" in
    --force) FORCE=1 ;;
    -h|--help) sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $arg (try --help)" >&2; exit 2 ;;
  esac
done

# ---------------------------------------------------------------- logging --
exec > >(tee -a "$LOG_FILE") 2>&1

log()  { printf '\n\033[1;32m[%s] ==> %s\033[0m\n' "$(date '+%F %T')" "$*"; }
info() { printf '    %s\n' "$*"; }
warn() { printf '\033[1;33m    WARNING: %s\033[0m\n' "$*"; }
die()  { printf '\n\033[1;31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }

on_error() {
  local exit_code=$1 line=$2 cmd=$3
  printf '\n\033[1;31mFAILED (exit %s) at %s line %s while running:\033[0m\n' \
    "$exit_code" "$(basename "$0")" "$line" >&2
  printf '\033[1;31m    %s\033[0m\n' "$cmd" >&2
  printf 'Full log: %s\n' "$LOG_FILE" >&2
  printf 'The service was NOT restarted with a half-finished update.\n' >&2
}
trap 'on_error $? $LINENO "$BASH_COMMAND"' ERR

# Allow git to operate on the repo even when run via sudo / as a different
# user than the checkout's owner (avoids "dubious ownership" errors).
git_repo() { git -C "$REPO_DIR" -c safe.directory="$REPO_DIR" "$@"; }

changed() {
  # True if any file matching the pattern changed between the two commits.
  git_repo diff --name-only "$OLD_HEAD" "$NEW_HEAD" | grep -qE "$1"
}

log "micboard update starting (log: $LOG_FILE)"

# ------------------------------------------------------------------- pull --
log "Pulling latest changes"
OLD_HEAD="$(git_repo rev-parse HEAD)"
git_repo pull --no-rebase
NEW_HEAD="$(git_repo rev-parse HEAD)"

if [[ "$OLD_HEAD" == "$NEW_HEAD" && "$FORCE" -eq 0 ]]; then
  log "Already up to date ($(git_repo rev-parse --short HEAD)) - nothing to do"
  info "Use ./update.sh --force to rebuild anyway."
  exit 0
fi

if [[ "$OLD_HEAD" != "$NEW_HEAD" ]]; then
  info "Updated $(git_repo rev-parse --short "$OLD_HEAD") -> $(git_repo rev-parse --short "$NEW_HEAD"):"
  git_repo log --oneline "$OLD_HEAD..$NEW_HEAD" | sed 's/^/      /'
else
  info "No new commits, but --force given - rebuilding everything."
fi

# --------------------------------------------------------- JS dependencies --
if [[ "$FORCE" -eq 1 ]] || changed '^package(-lock)?\.json$'; then
  log "package.json changed - installing JS dependencies"
  (cd "$REPO_DIR" && npm install --no-fund --no-audit)
else
  log "JS dependencies unchanged - skipping npm install"
fi

# ----------------------------------------------------- Python dependencies --
if [[ ! -x "$VENV_DIR/bin/pip" ]]; then
  warn "No venv at $VENV_DIR - run ./install.sh first for a full setup."
elif [[ "$FORCE" -eq 1 ]] || changed '^py/requirements\.txt$'; then
  log "requirements.txt changed - installing Python dependencies"
  "$VENV_DIR/bin/pip" install -q -r "$REPO_DIR/py/requirements.txt"
else
  log "Python dependencies unchanged - skipping pip install"
fi

# --------------------------------------------------------- frontend build --
if [[ "$FORCE" -eq 1 ]] || changed '^(js/|css/|webpack\.config\.js|package\.json)'; then
  log "Frontend sources changed - rebuilding bundle (npm run build)"
  (cd "$REPO_DIR" && npm run build)
  compgen -G "$REPO_DIR/static/*.js" >/dev/null \
    || die "Build reported success but no bundles found in static/ - check the webpack output above."
  info "Bundle rebuilt"
else
  log "No frontend changes - skipping rebuild"
fi

# ---------------------------------------------------------------- restart --
if systemctl list-unit-files "${SERVICE_NAME}.service" --no-legend 2>/dev/null | grep -q "$SERVICE_NAME"; then
  log "Restarting service '$SERVICE_NAME'"
  [[ $EUID -eq 0 ]] || die "Restarting the service needs root. Re-run with: sudo $0"
  systemctl restart "$SERVICE_NAME"
  sleep 2
  if systemctl is-active --quiet "$SERVICE_NAME"; then
    info "Service restarted and running"
  else
    printf '\n'
    journalctl -u "$SERVICE_NAME" -n 20 --no-pager || true
    die "Service failed to come back up - recent log lines above. Full logs: journalctl -u $SERVICE_NAME"
  fi
else
  log "No systemd service found - restart the server yourself"
  info "e.g. stop the running 'npm run server' and start it again"
fi

log "micboard update complete ($(git_repo rev-parse --short HEAD))"
info "Hard-refresh the browser (Ctrl+Shift+R) to pick up the new bundle."
