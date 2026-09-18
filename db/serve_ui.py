#!/usr/bin/env python3
"""Serve DuckDB's built-in web UI/SQL console against the shared context store.

Uses DuckDB's `ui` extension (bundled with DuckDB >= 1.1; auto-installs on
first run, which needs network access once). Exposes a browser-based SQL
console at http://localhost:<port>/ (default 4213) so the DuckDB file can be
browsed by a human, separately from the db/server.py API skills use.

Opens the file read-only: db/server.py holds the read-write connection while
it's running (DuckDB allows only one writer), and this is a browsing tool,
not a way to mutate the store — so it also requires the file to already
exist (start the context-store server first).
"""

import argparse
import time
from pathlib import Path

import duckdb

from init_db import DEFAULT_DB_PATH

DEFAULT_PORT = 4213


def serve(db_path: Path = DEFAULT_DB_PATH, port: int = DEFAULT_PORT) -> None:
    if not db_path.exists():
        raise SystemExit(f"{db_path} does not exist yet — start the context-store server first (make up).")
    con = duckdb.connect(str(db_path), read_only=True)
    con.execute("INSTALL ui")
    con.execute("LOAD ui")
    con.execute(f"SET ui_local_port = {int(port)}")
    con.execute("CALL start_ui_server()")
    (url,) = con.execute("SELECT * FROM get_ui_url()").fetchone()
    print(f"DuckDB UI serving {db_path} at {url} (listening on 0.0.0.0:{port})")

    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        con.execute("CALL stop_ui_server()")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="Path to the DuckDB file")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()

    serve(args.db, args.port)
