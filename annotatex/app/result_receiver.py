"""Simple result receiver — listens on a port and shows detection results in the browser.

GET  /        → HTML dashboard (auto-refreshes via JS polling)
POST /result  → receives JSON from a detection service
GET  /api/results → returns last N results per service as JSON
"""
from __future__ import annotations

import threading
import logging
from collections import deque
from datetime import datetime
from typing import Optional

log = logging.getLogger("result_receiver")

_MAX_PER_SERVICE = 100  # how many results to keep per service

_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>VisionQ — Detection Results</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: #0f172a; color: #e2e8f0;
    font-family: monospace; padding: 24px;
    min-height: 100vh;
  }
  /* ── Header ── */
  .header { margin-bottom: 24px; }
  h1 { color: #a78bfa; font-size: 20px; margin-bottom: 4px; }
  .sub { color: #475569; font-size: 12px; }
  #global-status {
    font-size: 11px; color: #64748b;
    display: flex; align-items: center; gap: 6px; margin-top: 10px;
  }
  .dot {
    display: inline-block; width: 8px; height: 8px; border-radius: 50%;
    background: #4ade80; animation: pulse 1.5s infinite;
  }
  .offline .dot { background: #f87171; animation: none; }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.3} }

  /* ── Service panels grid ── */
  #panels {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(480px, 1fr));
    gap: 20px;
    align-items: start;
  }
  .panel {
    background: #1e293b; border-radius: 10px;
    border: 1px solid #334155; overflow: hidden;
  }

  /* ── Panel header ── */
  .panel-header {
    display: flex; align-items: center; justify-content: space-between;
    padding: 12px 16px; border-bottom: 1px solid #334155;
    background: #0f172a;
  }
  .panel-name { color: #a78bfa; font-size: 14px; font-weight: bold; }
  .panel-status {
    font-size: 10px; color: #64748b;
    display: flex; align-items: center; gap: 5px;
  }
  .panel-status .dot { width: 6px; height: 6px; }

  /* ── Panel stats ── */
  .panel-stats {
    display: flex; gap: 0;
    border-bottom: 1px solid #334155;
  }
  .stat {
    flex: 1; padding: 10px 14px;
    border-right: 1px solid #334155;
  }
  .stat:last-child { border-right: none; }
  .stat-val { font-size: 20px; font-weight: bold; color: #a78bfa; }
  .stat-lbl { font-size: 10px; color: #64748b; margin-top: 2px; }

  /* ── Panel table ── */
  .panel-table-wrap {
    max-height: 320px; overflow-y: auto;
  }
  table { width: 100%; border-collapse: collapse; font-size: 11px; }
  th {
    background: #0f172a; color: #475569; font-size: 9px;
    letter-spacing: 1px; text-align: left;
    padding: 6px 12px; border-bottom: 1px solid #334155;
    position: sticky; top: 0; z-index: 1;
  }
  td { padding: 6px 12px; border-bottom: 1px solid #1e293b44; vertical-align: middle; }
  tr:hover td { background: #ffffff08; }

  /* ── State colours ── */
  .car     { color: #4ade80; font-weight: bold; }
  .nocar   { color: #475569; }
  .fwd     { color: #60a5fa; }
  .bwd     { color: #f97316; }
  .idle-cl { color: #facc15; }
  .unk     { color: #475569; }

  /* ── Empty / no-services placeholder ── */
  #empty {
    color: #334155; font-size: 13px; text-align: center;
    padding: 60px 0; display: none;
  }
  #empty.visible { display: block; }
</style>
</head>
<body>

<div class="header">
  <h1>⚡ VisionQ — Detection Results</h1>
  <p class="sub">Each active service appears as its own panel</p>
  <div id="global-status">
    <span class="dot"></span>
    <span id="status-text">Connecting…</span>
  </div>
</div>

<div id="panels"></div>
<div id="empty">No services have reported yet.</div>

<script>
// panels we've already created  {serviceName -> true}
const knownPanels = {};

async function poll() {
  try {
    const r = await fetch('/api/results');
    const byService = await r.json();  // { service_name: [rows...] }

    setStatus(true);
    const names = Object.keys(byService);

    if (names.length === 0) {
      document.getElementById('empty').classList.add('visible');
    } else {
      document.getElementById('empty').classList.remove('visible');
      names.forEach(name => {
        if (!knownPanels[name]) createPanel(name);
        renderPanel(name, byService[name]);
      });
    }
  } catch(e) {
    setStatus(false);
  }
}

function setStatus(online) {
  const el = document.getElementById('global-status');
  el.classList.toggle('offline', !online);
  document.getElementById('status-text').textContent = online ? 'Live' : 'Disconnected';
}

function createPanel(name) {
  knownPanels[name] = true;
  const id = panelId(name);
  const div = document.createElement('div');
  div.className = 'panel';
  div.id = id;
  div.innerHTML = `
    <div class="panel-header">
      <span class="panel-name">${escHtml(name)}</span>
      <span class="panel-status"><span class="dot"></span><span class="ps-text">waiting…</span></span>
    </div>
    <div class="panel-stats">
      <div class="stat"><div class="stat-val" id="${id}-total">0</div><div class="stat-lbl">Reports</div></div>
      <div class="stat"><div class="stat-val" id="${id}-cars">0</div><div class="stat-lbl">Car</div></div>
      <div class="stat"><div class="stat-val" id="${id}-rears">0</div><div class="stat-lbl">Car rear</div></div>
      <div class="stat"><div class="stat-val" id="${id}-dir">—</div><div class="stat-lbl">Last dir</div></div>
    </div>
    <div class="panel-table-wrap">
      <table>
        <thead><tr>
          <th>TIME</th><th>CAR</th><th>CAR DIR</th><th>REAR</th><th>REAR DIR</th><th>FRAMES</th>
        </tr></thead>
        <tbody id="${id}-tbody"></tbody>
      </table>
    </div>
  `;
  document.getElementById('panels').appendChild(div);
}

function renderPanel(name, rows) {
  const id = panelId(name);
  const panel = document.getElementById(id);
  if (!panel) return;

  // Stats
  const carRows  = rows.filter(r => r.car?.detected);
  const rearRows = rows.filter(r => r.car_rear?.detected);
  setText(id + '-total', rows.length);
  setText(id + '-cars',  carRows.length);
  setText(id + '-rears', rearRows.length);

  const latest = rows[0];
  if (latest) {
    const carDir  = latest.car?.direction      || '—';
    const rearDir = latest.car_rear?.direction || '—';
    setText(id + '-dir', carDir === rearDir ? carDir : carDir + ' / ' + rearDir);
  }

  // Status dot — "live" if last result arrived recently
  const dot = panel.querySelector('.panel-status .dot');
  const psText = panel.querySelector('.ps-text');
  if (rows.length > 0) {
    dot.style.background = '#4ade80';
    dot.style.animation = 'pulse 1.5s infinite';
    psText.textContent = 'Live · ' + (rows[0].timestamp || '');
  }

  // Table rows
  const tbody = document.getElementById(id + '-tbody');
  tbody.innerHTML = rows.map(r => {
    const car  = r.car      || {};
    const rear = r.car_rear || {};
    const carConf  = car.detected  && car.confidence  ? ' ' + (car.confidence  * 100).toFixed(0) + '%' : '';
    const rearConf = rear.detected && rear.confidence ? ' ' + (rear.confidence * 100).toFixed(0) + '%' : '';
    return `
    <tr>
      <td style="color:#475569">${r.timestamp || '—'}</td>
      <td class="${car.detected  ? 'car' : 'nocar'}">${car.detected  ? '● CAR'  : '○ —'}</td>
      <td class="${dirClass(car.direction)}">${car.detected   ? (car.direction  || '—') + carConf  : '—'}</td>
      <td class="${rear.detected ? 'car' : 'nocar'}">${rear.detected ? '● REAR' : '○ —'}</td>
      <td class="${dirClass(rear.direction)}">${rear.detected ? (rear.direction || '—') + rearConf : '—'}</td>
      <td style="color:#64748b">${r.frames_analyzed ?? '—'}</td>
    </tr>
  `;
  }).join('');
}

function dirClass(d) {
  if (d === 'forward')  return 'fwd';
  if (d === 'backward') return 'bwd';
  if (d === 'idle')     return 'idle-cl';
  return 'unk';
}
function panelId(name) { return 'svc-' + name.replace(/[^a-zA-Z0-9]/g, '_'); }
function setText(id, val) { const el = document.getElementById(id); if (el) el.textContent = val; }
function escHtml(s) { return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

setInterval(poll, 800);
poll();
</script>
</body>
</html>
"""


class ResultReceiver:
    """Lightweight Flask server that receives and displays detection results."""

    def __init__(self):
        # Results stored per service: { service_name: deque[dict] }
        self._results: dict[str, deque] = {}
        self._lock = threading.Lock()
        self._server = None
        self._thread: Optional[threading.Thread] = None
        self._running = False

    def start(self, host: str = "127.0.0.1", port: int = 6060) -> str:
        """Start the receiver. Returns error string or empty string on success."""
        if self._running:
            return ""

        from flask import Flask, request, jsonify, Response
        app = Flask("result_receiver")
        logging.getLogger("werkzeug").setLevel(logging.ERROR)

        receiver = self  # closure ref

        @app.route("/", methods=["GET"])
        def index():
            return Response(_HTML, mimetype="text/html")

        @app.route("/result", methods=["POST"])
        def receive():
            data = request.get_json(silent=True) or {}
            data["timestamp"] = datetime.now().strftime("%H:%M:%S")
            name = data.get("service_name") or "unknown"
            with receiver._lock:
                if name not in receiver._results:
                    receiver._results[name] = deque(maxlen=_MAX_PER_SERVICE)
                receiver._results[name].appendleft(data)
            return jsonify({"ok": True})

        @app.route("/api/results", methods=["GET"])
        def api_results():
            with receiver._lock:
                return jsonify({
                    name: list(q)
                    for name, q in receiver._results.items()
                })

        from werkzeug.serving import make_server
        try:
            self._server = make_server(host, port, app)
        except Exception as e:
            return f"Cannot bind result receiver to {host}:{port} — {e}"

        self._running = True
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            daemon=True,
            name="ResultReceiver",
        )
        self._thread.start()
        log.info(f"Result receiver listening on http://{host}:{port}/")
        return ""

    def stop(self):
        if self._server:
            self._server.shutdown()
            self._server = None
        self._running = False
        self._thread = None
        with self._lock:
            self._results.clear()

    @property
    def is_running(self) -> bool:
        return self._running


_receiver = ResultReceiver()


def get_receiver() -> ResultReceiver:
    return _receiver
