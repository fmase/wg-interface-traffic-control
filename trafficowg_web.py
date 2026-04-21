#!/usr/bin/env python3
import json
import os
import subprocess
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

WG_IF = os.environ.get('TRAFFICOWG_IF', 'wg0')
WG_CONF = Path(f'/etc/wireguard/{WG_IF}.conf')
BIND_HOST = os.environ.get('TRAFFICOWG_BIND', '0.0.0.0')
PORT = int(os.environ.get('TRAFFICOWG_PORT', '65430'))
REFRESH_MS = int(os.environ.get('TRAFFICOWG_REFRESH_MS', '2000'))
STATE = {}
PEAK_FILE = Path('/tmp/trafficowg_peaks.json')
PEAKS = {}


def load_map():
    peers = {}
    if not WG_CONF.exists():
        return peers
    name = ''
    key = ''
    for raw in WG_CONF.read_text().splitlines():
        line = raw.strip()
        if line.startswith('### Client '):
            name = line[len('### Client '):].strip()
        elif line == '[Peer]':
            key = ''
        elif line.startswith('PublicKey = '):
            key = line.split(' = ', 1)[1].strip()
        elif line.startswith('AllowedIPs = ') and key:
            first = line.split(' = ', 1)[1].split(',', 1)[0].split('/', 1)[0].strip()
            peers[key] = {'name': name or f'{key[:8]}...', 'ip': first}
            key = ''
    return peers


def load_peaks():
    global PEAKS
    if not PEAK_FILE.exists():
        PEAKS = {}
        return
    try:
        raw = json.loads(PEAK_FILE.read_text())
        if not isinstance(raw, dict):
            PEAKS = {}
            return
        normalized = {}
        for key, value in raw.items():
            if isinstance(value, dict):
                normalized[key] = {
                    'rx': int(value.get('rx', 0) or 0),
                    'tx': int(value.get('tx', 0) or 0),
                }
            else:
                legacy = int(value or 0)
                normalized[key] = {'rx': legacy, 'tx': legacy}
        PEAKS = normalized
    except Exception:
        PEAKS = {}


def save_peaks():
    PEAK_FILE.write_text(json.dumps(PEAKS))


def human_bytes(v: int) -> str:
    units = ['B', 'KiB', 'MiB', 'GiB', 'TiB']
    n = float(v)
    for unit in units:
        if n < 1024 or unit == units[-1]:
            return f'{n:.2f} {unit}' if unit != 'B' else f'{int(n)} B'
        n /= 1024
    return f'{int(v)} B'


def human_rate(v: float) -> str:
    return human_bytes(int(v)).replace(' B', ' B/s').replace('KiB', 'KiB/s').replace('MiB', 'MiB/s').replace('GiB', 'GiB/s').replace('TiB', 'TiB/s')


def handshake_text(ts: int) -> str:
    if ts == 0:
        return 'never'
    diff = max(0, int(time.time() - ts))
    if diff < 60:
        return f'{diff}s ago'
    if diff < 3600:
        return f'{diff // 60}m ago'
    if diff < 86400:
        return f'{diff // 3600}h ago'
    return f'{diff // 86400}d ago'


