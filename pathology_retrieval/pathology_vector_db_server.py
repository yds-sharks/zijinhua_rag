#!/usr/bin/env python3
"""Resident HTTP service for the pathology hybrid vector database.

Start once, then call `call_pathology_vector_db.py` repeatedly. The process keeps
the BGE model and Milvus connection loaded, avoiding the slow per-query startup.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict

from call_pathology_vector_db import DEFAULT_CONFIG, HybridRetriever, load_config


class RetrievalState:
    def __init__(self, config_path: Path, topk: int | None):
        self.config_path = config_path
        self.cfg = load_config(config_path, topk=topk)
        self.lock = threading.Lock()
        with contextlib.redirect_stdout(sys.stderr):
            self.retriever = HybridRetriever(self.cfg)

    def health(self) -> Dict[str, Any]:
        col = self.retriever.collection
        return {
            "status": "ok",
            "config": str(self.config_path),
            "milvus_uri": self.cfg["milvus"]["uri"],
            "collection": self.cfg["milvus"]["collection"],
            "topk": self.retriever.topk,
            "num_entities": col.num_entities,
        }

    def search(self, query: str, topk: int | None = None) -> Dict[str, Any]:
        with self.lock:
            old_topk = self.retriever.topk
            if topk is not None:
                self.retriever.topk = int(topk)
            try:
                with contextlib.redirect_stdout(sys.stderr):
                    return self.retriever.search(query)
            finally:
                self.retriever.topk = old_topk


def make_handler(state: RetrievalState):
    class Handler(BaseHTTPRequestHandler):
        server_version = "PathologyVectorDB/1.0"

        def _send_json(self, status: HTTPStatus, payload: Dict[str, Any]) -> None:
            data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:
            if self.path.rstrip("/") == "/health":
                self._send_json(HTTPStatus.OK, state.health())
                return
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})

        def do_POST(self) -> None:
            if self.path.rstrip("/") != "/search":
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
                return

            try:
                length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(length).decode("utf-8")
                payload = json.loads(body) if body else {}
                query = str(payload.get("query") or "").strip()
                topk = payload.get("topk")
                if not query:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": "query is required"})
                    return
                result = state.search(query, topk=topk)
                self._send_json(HTTPStatus.OK, result)
            except Exception as exc:
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": repr(exc)})

        def log_message(self, fmt: str, *args: Any) -> None:
            print(f"[http] {self.address_string()} - {fmt % args}", file=sys.stderr)

    return Handler


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run resident pathology vector DB retrieval service")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--topk", type=int, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print(f"[startup] loading retriever from {args.config}", file=sys.stderr)
    state = RetrievalState(args.config, args.topk)
    httpd = ThreadingHTTPServer((args.host, args.port), make_handler(state))
    print(f"[startup] ready on http://{args.host}:{args.port}", file=sys.stderr)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
