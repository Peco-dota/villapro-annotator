# VisionQ — Architecture & Developer Reference

## What this app is

A headless server that runs on an Ubuntu machine (with a GPU/camera setup) and exposes:
1. A REST + SSE API for the web UI and other HTTP clients
2. A TCP push server per detection service for machine-to-machine integrations
3. A React web UI served statically (or via Vite dev server in development)

Users access the web UI from their own PC over the local network. The Ubuntu machine does all the heavy lifting (YOLO inference, training, recording, etc.).

---

## Stack

| Layer | Technology |
|---|---|
| Server | Python, FastAPI, Uvicorn |
| Database | SQLite (via SQLAlchemy) — stores users, project metadata, annotations |
| Config file | JSON — `~/.config/visionq.json` (path overridable with `-c`) |
| ML inference | Ultralytics YOLO (runs in background threads) |
| Frontend | React + TypeScript + Vite + TailwindCSS |
| Auth | JWT (login) + API tokens (for SSE / machine clients) |

---

## Starting the server

```bash
# Default config path (~/.config/visionq.json)
python main.py

# Custom config path
python main.py -c /etc/visionq/config.json

# Override host/port on top of config file
python main.py -c /etc/visionq/config.json --host 0.0.0.0 --port 9000

# Dev mode with auto-reload
python main.py --reload
```

Config file is JSON and is read at startup, written back whenever settings change via the API:

```json
{
  "host": "0.0.0.0",
  "port": 8000,
  "ssl_certfile": "",
  "ssl_keyfile": "",
  "api_tokens": [
    { "name": "my_token", "token": "abc123..." }
  ]
}
```

If `ssl_certfile` + `ssl_keyfile` are set, the server starts with HTTPS automatically (Uvicorn handles it).

---

## Running as a systemd service (Ubuntu production)

Create `/etc/systemd/system/visionq.service`:

```ini
[Unit]
Description=VisionQ Server
After=network.target

[Service]
User=visionq
WorkingDirectory=/opt/visionq/server
ExecStart=/opt/visionq/server/.venv/bin/python main.py -c /etc/visionq/config.json
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Then:
```bash
sudo systemctl enable visionq
sudo systemctl start visionq
sudo journalctl -u visionq -f   # view logs
```

---

## How SSE works (browser ↔ server)

SSE = Server-Sent Events. The browser opens one long-lived HTTP connection and the server pushes events down it — no polling needed.

Used for:
- Live detection results in the web UI (inline preview panel, receiver dashboard)
- Training log streaming

```
Browser → GET /api/detection/services/camera_01/stream?token=xxx
Server  ← data: {"car":{"detected":true,"direction":"forward","confidence":0.91},...}\n\n
Server  ← data: {"car":{"detected":false,...}}\n\n
         ...forever until browser closes the tab
```

Auth: the token is passed as a query param (`?token=xxx`) because browsers can't set headers on EventSource connections.

Relevant files:
- `server/app/routers/detection.py` — `GET /services/{name}/stream` endpoint
- `frontend/src/components/detection/ServiceCard.tsx` — `useServiceResults` hook (SSE + polling fallback)

---

## How TCP push works (machine ↔ machine)

TCP push is a separate raw TCP socket that the server opens per detection service. The customer's other systems (gate controllers, alarm panels, building management software) connect to it and receive the same detection events as newline-delimited JSON.

```
Their app → connects to ubuntu-machine:9001
Server    ← {"service_name":"camera_01","car":{"detected":true,"direction":"forward"}}\n
Server    ← {"type":"keepalive"}\n   (every 5 seconds)
           ...forever
```

- One JSON object per line, `\n` separated
- N clients can connect simultaneously — all receive every event
- Optional TLS / mTLS (configure cert + key paths in the service config)
- Keepalive every 5s so NAT sessions and dead clients are detected

How to enable: in the web UI → Detection → Edit service → TCP Push section → enable + set port.

Relevant files:
- `server/app/tcp_push.py` — full TCP server implementation
- `server/app/routers/detection.py` — `/services/{name}/tcp/start` and `/stop` endpoints
- `frontend/src/components/detection/ServiceForm.tsx` — TCP Push config section
- `frontend/src/components/detection/ServiceCard.tsx` — TCP start/stop button

---

## Detection service lifecycle

Each "service" is one camera/video/HTTP source running YOLO inference in a background thread.

```
create config → startService() → background thread starts
                                 ↓ reads frames
                                 ↓ runs YOLO
                                 ↓ computes direction (forward/backward/idle/no_car)
                                 ↓ _notify_internal(name, payload)
                                      ├── SSE queue → browser
                                      ├── result buffer → polling fallback
                                      └── TCP push → external clients