def collect_rows():
    mapping = load_map()
    out = subprocess.check_output(['wg', 'show', WG_IF, 'dump'], text=True)
    now = time.time()
    changed = False
    rows = []
    for idx, line in enumerate(out.splitlines()):
        if idx == 0 or not line.strip():
            continue
        key, _psk, endpoint, allowed, hs, rx, tx, _ka = line.split('\t')
        rx_i = int(rx)
        tx_i = int(tx)
        hs_i = int(hs)
        meta = mapping.get(key, {})
        prev = STATE.get(key)
        rx_rate = 0.0
        tx_rate = 0.0
        if prev:
            delta = max(now - prev['ts'], 1e-6)
            rx_rate = max(0.0, (rx_i - prev['rx']) / delta)
            tx_rate = max(0.0, (tx_i - prev['tx']) / delta)
        STATE[key] = {'rx': rx_i, 'tx': tx_i, 'ts': now}
        peak = PEAKS.get(key, {"rx": 0, "tx": 0})
        peak_rx = int(peak.get("rx", 0))
        peak_tx = int(peak.get("tx", 0))
        if int(rx_rate) > peak_rx:
            peak_rx = int(rx_rate)
            changed = True
        if int(tx_rate) > peak_tx:
            peak_tx = int(tx_rate)
            changed = True
        PEAKS[key] = {"rx": peak_rx, "tx": peak_tx}
        ip_value = meta.get('ip', allowed.split(',', 1)[0].split('/', 1)[0])
        rows.append({
            'name': meta.get('name', f'{key[:8]}...'),
            'ip': ip_value,
            'endpoint': '-' if endpoint == '(none)' else endpoint,
            'handshake': handshake_text(hs_i),
            'rx_total': human_bytes(rx_i),
            'tx_total': human_bytes(tx_i),
            'rx_rate': human_rate(rx_rate),
            'tx_rate': human_rate(tx_rate),
            'top_rx_rate': human_rate(peak_rx),
            'top_tx_rate': human_rate(peak_tx),
        })
    if changed:
        save_peaks()
    rows.sort(key=lambda row: tuple(int(part) for part in row['ip'].split('.')) if row['ip'].count('.') == 3 else (999, row['ip']))
    return rows


