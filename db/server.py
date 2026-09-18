#!/usr/bin/env python3
"""HTTP JSON API in front of the shared DuckDB context store.

This is what makes the store reachable as "some host:port on a server" —
skills never touch the DuckDB file or run inside this process; they just
send HTTP requests to CONTEXT_STORE_URL, wherever this happens to be
running (this docker-compose stack, or a real remote box).

Routes:
  GET  /health   -> {"status": "ok", "documents": <count>}
  POST /ingest   body: NDJSON text (one JSON record per line)
                 -> {"count": <ingested>}
  POST /query    body: {"text": ..., "top_k": 5}
                 -> [{"id", "text", "tags", "metadata", "score"}, ...]
  POST /context  body: {"domain": ..., "model": ..., "tags": [...], "query": ...}
                 -> {"domain", "requested_model", "used_model_fallback", "count", "topics", "documents"}
"""

import argparse
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from db.init_db import DEFAULT_DB_PATH, init_db
from db.store import get_project_context, ingest_lines, query_similar

_lock = threading.Lock()
_con = None


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, status: int, payload) -> None:
        body = json.dumps(payload, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length) if length else b""

    def do_GET(self):
        if self.path == "/health":
            with _lock:
                (count,) = _con.execute("SELECT count(*) FROM documents").fetchone()
            self._send_json(200, {"status": "ok", "documents": count})
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self):
        try:
            body = self._read_body()
            if self.path == "/ingest":
                lines = body.decode().splitlines()
                with _lock:
                    n = ingest_lines(_con, lines)
                self._send_json(200, {"count": n})
            elif self.path == "/query":
                req = json.loads(body or b"{}")
                with _lock:
                    results = query_similar(_con, req["text"], req.get("top_k", 5))
                self._send_json(200, results)
            elif self.path == "/context":
                req = json.loads(body or b"{}")
                with _lock:
                    result = get_project_context(
                        _con, req["domain"], req.get("model"), req.get("tags"), req.get("query")
                    )
                self._send_json(200, result)
            else:
                self._send_json(404, {"error": "not found"})
        except Exception as exc:  # surface all errors to the client rather than 500 blind
            self._send_json(400, {"error": str(exc)})

    def log_message(self, fmt, *args):
        print(f"{self.address_string()} - {fmt % args}")


def serve(db_path: Path = DEFAULT_DB_PATH, host: str = "0.0.0.0", port: int = 8000) -> None:
    global _con
    _con = init_db(db_path)
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"context-store API listening on http://{host}:{port} (db: {db_path})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        _con.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    serve(args.db, args.host, args.port)
