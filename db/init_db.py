#!/usr/bin/env python3
"""Create (or reconnect to) the DuckDB context store and apply schema.sql."""

import argparse
from pathlib import Path

import duckdb

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "db" / "context.duckdb"
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def init_db(db_path: Path = DEFAULT_DB_PATH) -> duckdb.DuckDBPyConnection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))
    con.execute(SCHEMA_PATH.read_text())
    return con


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="Path to the DuckDB file")
    args = parser.parse_args()

    connection = init_db(args.db)
    (count,) = connection.execute("SELECT count(*) FROM documents").fetchone()
    print(f"DuckDB ready at {args.db} ({count} document(s))")
