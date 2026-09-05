"""Server configuration — loaded from a JSON file at startup.

Usage:
    server.py --config ~/.config/visionq.json
    server.py -c /etc/visionq/config.json

The config file is also written back when settings change via the API.
"""
from __future__ import annotations

import json
import os
import secrets
from pathlib import Path
from typing import Optional

DEFAULT_CONFIG_PATH = Path(os.environ.get("VISIONQ_DATA", str(Path.home() / ".config"))) / "visionq.json"

_DEFAULT: dict = {
    "host": "0.0.0.0",
    "port": 8000,
    "ssl_certfile": "",
    "ssl_keyfile": "",
    "api_tokens": [],       # list of {"name": str, "token": str}
    "result_receiver_host": "127.0.0.1",
    "result_receiver_port": 6060,
}


class AppConfig:
    def __init__(self, path: Optional[str] = None):
        self.path = Path(path) if path else DEFAULT_CONFIG_PATH
        self._data: dict = dict(_DEFAULT)
        self._load()

    def _load(self):
        if self.path.exists():
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    on_disk = json.load(f)
                self._data.update(on_disk)
            except Exception as e:
                print(f"[config] Warning: could not load {self.path}: {e}")

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2)

    # ── Server settings ───────────────────────────────────────────────────────

    @property
    def host(self) -> str:
        return self._data.get("host", "0.0.0.0")

    @property
    def port(self) -> int:
        return int(self._data.get("port", 8000))

    @property
    def ssl_certfile(self) -> Optional[str]:
        v = self._data.get("ssl_certfile", "")
        return v if v else None

    @property
    def ssl_keyfile(self) -> Optional[str]:
        v = self._data.get("ssl_keyfile", "")
        return v if v else None

    @property
    def result_receiver_host(self) -> str:
        return self._data.get("result_receiver_host", "127.0.0.1")

    @property
    def result_receiver_port(self) -> int:
        return int(self._data.get("result_receiver_port", 6060))

    # ── API token management ──────────────────────────────────────────────────

    def get_tokens(self) -> list[dict]:
        return list(self._data.get("api_tokens", []))

    def validate_token(self, token: str) -> Optional[dict]:
        """Return the token record if valid, else None."""
        for t in self._data.get("api_tokens", []):
            if t["token"] == token:
                return t
        return None

    def create_token(self, label: str, services: list = None, permissions: list = None) -> str:
        from datetime import datetime, timezone
        token = secrets.token_hex(32)
        tokens = self._data.setdefault("api_tokens", [])
        tokens.append({
            "label": label,
            "token": token,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "services": services if services is not None else [],
            "permissions": permissions if permissions is not None else ["stream", "results"],
        })
        self.save()
        return token

    def revoke_token(self, token: str) -> bool:
        tokens = self._data.get("api_tokens", [])
        new_tokens = [t for t in tokens if t["token"] != token]
        if len(new_tokens) == len(tokens):
            return False
        self._data["api_tokens"] = new_tokens
        self.save()
        return True

    def to_dict(self) -> dict:
        return {
            "host": self.host,
            "port": self.port,
            "ssl_certfile": self._data.get("ssl_certfile", ""),
            "ssl_keyfile": self._data.get("ssl_keyfile", ""),
            "result_receiver_host": self.result_receiver_host,
            "result_receiver_port": self.result_receiver_port,
        }

    def update(self, data: dict):
        allowed = {"host", "port", "ssl_certfile", "ssl_keyfile",
                   "result_receiver_host", "result_receiver_port"}
        for k, v in data.items():
            if k in allowed:
                self._data[k] = v
        self.save()


# Module-level singleton — set by main.py at startup
_config: Optional[AppConfig] = None


def init_config(path: Optional[str] = None) -> AppConfig:
    global _config
    _config = AppConfig(path)
    return _config


def get_config() -> AppConfig:
    if _config is None:
        raise RuntimeError("Config not initialized. Call init_config() first.")
    return _config
