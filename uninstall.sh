#!/usr/bin/env bash
set -euo pipefail

MODE="auto"
SERVICE_NAME="trafficowg-web"
INSTALL_DIR="/opt/trafficowg"

usage() {
  cat <<'EOF'
Usage: ./uninstall.sh [options]

Options:
  --mode auto|systemd|local   Uninstall mode (default: auto)
  --service-name <name>       systemd service name (default: trafficowg-web)
  --install-dir <path>        systemd install dir (default: /opt/trafficowg)
  --purge                     Remove installed python file and local .run data
  -h, --help                  Show this help
EOF
}

PURGE=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode) MODE="${2:-}"; shift 2 ;;
    --service-name) SERVICE_NAME="${2:-}"; shift 2 ;;
    --install-dir) INSTALL_DIR="${2:-}"; shift 2 ;;
    --purge) PURGE=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1"; usage; exit 1 ;;
  esac
done

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$ROOT_DIR/.run/trafficowg_web.pid"
LOG_FILE="$ROOT_DIR/.run/trafficowg_web.log"

is_root=0
if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
  is_root=1
fi

if [[ "$MODE" == "auto" ]]; then
  if [[ "$is_root" -eq 1 ]] && command -v systemctl >/dev/null 2>&1; then
    MODE="systemd"
  else
    MODE="local"
  fi
fi

stop_local() {
  if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" >/dev/null 2>&1; then
    kill "$(cat "$PID_FILE")"
    echo "Stopped local instance PID $(cat "$PID_FILE")."
  else
    echo "No local instance PID found."
  fi
  rm -f "$PID_FILE"
  if [[ "$PURGE" -eq 1 ]]; then
    rm -f "$LOG_FILE"
    rmdir "$ROOT_DIR/.run" 2>/dev/null || true
  fi
}

remove_systemd() {
  if [[ "$is_root" -ne 1 ]]; then
    echo "Systemd mode requires root. Re-run with sudo/root."
    exit 1
  fi
  if ! command -v systemctl >/dev/null 2>&1; then
    echo "systemctl not found. Use --mode local."
    exit 1
  fi

  systemctl disable --now "$SERVICE_NAME" 2>/dev/null || true
  rm -f "/etc/systemd/system/${SERVICE_NAME}.service"
  systemctl daemon-reload

  if [[ "$PURGE" -eq 1 ]]; then
    rm -f "$INSTALL_DIR/trafficowg_web.py"
    rmdir "$INSTALL_DIR" 2>/dev/null || true
  fi

  echo "Systemd service removed: $SERVICE_NAME"
}

case "$MODE" in
  local) stop_local ;;
  systemd) remove_systemd ;;
  *)
    echo "Invalid mode: $MODE"
    usage
    exit 1
    ;;
esac
