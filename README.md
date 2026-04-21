# WG Interface Traffic Control

Single-file Python web UI for real-time WireGuard peer traffic monitoring.

> 🇮🇹 [Leggi in italiano](README.it.md)

## Preview

<p align="center">
  <img src="docs/images/overview.svg" width="90%" alt="Desktop UI preview"/>
</p>
<p align="center">
  <img src="docs/images/mobile.svg" width="45%" alt="Mobile UI preview"/>
</p>

## Project Overview

This project provides:

- Real-time peer table (download, upload, peak, totals, endpoint, status)
- Auto-refresh dashboard with WireGuard stats
- Standalone Python app (`trafficowg_web.py`)
- Ready-to-use `install.sh` and `uninstall.sh`
- `systemd` mode for production and `local` mode for quick tests

## Repository Structure

```text
├── trafficowg_web.py      # Main web UI app
├── install.sh             # Installer (auto/systemd/local)
├── uninstall.sh           # Uninstaller (auto/systemd/local)
├── README.md              # English documentation
├── README.it.md           # Italian documentation
└── docs/
    └── images/
        ├── overview.svg   # Desktop preview
        └── mobile.svg     # Mobile preview
```

## Installation (3 steps)

1. Copy project files to server:

```bash
mkdir -p /opt/trafficowg
cp trafficowg_web.py install.sh uninstall.sh /opt/trafficowg/
chmod +x /opt/trafficowg/trafficowg_web.py /opt/trafficowg/install.sh /opt/trafficowg/uninstall.sh
```

2. Run installer in `systemd` mode:

```bash
cd /opt/trafficowg
sudo bash install.sh --mode systemd --bind <SERVER_BIND_IP> --port 65430 --if wg0
```

3. Open the UI:

```text
http://<SERVER_BIND_IP>:65430/
```

## Quick Commands

```bash
# Recommended one-shot setup
bash install.sh

# Local test mode
bash install.sh --mode local --bind <LOCAL_BIND_IP> --port 65430

# Remove service
sudo bash uninstall.sh --mode systemd --purge

# Stop local instance
bash uninstall.sh --mode local --purge
```

## Environment Variables

- `TRAFFICOWG_BIND` (default: `0.0.0.0`)
- `TRAFFICOWG_PORT` (default: `65430`)
- `TRAFFICOWG_IF` (default: `wg0`)
- `TRAFFICOWG_REFRESH_MS` (default: `2000`)

## Notes

- All screenshots in this repository are sanitized (no real IP addresses).
- `/usr/local/bin/trafficowg` is CLI-only; web UI runs from `trafficowg_web.py`.
