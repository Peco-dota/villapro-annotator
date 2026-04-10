"""Simple result receiver — listens on a port and shows detection results in the browser.

GET  /        → HTML dashboard (auto-refreshes)
POST /result  → receives JSON from detection service
GET  /api/results → returns last N results as JSON (used by dashboard JS)
"""
from __future__ import annotations

import threading
import logging
from collections import deque
from datetime import datetime
from typing import Optional

log = logging.getLogger("result_receiver")

_MAX_RESULTS = 200

_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>VisionQ — Detection Results</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: #0f172a; color: #e2e8f0; font-family: monospace; padding: 24px; }
  h1 { color: #a78bfa; font-size: 20px; margin-bottom: 6px; }
  .sub { color: #475569; font-size: 12px; margin-bottom: 20px; }
  .stats { display: flex; gap: 16px; margin-bottom: 20px; flex-wrap: wrap; }
  .stat { background: #1e293b; border-radius: 8px; padding: 12px 20px; min-width: 130px; }
  .stat-val { font-size: 28px; font-weight: bold; color: #a78bfa; }
  .stat-lbl { font-size: 11px; color: #64748b; margin-top: 2px; }
  table { width: 100%; border-collapse: collapse; font-size: 12px; }
  th { background: #1e293b; color: #64748b; font-size: 10px; letter-spacing: 1px;
       text-align: left; padding: 8px 12px; border-bottom: 1px solid #334155; }
  td { padding: 7px 12px; border-bottom: 1px solid #1e293b; vertical-align: middle; }
  tr:hover td { background: #1e293b44; }
  .car { color: #4ade80; font-weight: bold; }
  .nocar { color: #475569; }
  .fwd { color: #60a5fa; }
  .bwd { color: #f97316; }
  .unk { color: #475569; }
  .dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%;
         background: #4ade80; margin-right: 6px; animation: pulse 1.5s infinite; }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.3} }
  .offline .dot { background: #f87171; animation: none; }
  #status { font-size: 11px; color: #64748b; display: flex; align-items: center; gap: 6px; margin-bottom: 16px; }
</style>
</head>
<body>
<h1>⚡ VisionQ — Detection Results</h1>
<p class="sub">Live feed from detection services</p>
<div id="status"><span class="dot"></span><span id="status-text">Connecting…</span></div>
<div class="stats">
  <div class="stat"><div class="stat-val" id="total">0</div><div class="stat-lbl">Total detections</div></div>
  <div class="stat"><div class="stat-val" id="cars">0</div><div class="stat-lbl">Cars detected</div></div>
  <div class="stat"><div class="stat-val" id="last-conf">—</div><div class="stat-lbl">Last confidence</div></div>
  <div class="stat"><div class="stat-val" id="last-dir">—</div><div class="stat-lbl">Last direction</div></div>
</div>
<table>
  <thead>
    <tr>
      <th>TIME</th>
      <th>SERVICE</th>
      <th>DETECTED</th>
      <th>DIRECTION</th>
      <th>CONFIDENCE</th>
      <th>FRAMES</th>
    </tr>
  </thead>
  <tbody id="tbody"></tbody>
</table>
<script>
let seen = 0;
async function poll() {
  try {
    const r = await fetch('/api/results');
    const data = await r.json();
    document.getElementById('status').classList.remove('offline');
    document.getElementById('status-text').textContent = 'Live';
    render(data);
  } catch(e) {
    document.getElementById('status').classList.add('offline');
    document.getElementById('status-text').textContent = 'Disconnected';
  }
}
function render(rows) {
  document.getElementById('total').textContent = rows.length;
  const cars = rows.filter(r => r.car_detected);
  document.getElementById('cars').textContent = cars.length;
  if (cars.length > 0) {
    const last = cars[0];
    document.getElementById('last-conf').textContent = (last.confidence * 100).toFixed(1) + '%';
    document.getElementById('last-dir').textContent = last.direction || '—';
  }
  const tbody = document.getElementById('tbody');
  tbody.innerHTML = rows.map(r => `
    <tr>
      <td style="color:#475569">${r.timestamp}</td>
      <td style="color:#94a3b8">${r.service_name || '—'}</td>
      <td class="${r.car_detected ? 'car' : 'nocar'}">${r.car_detected ? '● CAR' : '○ no car'}</td>
      <td class="${dirClass(r.direction)}">${r.direction || '—'}</td>
      <td style="color:#e2e8f0">${r.car_detected ? (r.confidence * 100).toFixed(1) + '%' : '—'}</td>
      <td style="color:#64748b">${r.frames_analyzed ?? '—'}</td>
    </tr>
  `).join('');
}
function dirClass(d) {
  if (d === 'forward') return 'fwd';
  if (d === 'backward') return 'bwd';
  return 'unk';
}
setInterval(poll, 800);
poll();
</script>
</body>
</html>
"""


class ResultReceiver:
    """Lightweight Flask server that receives and displays detection results."""

    def __init__(self):
        self._results: deque[dict] = deque(maxlen=_MAX_RESULTS)
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
            with receiver._lock:
                receiver._results.appendleft(data)
            return jsonify({"ok": True})

        @app.route("/api/results", methods=["GET"])
        def api_results():
            with receiver._lock:
                return jsonify(list(receiver._results))

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

    @property
    def is_running(self) -> bool:
        return self._running


_receiver = ResultReceiver()


def get_receiver() -> ResultReceiver:
    return _receiver