```

States: `stopped` → `loading` → `running` → `stopped` (or `error`)

Relevant files:
- `server/app/detection_service.py` — inference loop, direction logic, recording, dataset capture
- `server/app/routers/detection.py` — REST API for managing services

---

## Direction logic

The service computes car direction based on bounding box movement across frames:
- `forward` — car moving toward gate
- `backward` — car moving away from gate
- `idle` — car present but not moving
- `no_car` — no detection above confidence threshold

Gate trigger: if `gate_area_threshold > 0` and an idle car's bbox area ≥ threshold → `gate_open: true` in the payload.

Debug CSV: start with the Debug button on the service card → saves per-frame bbox signals to `~/VisionQ_debug/<service_name>/debug_<timestamp>.csv` — use this to tune the gate threshold (read the `area` column).

---

## Training

Training runs YOLO fine-tuning on an exported dataset. It runs in a background thread (not async) so it can be force-killed.

- Graceful stop: sets a flag, training stops after the current epoch finishes
- Force stop: injects `KeyboardInterrupt` into the training thread via `ctypes.PyThreadState_SetAsyncExc`
- Progress survives page refresh: `jobId` is stored in `localStorage`, `GET /api/datasets/train/active` reconnects on reload
- Best weights saved to: `~/visionq-projects/models/<run_name>/weights/best.pt`

Relevant files:
- `server/app/routers/datasets.py` — train, cancel, active endpoints
- `frontend/src/components/train/TrainModel.tsx` — full training UI

---

## File layout

```
villapro-annotator/
├── server/
│   ├── main.py                  ← entry point, argparse, uvicorn startup
│   ├── app/
│   │   ├── config.py            ← JSON config file loader/writer
│   │   ├── db.py                ← SQLite setup
│   │   ├── detection_service.py ← YOLO inference, direction, recording
│   │   ├── tcp_push.py          ← TCP/SSL push server
│   │   ├── project.py           ← annotation project model
│   │   └── routers/
│   │       ├── auth.py          ← login, JWT, change password
│   │       ├── system.py        ← settings, tokens, system info
│   │       ├── projects.py      ← project CRUD, images, classes
│   │       ├── annotations.py   ← annotation CRUD
│   │       ├── detection.py     ← services, SSE, TCP, preview, recording
│   │       ├── datasets.py      ← export, augment, merge, train
│   │       └── fs.py            ← filesystem browse (for file pickers)
└── frontend/
    ├── src/
    │   ├── App.tsx              ← router
    │   ├── pages/               ← full page components
    │   ├── components/
    │   │   ├── annotate/        ← canvas, image list, class sidebar, toolbar
    │   │   ├── detection/       ← service cards, receiver dashboard, preview
    │   │   ├── train/           ← training UI
    │   │   ├── augment/         ← augmentation settings (shared component)
    │   │   ├── merge/           ← merge datasets
    │   │   └── ui/              ← shared UI primitives (Button, Input, Modal…)
    │   └── lib/
    │       ├── api.ts           ← all API calls in one place
    │       └── types.ts         ← shared TypeScript types
    └── .env                     ← VITE_API_URL (blank = same origin)
```

---

## Customer requirements (README.md) — status

| Requirement | Done |
|---|---|
| Headless server, no GUI | ✅ |
| `-c` / `--config` CLI argument | ✅ |
| Config file with host + port | ✅ |
| HTTPS via cert files | ✅ (set ssl_certfile + ssl_keyfile in config) |
| All settings via HTTP API | ✅ |
| API token + user authentication | ✅ |
| Web configuration UI | ✅ |
| SSE stream per service (token auth) | ✅ |
| TCP/SSL push per service, N clients, keepalive | ✅ |
