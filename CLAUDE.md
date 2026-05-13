# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

VisionQ — a headless server that runs YOLO inference on camera streams, exposes REST + SSE + TCP push APIs, and serves a React web UI. The server runs on an Ubuntu machine (with GPU/camera); users access the web UI from their own PC over the local network.

---

## Commands

### Backend (server/)

```bash
# Install dependencies
cd server
pip install -r requirements.txt

# Run server (dev — auto-reload)
python main.py --reload

# Run with a specific config file
python main.py -c /path/to/config.json

# Run with host/port override
python main.py --host 0.0.0.0 --port 8000
```

The server serves the built frontend from `server/static/`. API docs are at `/docs`.

### Frontend (frontend/)

```bash
cd frontend
npm install

# Dev server (proxies /api to backend via VITE_API_URL)
npm run dev

# Type-check + production build (output → server/static/)
npm run build

# Lint
npm run lint
```

Set `VITE_API_URL` in `frontend/.env` to point the dev server at a running backend (e.g. `VITE_API_URL=http://localhost:8000`). Leave it blank when serving from the same origin (production).

### Docker (production)

```bash
# First-time setup (installs Docker, detects GPU, builds, starts)
bash setup.sh

# Normal operations
docker compose build && docker compose up -d
docker compose down
docker compose logs -f
```

GPU overlay: `docker-compose.gpu.yml` is activated automatically by `setup.sh` when an NVIDIA GPU is detected (sets `COMPOSE_FILE` in `.env`).

The persistent data volume maps to `./villapro-data` (or `$VISIONQ_DATA_DIR`) → `/villapro-data` inside the container. Set `VISIONQ_DATA=/villapro-data` in the environment so the server knows where to write configs, recordings, and the database.

---

## Architecture

### Data flow overview

```
Camera/video/HTTP source
  → DetectionService (background thread, YOLO inference)
      → _notify_internal(name, payload)
           ├─ SSE queues     → browser (EventSource)
           ├─ result buffer  → polling fallback (last 100 per service)
           ├─ TCP push       → external clients (gate controllers, BMS…)
           └─ counting hooks → CountingService (parking occupancy)
```

### Backend structure

`server/main.py` — entry point. Registers all routers, wires the asyncio event loop reference into the detection and counting routers (needed so background threads can push to SSE queues via `call_soon_threadsafe`), auto-starts services marked `auto_start=true`, and auto-starts TCP push servers.

`server/app/detection_service.py` — the core inference engine (~1700 lines). Contains:
- `ServiceConfig` dataclass + JSON persistence (`~/.config/visionq_services.json` or `$VISIONQ_DATA/config/`)
- `DetectionService` — manages one camera/video/HTTP source; runs YOLO in a background thread
- `ServiceRegistry` — singleton managing all `DetectionService` instances
- Direction algorithm: linear regression over a sliding window of (cx, cy, area) tuples → votes `forward`/`backward`/`idle`
- Gate trigger: emits `gate_open: true` when an idle car's bbox area ≥ `gate_area_threshold`

`server/app/counting_service.py` — parking occupancy counter. `CountingService` subscribes to a `DetectionService` via a callback hook registered in `routers/detection.py`. Counting rules: `car forward→no_car = +1`, `car_rear forward→no_car = −1`, any `backward→no_car = 0`. Config persisted to `$VISIONQ_DATA/config/visionq_counters.json`. Each detection service can have an associated counter named `{service_name}_counter`.

`server/app/tcp_push.py` — `TcpPushServer`: raw TCP (optionally TLS/mTLS), newline-delimited JSON, N simultaneous clients, 5s keepalive. A single `TcpPushRegistry` singleton manages all servers (shared by both detection and counting services).

`server/app/routers/detection.py` — manages the SSE queues (`_sse_queues`), result buffer (`_result_buffer`), MJPEG queues, and counting hooks (`_counting_hooks`). `_do_notify` runs on the asyncio event loop and fans a payload out to SSE subscribers, the TCP push registry, and all registered counting callbacks.

`server/app/routers/counting.py` — mirrors detection router for counting services: SSE, TCP, result buffer, REST CRUD.

`server/app/db.py` — SQLite via SQLAlchemy. Stores users, annotation projects, and image metadata. Config (service settings, tokens, app config) is JSON-file-based, not in the DB.

### Frontend structure

All API calls are in `frontend/src/lib/api.ts` — add new endpoints here.  
All TypeScript types are in `frontend/src/lib/types.ts`.

`components/detection/ServiceCard.tsx` — the main service management component. Contains:
- `useServiceResults` hook: subscribes to the detection SSE stream + polling fallback; tracks `totalReports`, `carCount`, `rearCount`
- Counter query: polls `/api/counting/services/{name}_counter/status` every 2s; shows type badge ("Detection" vs "Detection + Counter"), live occupancy `🅿 N`, and reset button
- Start/stop mutations chain detection + counter service together

`components/detection/ServiceForm.tsx` — create/edit modal for both service type and counter. Selecting "Detection + Counter" upserts a `{name}_counter` counting service; switching back to "Detection only" deletes it.

### SSE authentication pattern

Browsers can't set headers on `EventSource` connections, so the JWT is passed as a query parameter: `?token=<jwt>`. The SSE endpoints decode it manually before streaming. The `sseUrl()` helper in `api.ts` appends the token automatically.

### Adding a new service type

Follow the detection + counting pattern:
1. `server/app/<name>_service.py` — config dataclass, service class, registry singleton with `get_<name>_registry()`
2. `server/app/routers/<name>.py` — FastAPI router; include SSE queues, result buffer, `_notify_<name>_sse` + `_do_notify_<name>`, TCP push wiring
3. Register in `main.py`: import router, `set_event_loop`, `auto_start_services`, `stop_all` in lifespan
4. `frontend/src/lib/api.ts` — add API functions
5. `frontend/src/lib/types.ts` — add TypeScript interfaces

### Persistence paths

All paths resolve relative to `$VISIONQ_DATA` (defaults to `~` in dev, `/villapro-data` in Docker):

| What | Path |
|---|---|
| App config | `$VISIONQ_DATA/config/visionq.json` |
| Detection service configs | `$VISIONQ_DATA/config/visionq_services.json` |
| Counting service configs | `$VISIONQ_DATA/config/visionq_counters.json` |
| SQLite database | `$VISIONQ_DATA/visionq.db` |
| Recordings | configurable per service, default `~/VisionQ_recordings/` |
| Direction debug CSVs | `$VISIONQ_DATA/debug/<service_name>/` |
| Dataset frames | configurable per service |
| Trained models | `~/visionq-projects/models/<run_name>/weights/best.pt` |