HTML = f'''<!doctype html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GWHUB-WG Traffic control</title>
<style>
:root {{ color-scheme: dark; --bg:#05070c; --bg2:#0b1220; --panel:rgba(11,13,18,.96); --panel-2:rgba(15,18,24,.98); --line:#1f2736; --text:#eef2fb; --muted:#9099ab; --acc:#22c55e; --acc2:#38bdf8; --warn:#f59e0b; --chip:#121722; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; font-family: Inter, \"Segoe UI\", system-ui, -apple-system, sans-serif; background: radial-gradient(circle at top, #172947 0, #0a111d 18%, var(--bg) 54%, #020307 100%); color:var(--text); }}
main {{ max-width: 1280px; margin: 0 auto; padding: 20px 14px 32px; }}
header {{ display:flex; align-items:flex-start; justify-content:space-between; gap:14px; margin-bottom:14px; }}
.title-wrap {{ min-width:0; }}
h1 {{ margin:0; font-size: clamp(24px, 5vw, 34px); line-height:1.05; letter-spacing:-0.03em; font-weight:800; }}
.updated {{ white-space:nowrap; border:1px solid #26314a; background:rgba(13,18,30,.88); padding:10px 12px; border-radius:14px; font-size:13px; color:var(--muted); font-family: Inter, \"Segoe UI\", system-ui, -apple-system, sans-serif; }}
.summary-grid {{ display:grid; grid-template-columns:repeat(4, minmax(0, 1fr)); gap:10px; margin-bottom:14px; }}
.summary-card {{ background:linear-gradient(180deg, rgba(15,18,24,.98), rgba(9,11,16,.98)); border:1px solid var(--line); border-radius:16px; padding:12px 14px; min-width:0; box-shadow:0 10px 30px rgba(0,0,0,.18); }}
.summary-label {{ color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.08em; margin-bottom:8px; font-weight:700; }}
.summary-value {{ font-size:28px; font-weight:780; line-height:1; letter-spacing:-0.04em; }}
.summary-sub {{ color:var(--muted); font-size:12px; margin-top:8px; }}
.section-panel {{ background:linear-gradient(180deg, rgba(10,12,17,.98), rgba(7,9,13,.98)); border:1px solid var(--line); border-radius:18px; overflow:hidden; box-shadow:0 10px 35px rgba(0,0,0,.25); }}
.section-head {{ display:flex; align-items:center; justify-content:space-between; gap:12px; padding:16px 18px 12px; border-bottom:1px solid var(--line); }}
.section-title {{ font-size:20px; font-weight:760; letter-spacing:-0.03em; }}
.section-subtitle {{ color:var(--muted); font-size:12px; margin-top:4px; }}
.table-wrap {{ background:transparent; overflow:hidden; }}
table {{ width:100%; border-collapse:collapse; table-layout:fixed; }}
th, td {{ padding:12px 10px; border-bottom:1px solid var(--line); text-align:left; font-size:14px; vertical-align:middle; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; font-variant-numeric: tabular-nums; }}
th {{ color:var(--muted); font-weight:620; font-size:12px; text-transform:uppercase; letter-spacing:.03em; background:rgba(12,14,19,.94); font-family: Inter, \"Segoe UI\", system-ui, -apple-system, sans-serif; }}
tr:last-child td {{ border-bottom:none; }}
tr:hover td {{ background:rgba(255,255,255,.02); }}
th:last-child, td:last-child {{ text-align:center; }}
td, .ip, .endpoint-mobile, .stats-value, .value {{ font-family: Inter, \"Segoe UI\", system-ui, -apple-system, sans-serif; font-weight:540; font-variant-numeric: tabular-nums; }}
.name {{ font-weight:660; font-family: Inter, \"Segoe UI\", system-ui, -apple-system, sans-serif; }}
.client-cell {{ display:flex; align-items:center; gap:8px; min-width:0; }}
.client-dot {{ width:7px; height:7px; border-radius:999px; background:#737b8f; flex:0 0 auto; }}
.status-pill {{ display:inline-flex; align-items:center; justify-content:center; min-width:92px; padding:4px 12px; border-radius:999px; font-size:11px; font-weight:650; letter-spacing:.02em; font-family: Inter, \"Segoe UI\", system-ui, -apple-system, sans-serif; }}
.status-active {{ color:#eafff0; background:rgba(34,197,94,.16); border:1px solid rgba(34,197,94,.28); }}
.status-idle {{ color:#fff6e6; background:rgba(245,158,11,.14); border:1px solid rgba(245,158,11,.24); }}
.status-offline {{ color:#ffe8e8; background:rgba(239,68,68,.14); border:1px solid rgba(239,68,68,.24); }}
.rate-rx {{ color: var(--acc2); font-weight:700; }}
.rate-tx {{ color: var(--acc); font-weight:700; }}
.rate-top {{ color: var(--warn); font-weight:700; }}
.col-client {{ width: 116px; }}
.col-ip {{ width: 96px; }}
.col-rate {{ width: 118px; }}
.col-top {{ width: 196px; }}
.col-total {{ width: 220px; }}
.col-handshake {{ width: 124px; }}
.col-endpoint {{ width: 184px; }}
.mobile-cards {{ display:none; gap:6px; }}
.card {{ background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:7px 8px; box-shadow:0 10px 35px rgba(0,0,0,.16); }}
.card-top {{ display:flex; justify-content:space-between; gap:8px; align-items:flex-start; margin-bottom:4px; }}
.ip {{ color:var(--muted); font-size:12px; font-weight:540; margin-top:1px; }}
.endpoint-mobile {{ color:var(--muted); font-size:10px; font-weight:500; line-height:1.2; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; margin-bottom:5px; }}
.stats-table {{ width:100%; border-collapse:collapse; table-layout:fixed; }}
.stats-table td {{ border-bottom:1px solid rgba(32,50,82,.7); padding:5px 3px; vertical-align:top; }}
.stats-table tr:last-child td {{ border-bottom:none; }}
.stats-label {{ color:var(--muted); font-size:9px; font-weight:680; text-transform:uppercase; letter-spacing:.12em; margin-bottom:2px; }}
.stats-value {{ font-size:15px; font-weight:700; line-height:1; }}
.speed-value.rx {{ color:var(--acc2); }}
.speed-value.tx {{ color:var(--acc); }}
.stats-value.rx {{ color:var(--acc2); }}
.stats-value.tx {{ color:var(--acc); }}
.stats-value.top {{ color:var(--warn); }}
.label {{ color:var(--muted); font-size:9px; font-weight:680; text-transform:uppercase; letter-spacing:.08em; margin-bottom:2px; }}
.value {{ font-size:12px; font-weight:560; overflow-wrap:anywhere; line-height:1.05; }}
@media (max-width: 780px) {{
  main {{ padding: 10px 8px 18px; }}
  header {{ flex-direction:column; align-items:flex-start; gap:8px; margin-bottom:10px; }}
  h1 {{ font-size: 24px; }}
  .updated {{ padding:6px 8px; border-radius:10px; font-size:12px; }}
  .summary-grid {{ grid-template-columns:repeat(2, minmax(0, 1fr)); gap:6px; margin-bottom:10px; }}
  .summary-card {{ padding:8px 9px; border-radius:12px; }}
  .summary-label {{ font-size:9px; margin-bottom:5px; }}
  .summary-value {{ font-size:18px; }}
  .summary-sub {{ font-size:10px; margin-top:5px; }}
  .table-wrap {{ display:none; }}
  .mobile-cards {{ display:grid; }}
}}
</style>
</head>
<body>
<main>
<header>
  <div class="title-wrap">
    <h1>GWHUB-WG Traffic control</h1>
  </div>
  <div class="updated" id="updated">Ultimo aggiornamento ora</div>
</header>
<section class="summary-grid" id="summary">
  <div class="summary-card">
    <div class="summary-label">Client</div>
    <div class="summary-value" id="sum-clients">0</div>
    <div class="summary-sub">Peer configurati</div>
  </div>
  <div class="summary-card">
    <div class="summary-label">Attivi</div>
    <div class="summary-value" id="sum-active">0</div>
    <div class="summary-sub">Handshake recente</div>
  </div>
  <div class="summary-card">
    <div class="summary-label">Download live</div>
    <div class="summary-value rate-rx" id="sum-rx">0 B/s</div>
    <div class="summary-sub">Somma client</div>
  </div>
  <div class="summary-card">
    <div class="summary-label">Upload live</div>
    <div class="summary-value rate-tx" id="sum-tx">0 B/s</div>
    <div class="summary-sub">Somma client</div>
  </div>
</section>
<section class="section-panel">
<div class="section-head">
  <div>
    <div class="section-title">Peer</div>
    <div class="section-subtitle">Monitoraggio traffico WireGuard in tempo reale</div>
  </div>
</div>
<div class="table-wrap">
<table>
<colgroup>
<col class="col-client">
<col class="col-ip">
<col class="col-rate">
<col class="col-rate">
<col class="col-top">
<col class="col-total">
<col class="col-endpoint">
<col class="col-handshake">
</colgroup>
<thead>
<tr><th>Client</th><th>IP</th><th>Download</th><th>Upload</th><th>Picco DW/UP</th><th>Scaricati / Inviati</th><th>Endpoint</th><th>Stato</th></tr>
</thead>
<tbody id="rows"></tbody>
</table>
</div>
</section>
<div class="mobile-cards" id="mobile-rows"></div>
</main>
<script>
function esc(v) {{
  return String(v).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');
}}
function parseRateToBytes(v) {{
  const s = String(v || '').trim();
  const m = s.match(/^([0-9]+(?:\.[0-9]+)?)\s*(B|KiB|MiB|GiB|TiB)\/s$/);
  if (!m) return 0;
  const value = Number(m[1]);
  const unit = m[2];
  const factors = {{ B: 1, KiB: 1024, MiB: 1024 ** 2, GiB: 1024 ** 3, TiB: 1024 ** 4 }};
  return Math.round(value * (factors[unit] || 1));
}}
function humanBytes(v) {{
  const units = ['B', 'KiB', 'MiB', 'GiB', 'TiB'];
  let n = Number(v || 0);
  let i = 0;
  while (n >= 1024 && i < units.length - 1) {{
    n /= 1024;
    i += 1;
  }}
  if (units[i] === 'B') return `${{Math.round(n)}} B/s`;
  return `${{n.toFixed(2)}} ${{units[i]}}/s`;
}}
function isRecentHandshake(v) {{
  if (!v || v === 'never') return false;
  const m = String(v).match(/^([0-9]+)([smhd]) ago$/);
  if (!m) return false;
  const value = Number(m[1]);
  const unit = m[2];
  if (unit === 's' || unit === 'm' || unit === 'h') return true;
  return unit === 'd' && value <= 1;
}}
function statusMeta(handshake) {{
  if (!handshake || handshake === 'never') return {{ label: 'Offline', cls: 'status-offline', dot: '#ef4444' }};
  const m = String(handshake).match(/^([0-9]+)([smhd]) ago$/);
  if (!m) return {{ label: 'Idle', cls: 'status-idle', dot: '#f59e0b' }};
  const value = Number(m[1]);
  const unit = m[2];
  if (unit === 's' || unit === 'm' || unit === 'h' || (unit === 'd' && value <= 1)) {{
    return {{ label: 'Attivo', cls: 'status-active', dot: '#22c55e' }};
  }}
  return {{ label: 'Idle', cls: 'status-idle', dot: '#f59e0b' }};
}}
async function load() {{
  const res = await fetch('/api');
  const data = await res.json();
  const tbody = document.getElementById('rows');
  const mobile = document.getElementById('mobile-rows');
  const totalRx = data.rows.reduce((sum, r) => sum + parseRateToBytes(r.rx_rate), 0);
  const totalTx = data.rows.reduce((sum, r) => sum + parseRateToBytes(r.tx_rate), 0);
  const active = data.rows.filter(r => isRecentHandshake(r.handshake)).length;
  document.getElementById('sum-clients').textContent = data.rows.length;
  document.getElementById('sum-active').textContent = active;
  document.getElementById('sum-rx').textContent = humanBytes(totalRx);
  document.getElementById('sum-tx').textContent = humanBytes(totalTx);
  tbody.innerHTML = data.rows.map(r => {{
    const status = statusMeta(r.handshake);
    return `
    <tr>
      <td><div class="client-cell"><span class="client-dot" style="background:${{status.dot}}"></span><span class="name">${{esc(r.name)}}</span></div></td>
      <td>${{esc(r.ip)}}</td>
      <td class="rate-rx">${{esc(r.rx_rate)}}</td>
      <td class="rate-tx">${{esc(r.tx_rate)}}</td>
      <td class="rate-top">${{esc(r.top_rx_rate)}} / ${{esc(r.top_tx_rate)}}</td>
      <td>${{esc(r.rx_total)}} / ${{esc(r.tx_total)}}</td>
      <td>${{esc(r.endpoint)}}</td>
      <td><span class="status-pill ${{status.cls}}">${{status.label}}</span></td>
    </tr>`;
  }}).join('');
  mobile.innerHTML = data.rows.map(r => `
    <section class="card">
      <div class="card-top">
        <div>
          <div class="name">${{esc(r.name)}}</div>
          <div class="ip">${{esc(r.ip)}}</div>
        </div>
        <div class="label">${{esc(r.handshake)}}</div>
      </div>
      <div class="endpoint-mobile">${{esc(r.endpoint)}}</div>
      <table class="stats-table">
        <tr>
          <td><div class="stats-label">Download</div><div class="stats-value rx">${{esc(r.rx_rate)}}</div></td>
          <td><div class="stats-label">Upload</div><div class="stats-value tx">${{esc(r.tx_rate)}}</div></td>
        </tr>
        <tr>
          <td><div class="stats-label">Picco download</div><div class="stats-value top">${{esc(r.top_rx_rate)}}</div></td>
          <td><div class="stats-label">Picco upload</div><div class="stats-value top">${{esc(r.top_tx_rate)}}</div></td>
        </tr>
        <tr>
          <td><div class="stats-label">Scaricati</div><div class="value">${{esc(r.rx_total)}}</div></td>
          <td><div class="stats-label">Inviati</div><div class="value">${{esc(r.tx_total)}}</div></td>
        </tr>
      </table>
    </section>`).join('');
  document.getElementById('updated').textContent = 'Ultimo aggiornamento ' + new Date().toLocaleTimeString('it-IT');
}}
load();
setInterval(load, {REFRESH_MS});
</script>
</body>
</html>'''


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/api':
            rows = collect_rows()
            payload = json.dumps({'rows': rows}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        if self.path == '/' or self.path.startswith('/?'):
            body = HTML.encode()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404)

    def log_message(self, _format, *_args):
        return


if __name__ == '__main__':
    load_peaks()
    server = ThreadingHTTPServer((BIND_HOST, PORT), Handler)
    server.serve_forever()
