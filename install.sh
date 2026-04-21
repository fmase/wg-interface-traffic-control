#!/usr/bin/env bash
set -euo pipefail

MODE="auto"
BIND="0.0.0.0"
PORT="65430"
WG_IF="wg0"
REFRESH_MS="2000"
SERVICE_NAME="trafficowg-web"
INSTALL_DIR="/opt/trafficowg"

usage() {
  cat <<'EOF'
Usage: ./install.sh [options]

Options:
  --mode auto|systemd|local   Install mode (default: auto)
  --bind <ip>                 TRAFFICOWG_BIND (default: 0.0.0.0)
  --port <port>               TRAFFICOWG_PORT (default: 65430)
  --if <name>                 TRAFFICOWG_IF (default: wg0)
  --refresh-ms <ms>           TRAFFICOWG_REFRESH_MS (default: 2000)
  --service-name <name>       systemd service name (default: trafficowg-web)
  --install-dir <path>        systemd install dir (default: /opt/trafficowg)
  -h, --help                  Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode) MODE="${2:-}"; shift 2 ;;
    --bind) BIND="${2:-}"; shift 2 ;;
    --port) PORT="${2:-}"; shift 2 ;;
    --if) WG_IF="${2:-}"; shift 2 ;;
    --refresh-ms) REFRESH_MS="${2:-}"; shift 2 ;;
    --service-name) SERVICE_NAME="${2:-}"; shift 2 ;;
    --install-dir) INSTALL_DIR="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1"; usage; exit 1 ;;
  esac
done

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 not found. Install Python 3 and retry."
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_FILE="$ROOT_DIR/trafficowg_web.py"
if [[ ! -f "$SOURCE_FILE" ]]; then
  echo "Cannot find trafficowg_web.py in $ROOT_DIR"
  exit 1
fi

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

start_local() {
  local run_dir="$ROOT_DIR/.run"
  local log_file="$run_dir/trafficowg_web.log"
  local pid_file="$run_dir/trafficowg_web.pid"
  mkdir -p "$run_dir"

  if [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" >/dev/null 2>&1; then
    echo "Local instance already running (PID $(cat "$pid_file"))."
    echo "Log: $log_file"
    echo "URL: http://$BIND:$PORT/"
    exit 0
  fi

  TRAFFICOWG_BIND="$BIND" \
  TRAFFICOWG_PORT="$PORT" \
  TRAFFICOWG_IF="$WG_IF" \
  TRAFFICOWG_REFRESH_MS="$REFRESH_MS" \
  nohup python3 "$SOURCE_FILE" >"$log_file" 2>&1 &

  echo $! >"$pid_file"
  echo "Local mode started."
  echo "PID: $(cat "$pid_file")"
  echo "Log: $log_file"
  echo "URL: http://$BIND:$PORT/"
}

install_systemd() {
  if [[ "$is_root" -ne 1 ]]; then
    echo "Systemd mode requires root. Re-run with sudo/root."
    exit 1
  fi
  if ! command -v systemctl >/dev/null 2>&1; then
    echo "systemctl not found. Use --mode local."
    exit 1
  fi

  mkdir -p "$INSTALL_DIR"
  install -m 755 "$SOURCE_FILE" "$INSTALL_DIR/trafficowg_web.py"

  local service_path="/etc/systemd/system/${SERVICE_NAME}.service"
  cat >"$service_path" <<EOF
[Unit]
Description=TrafficoWG web monitor
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
Environment=TRAFFICOWG_BIND=$BIND
Environment=TRAFFICOWG_PORT=$PORT
Environment=TRAFFICOWG_IF=$WG_IF
Environment=TRAFFICOWG_REFRESH_MS=$REFRESH_MS
ExecStart=/usr/bin/python3 $INSTALL_DIR/trafficowg_web.py
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
EOF

  systemctl daemon-reload
  systemctl enable --now "$SERVICE_NAME"

  echo "Systemd mode installed."
  echo "Service: $SERVICE_NAME"
  echo "Service file: $service_path"
  echo "URL: http://$BIND:$PORT/"
}

case "$MODE" in
  local) start_local ;;
  systemd) install_systemd ;;
  *)
    echo "Invalid mode: $MODE"
    usage
    exit 1
    ;;
esac
