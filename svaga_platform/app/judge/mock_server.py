"""Programmable mock HTTP service for connector tasks.

Runs inside the hidden-check pytest process. The candidate app calls it over real HTTP; checks program its replies
and inspect the calls it received (method, path, query, JSON body, headers).
"""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlsplit

MOCK_HOST = "127.0.0.1"
MOCK_PORT = 18765
MOCK_BASE_URL = f"http://{MOCK_HOST}:{MOCK_PORT}"


@dataclass
class MockCall:
    method: str
    path: str
    query: dict[str, str]
    json: Any
    headers: dict[str, str]


@dataclass
class MockService:
    calls: list[MockCall] = field(default_factory=list)
    replies: dict[tuple[str, str], tuple[int, Any]] = field(default_factory=dict)
    sequences: dict[tuple[str, str], list[tuple[int, Any]]] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def respond(self, method: str, path: str, *, status: int = 200, json_body: Any = None) -> None:
        with self.lock:
            self.replies[(method.upper(), path)] = (status, json_body)

    def respond_sequence(self, method: str, path: str, replies: list[tuple[int, Any]]) -> None:
        """Reply with each (status, json) in turn; the last one repeats (e.g. fail, fail, then succeed)."""
        with self.lock:
            self.sequences[(method.upper(), path)] = list(replies)

    def reset(self) -> None:
        with self.lock:
            self.calls.clear()
            self.replies.clear()
            self.sequences.clear()

    def calls_to(self, path: str) -> list[MockCall]:
        return [c for c in self.calls if c.path == path]


def _handler_for(service: MockService):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: Any) -> None:  # keep test output clean
            return

        def _handle(self) -> None:
            parts = urlsplit(self.path)
            length = int(self.headers.get("content-length") or 0)
            raw = self.rfile.read(length) if length else b""
            try:
                body = json.loads(raw) if raw else None
            except ValueError:
                body = raw.decode("utf-8", "replace")
            call = MockCall(
                method=self.command.upper(),
                path=parts.path,
                query={k: v[0] for k, v in parse_qs(parts.query).items()},
                json=body,
                headers={k.lower(): v for k, v in self.headers.items()},
            )
            with service.lock:
                service.calls.append(call)
                key = (call.method, call.path)
                sequence = service.sequences.get(key)
                if sequence:
                    status, reply = sequence.pop(0) if len(sequence) > 1 else sequence[0]
                else:
                    status, reply = service.replies.get(key, (404, {"detail": "no mock reply programmed"}))
            payload = json.dumps(reply).encode("utf-8") if not isinstance(reply, (bytes, str)) else (
                reply.encode("utf-8") if isinstance(reply, str) else reply)
            self.send_response(status)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = _handle

    return Handler


def start_mock_server(port: int = MOCK_PORT) -> tuple[MockService, ThreadingHTTPServer]:
    service = MockService()
    server = ThreadingHTTPServer((MOCK_HOST, port), _handler_for(service))
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return service, server
