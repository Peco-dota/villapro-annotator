"""TCP/SSL push server for per-camera detection results.

Each detection service can optionally have a TCP server that pushes
JSON lines to all connected clients whenever a result is produced.

Protocol:
    - Server listens on a configured TCP port (optionally wrapped in TLS).
    - Clients connect and receive newline-delimited JSON messages.
    - Clients do not need to send anything (connection is read-only).
    - A keepalive {"type": "keepalive"} message is sent every 5 seconds
      to detect dead clients and keep NAT sessions alive.

Based on the pattern from https://github.com/cortexm/ser2tcp
"""
from __future__ import annotations

import json
import logging
import socket
import ssl
import threading
import time
from typing import Optional

log = logging.getLogger("tcp_push")

_KEEPALIVE_INTERVAL = 5.0  # seconds


class TcpPushServer:
    """A single TCP push server for one detection service."""

    def __init__(self, service_name: str, host: str, port: int,
                 certfile: Optional[str] = None, keyfile: Optional[str] = None,
                 ca_certs: Optional[str] = None):
        self.service_name = service_name
        self.host = host
        self.port = port
        self.certfile = certfile
        self.keyfile = keyfile
        self.ca_certs = ca_certs

        self._clients: list[socket.socket] = []
        self._clients_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._accept_thread: Optional[threading.Thread] = None
        self._keepalive_thread: Optional[threading.Thread] = None
        self._server_sock: Optional[socket.socket] = None

    def start(self) -> str:
        """Start listening. Returns error string or empty string on success."""
        try:
            raw_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            raw_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            raw_sock.bind((self.host, self.port))
            raw_sock.listen(16)
            raw_sock.settimeout(1.0)

            if self.certfile and self.keyfile:
                ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                ctx.load_cert_chain(self.certfile, self.keyfile)
                if self.ca_certs:
                    ctx.load_verify_locations(self.ca_certs)
                    ctx.verify_mode = ssl.CERT_REQUIRED
                self._server_sock = ctx.wrap_socket(raw_sock, server_side=True)
            else:
                self._server_sock = raw_sock

        except OSError as e:
            return f"Cannot bind TCP push server for '{self.service_name}' on {self.host}:{self.port} — {e}"

        self._stop_event.clear()

        self._accept_thread = threading.Thread(
            target=self._accept_loop,
            daemon=True,
            name=f"TcpAccept-{self.service_name}",
        )
        self._accept_thread.start()

        self._keepalive_thread = threading.Thread(
            target=self._keepalive_loop,
            daemon=True,
            name=f"TcpKeepalive-{self.service_name}",
        )
        self._keepalive_thread.start()

        tls = "TLS" if self.certfile else "TCP"
        log.info(f"[{self.service_name}] {tls} push server listening on {self.host}:{self.port}")
        return ""

    def stop(self):
        self._stop_event.set()
        if self._server_sock:
            try:
                self._server_sock.close()
            except Exception:
                pass
            self._server_sock = None

        with self._clients_lock:
            for c in self._clients:
                try:
                    c.close()
                except Exception:
                    pass
            self._clients.clear()

        if self._accept_thread and self._accept_thread.is_alive():
            self._accept_thread.join(timeout=2.0)
        if self._keepalive_thread and self._keepalive_thread.is_alive():
            self._keepalive_thread.join(timeout=2.0)

    def push(self, payload: dict):
        """Send a JSON line to all connected clients. Disconnected clients are removed."""
        line = (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")
        with self._clients_lock:
            alive = []
            for c in self._clients:
                try:
                    c.sendall(line)
                    alive.append(c)
                except OSError:
                    try:
                        c.close()
                    except Exception:
                        pass
            self._clients[:] = alive

    @property
    def client_count(self) -> int:
        with self._clients_lock:
            return len(self._clients)

    def _accept_loop(self):
        while not self._stop_event.is_set():
            try:
                conn, addr = self._server_sock.accept()
                conn.settimeout(None)
                with self._clients_lock:
                    self._clients.append(conn)
                log.info(f"[{self.service_name}] TCP client connected: {addr[0]}:{addr[1]} ({len(self._clients)} total)")
            except ssl.SSLError as e:
                if not self._stop_event.is_set():
                    log.warning(f"[{self.service_name}] SSL handshake failed: {e}")
            except OSError:
                break

    def _keepalive_loop(self):
        keepalive = {"type": "keepalive"}
        while not self._stop_event.is_set():
            self._stop_event.wait(timeout=_KEEPALIVE_INTERVAL)
            if self._stop_event.is_set():
                break
            with self._clients_lock:
                if self._clients:
                    self.push(keepalive)


class TcpPushRegistry:
    """Manages one TcpPushServer per detection service."""

    def __init__(self):
        self._servers: dict[str, TcpPushServer] = {}
        self._lock = threading.Lock()

    def start(self, service_name: str, host: str, port: int,
              certfile: Optional[str] = None, keyfile: Optional[str] = None,
              ca_certs: Optional[str] = None) -> str:
        with self._lock:
            existing = self._servers.get(service_name)
            if existing:
                existing.stop()
            srv = TcpPushServer(service_name, host, port, certfile, keyfile, ca_certs)
            err = srv.start()
            if not err:
                self._servers[service_name] = srv
            return err

    def stop(self, service_name: str):
        with self._lock:
            srv = self._servers.pop(service_name, None)
        if srv:
            srv.stop()

    def stop_all(self):
        with self._lock:
            servers = list(self._servers.values())
            self._servers.clear()
        for s in servers:
            s.stop()

    def push(self, service_name: str, payload: dict):
        with self._lock:
            srv = self._servers.get(service_name)
        if srv:
            srv.push(payload)

    def get_status(self) -> list[dict]:
        with self._lock:
            return [
                {"service": name, "port": srv.port, "clients": srv.client_count,
                 "tls": bool(srv.certfile)}
                for name, srv in self._servers.items()
            ]

    def is_running(self, service_name: str) -> bool:
        with self._lock:
            return service_name in self._servers


_tcp_registry = TcpPushRegistry()


def get_tcp_registry() -> TcpPushRegistry:
    return _tcp_registry
