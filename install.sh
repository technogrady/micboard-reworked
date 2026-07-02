#!/usr/bin/env bash
#
# micboard installer for Debian 11+, Ubuntu 20.04+, and Raspberry Pi OS.
#
# Installs Node.js and Python dependencies, builds the frontend bundle,
# and sets up a systemd service so micboard starts on boot and restarts
# on failure. Safe to re-run: every step is idempotent.
#
# Usage:
#   sudo ./install.sh                 full install, including systemd service
#   sudo ./install.sh --no-service    everything except the systemd service
#
# Output is mirrored to install.log next to this script.

set -Eeuo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="$REPO_DIR/install.log"
VENV_DIR="$REPO_DIR/.venv"
SERVICE_NAME="micboard"
NODE_MIN_MAJOR=20      # floor required by the sass/webpack toolchain
NODE_INSTALL_MAJOR=22  # LTS line installed when node is missing or too old
MICBOARD_PORT="${MICBOARD_PORT:-8058}"
INSTALL_SERVICE=1

for arg in "$@"; do
  case "$arg" in
    --no-service) INSTALL_SERVICE=0 ;;
    -h|--help) sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
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
}
trap 'on_error $? $LINENO "$BASH_COMMAND"' ERR

log "micboard install starting (log: $LOG_FILE)"

# --------------------------------------------------------- sanity checks --
[[ $EUID -eq 0 ]] || die "This script needs root for apt and systemd. Re-run with: sudo $0"

[[ -f "$REPO_DIR/package.json" && -f "$REPO_DIR/py/micboard.py" ]] \
  || die "This doesn't look like a micboard checkout: $REPO_DIR"

if [[ -r /etc/os-release ]]; then
  # shellcheck source=/dev/null
  . /etc/os-release
  case "${ID:-} ${ID_LIKE:-}" in
    *debian*|*ubuntu*|*raspbian*) info "Detected OS: ${PRETTY_NAME:-unknown}" ;;
    *) warn "Untested OS '${PRETTY_NAME:-unknown}' - continuing, but this script targets Debian/Ubuntu/Raspberry Pi OS." ;;
  esac
else
  warn "/etc/os-release not found - assuming a Debian-like system."
fi

ARCH="$(uname -m)"
if [[ "$ARCH" == armv6l ]]; then
  die "armv6 boards (Pi 1 / Pi Zero W) can't run Node ${NODE_MIN_MAJOR}+ from NodeSource. Use a Pi 3 or newer, or build the frontend on another machine and copy static/ over."
fi
info "Architecture: $ARCH"

# ----------------------------------------------------------- apt packages --
log "Installing system packages (curl, git, python3-venv)"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q curl ca-certificates git python3 python3-venv python3-pip

# ---------------------------------------------------------------- node.js --
node_major() { node -v 2>/dev/null | sed 's/^v\([0-9]*\).*/\1/'; }

log "Checking Node.js (need >= ${NODE_MIN_MAJOR})"
if command -v node >/dev/null && [[ "$(node_major)" -ge "$NODE_MIN_MAJOR" ]]; then
  info "Node $(node -v) already installed - OK"
else
  if command -v node >/dev/null; then
    info "Node $(node -v) is too old - installing Node ${NODE_INSTALL_MAJOR}.x from NodeSource"
  else
    info "Node not found - installing Node ${NODE_INSTALL_MAJOR}.x from NodeSource"
  fi
  curl -fsSL "https://deb.nodesource.com/setup_${NODE_INSTALL_MAJOR}.x" | bash -
  apt-get install -y -q nodejs
  command -v node >/dev/null || die "Node install finished but 'node' is not on PATH."
  [[ "$(node_major)" -ge "$NODE_MIN_MAJOR" ]] \
    || die "Node $(node -v) is still below ${NODE_MIN_MAJOR}. NodeSource may not support this OS/arch combination."
  info "Installed Node $(node -v), npm $(npm -v)"
fi

# --------------------------------------------------------- frontend build --
log "Installing JS dependencies (npm install)"
cd "$REPO_DIR"
npm install --no-fund --no-audit

log "Building frontend bundle (npm run build)"
npm run build
compgen -G "$REPO_DIR/static/*.js" >/dev/null \
  || die "Build reported success but no bundles found in static/ - check the webpack output above."
info "Bundle built into static/"

# ------------------------------------------------------------ python venv --
log "Setting up Python virtualenv at $VENV_DIR"
if [[ ! -x "$VENV_DIR/bin/python3" ]]; then
  python3 -m venv "$VENV_DIR"
  info "Created new venv"
else
  info "Reusing existing venv"
fi
"$VENV_DIR/bin/pip" install -q --upgrade pip
"$VENV_DIR/bin/pip" install -q -r "$REPO_DIR/py/requirements.txt"
"$VENV_DIR/bin/python3" -c 'import tornado' \
  || die "Python deps installed but 'import tornado' failed."
info "Python dependencies OK ($("$VENV_DIR/bin/python3" --version))"

# --------------------------------------------------------- systemd service --
if [[ "$INSTALL_SERVICE" -eq 1 ]]; then
  log "Installing systemd service '$SERVICE_NAME'"

  # Run the service as whoever owns the checkout so it can read/write config.
  SERVICE_USER="$(stat -c '%U' "$REPO_DIR")"
  [[ "$SERVICE_USER" == root ]] && warn "Repo is owned by root, so the service will run as root."
  info "Service user: $SERVICE_USER"

  cat > "/etc/systemd/system/${SERVICE_NAME}.service" <<UNIT
[Unit]
Description=Micboard wireless mic monitoring dashboard
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${SERVICE_USER}
WorkingDirectory=${REPO_DIR}
ExecStart=${VENV_DIR}/bin/python3 ${REPO_DIR}/py/micboard.py
Environment=MICBOARD_PORT=${MICBOARD_PORT}
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT

  systemctl daemon-reload
  systemctl enable --now "$SERVICE_NAME"

  sleep 2
  if systemctl is-active --quiet "$SERVICE_NAME"; then
    info "Service is running"
  else
    printf '\n'
    journalctl -u "$SERVICE_NAME" -n 20 --no-pager || true
    die "Service failed to start - recent log lines above. Full logs: journalctl -u $SERVICE_NAME"
  fi
else
  log "Skipping systemd service (--no-service)"
  info "Start manually with: $VENV_DIR/bin/python3 py/micboard.py"
fi

# ----------------------------------------------------------------- summary --
IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
log "micboard install complete"
info "URL:      http://${IP:-<this-machine>}:${MICBOARD_PORT}"
if [[ "$INSTALL_SERVICE" -eq 1 ]]; then
  info "Service:  systemctl status $SERVICE_NAME | journalctl -u $SERVICE_NAME -f"
fi
info "Updates:  ./update.sh (after a git pull it rebuilds and restarts as needed)"
