"""VisionQ headless server — entry point.

Usage:
    python main.py
    python main.py --config ~/.config/visionq.json
    python main.py -c /etc/visionq/config.json --host 0.0.0.0 --port 8000

The server runs until SIGTERM / Ctrl-C.
"""
from __future__ import annotations

import argparse
import logging
import mimetypes
import signal
import sys
import os

# Windows registry often maps .js/.mjs to text/plain — override explicitly
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("application/javascript", ".mjs")
mimetypes.add_type("text/css", ".css")

# Ensure `app` package is importable from this directory
sys.path.insert(0, os.path.dirname(__file__))

import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import init_config
from app.version import VERSION
from app.routers import system, projects, annotations, detection, datasets, fs, auth
from app.db import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("visionq")


def create_app(config_path: str | None = None) -> FastAPI:
    cfg = init_config(config_path)
    init_db()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        log.info(f"VisionQ Server v{VERSION} starting up")
        log.info(f"Config file: {cfg.path}")
        from app.detection_service import get_registry

        def _on_auto_done(name: str, error: str):
            if error:
                log.error(f"[auto-start] {name}: {error}")
            else:
                log.info(f"[auto-start] {name}: running")

        get_registry().auto_start_services(_on_auto_done)
        yield
        log.info("VisionQ Server shutting down…")
        from app.tcp_push import get_tcp_registry
        get_registry().stop_all()
        get_tcp_registry().stop_all()
        log.info("All services stopped.")

    app = FastAPI(
        title="VisionQ Server",
        version=VERSION,
        description="Headless YOLO annotation & detection server",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # Allow all origins — lock this down in production via config
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth.router)
    app.include_router(system.router)
    app.include_router(projects.router)
    app.include_router(annotations.router)
    app.include_router(detection.router)
    app.include_router(datasets.router)
    app.include_router(fs.router)

    # Serve built React frontend if the dist folder exists (production / Docker)
    _dist = os.path.join(os.path.dirname(__file__), "static")
    if os.path.isdir(_dist):
        app.mount("/assets", StaticFiles(directory=os.path.join(_dist, "assets")), name="assets")

        @app.get("/")
        def spa_root():
            return FileResponse(os.path.join(_dist, "index.html"))

        @app.get("/{full_path:path}")
        def spa_fallback(full_path: str):
            # API routes are handled by the routers above — only serve index.html for frontend routes
            if full_path.startswith("api/") or full_path.startswith("docs") or full_path.startswith("redoc"):
                from fastapi import HTTPException
                raise HTTPException(status_code=404)
            return FileResponse(os.path.join(_dist, "index.html"))
    else:
        @app.get("/")
        def root():
            return {
                "name": "VisionQ Server",
                "version": VERSION,
                "docs": "/docs",
            }

    return app


# Module-level app for uvicorn --reload (e.g. `uvicorn main:app --reload`)
app = create_app()


def main():
    parser = argparse.ArgumentParser(description="VisionQ headless server")
    parser.add_argument(
        "-c", "--config",
        default=None,
        help="Path to JSON config file (default: ~/.config/visionq.json)",
    )
    parser.add_argument("--host", default=None, help="Override listen host")
    parser.add_argument("--port", type=int, default=None, help="Override listen port")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload (dev mode)")
    args = parser.parse_args()

    # Build app (also initializes config)
    app = create_app(args.config)

    from app.config import get_config
    cfg = get_config()

    host = args.host or cfg.host
    port = args.port or cfg.port

    ssl_kwargs = {}
    if cfg.ssl_certfile and cfg.ssl_keyfile:
        ssl_kwargs["ssl_certfile"] = cfg.ssl_certfile
        ssl_kwargs["ssl_keyfile"] = cfg.ssl_keyfile
        log.info(f"TLS enabled: {cfg.ssl_certfile}")

    log.info(f"Listening on {host}:{port}")
    log.info("API docs: http(s)://{host}:{port}/docs")

    uvicorn.run(
        app,
        host=host,
        port=port,
        reload=args.reload,
        log_level="warning",
        **ssl_kwargs,
    )


if __name__ == "__main__":
    main()
