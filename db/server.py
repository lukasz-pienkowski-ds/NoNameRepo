#!/usr/bin/env python3
"""Central DuckDB decision store, served over the quack client/server protocol.

Every developer machine talks to this process instead of opening the database
file directly. That is the whole point of it: a DuckDB file allows exactly one
writing process, so three laptops pointing at a shared file would deadlock or
corrupt it. Here a single process owns the file and every write is funnelled
through it, which serialises them by construction.

Consequence worth knowing: nothing else may open the database file while this
runs -- not even a read-only script on the same host. It will fail with
"Could not set lock on file". Anything that needs the data, the embedding
worker included, connects as a quack client (see client.py).
"""

import argparse
import os
import time
from pathlib import Path

import duckdb

DEFAULT_DB_PATH = Path(__file__).resolve().parents[1] / "data" / "db" / "decisions.duckdb"
SCHEMA_PATH = Path(__file__).resolve().parent / "decisions_schema.sql"
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8888
MIN_TOKEN_LENGTH = 4  # enforced by quack_serve itself


def open_db(db_path: Path) -> duckdb.DuckDBPyConnection:
    """Open (creating if needed) the central database and apply the schema."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))
    con.execute(SCHEMA_PATH.read_text())
    return con


def serve(
    db_path: Path = DEFAULT_DB_PATH,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    token: str | None = None,
) -> None:
    # quack enforces this itself, but only once it is already serving, and the
    # failure surfaces as a raw DuckDB exception. Checking here turns a
    # stack trace into a sentence -- including for an empty token, so there is
    # no unauthenticated mode to discover the hard way.
    if not token or len(token) < MIN_TOKEN_LENGTH:
        raise SystemExit(
            f"QUACK_TOKEN must be at least {MIN_TOKEN_LENGTH} characters "
            f"(got {len(token or '')}). Set it in .env or pass --token."
        )

    con = open_db(db_path)

    con.execute("INSTALL quack")
    con.execute("LOAD quack")

    # No vss here on purpose. array_cosine_similarity() is a core DuckDB
    # function -- verified working with no extension loaded -- so retrieval
    # needs nothing beyond what ships in the box. vss only buys an HNSW index,
    # which at this corpus size costs more to maintain than the full scan it
    # replaces, and on a persistent database needs an experimental flag that
    # comes with a data-loss warning.
    #
    # If it is ever needed: it must be loaded by *this* process at startup.
    # Pushing "LOAD vss" through a client query returns Success and changes
    # nothing -- CREATE INDEX ... USING HNSW still fails with
    # "Unknown index type".

    # The URI scheme is mandatory. A bare "host:port" is rejected with
    # "Invalid DuckDB Quack RPC URI, needs to start with 'quack:'".
    listen_uri = f"quack://{host}:{int(port)}"

    # quack_serve returns immediately; the listener lives on in this process,
    # so the loop below is what keeps it alive.
    # quack_serve refuses any hostname but localhost unless told otherwise --
    # it will not bind 0.0.0.0, which is exactly what a container needs. The
    # flag is the documented override; the token remains the only thing
    # standing between the store and whoever can reach the port, so on a real
    # network put a reverse proxy with TLS in front instead of exposing this.
    allow_other_hostname = host not in {"127.0.0.1", "localhost", "::1"}

    con.execute(
        "SELECT * FROM quack_serve(?, token := ?, "
        "allow_other_hostname := ?, disable_ssl := true)",
        [listen_uri, token, allow_other_hostname],
    ).fetchall()

    (rows,) = con.execute("SELECT count(*) FROM decisions").fetchone()
    print(f"Central decision store: {db_path} ({rows} decision(s))", flush=True)
    print(f"Listening on {listen_uri}", flush=True)

    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        con.execute("SELECT * FROM quack_stop(?)", [listen_uri]).fetchall()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="Path to the DuckDB file")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--token",
        default=os.environ.get("QUACK_TOKEN", ""),
        help="Shared auth token (env: QUACK_TOKEN)",
    )
    args = parser.parse_args()

    serve(args.db, args.host, args.port, args.token)
