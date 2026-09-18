#!/usr/bin/env python3
"""Send a JSONL file to the context-store server to be tagged, embedded, and upserted.

Talks to the context store over HTTP (CONTEXT_STORE_URL env var, or --url) —
the server owns the DuckDB file, schema, and tagging/embedding logic. This
script has no project dependencies of its own: it just reads a local file
and POSTs it, so it runs anywhere the server is reachable, not just inside
its container.

Each line of the JSONL file is a JSON object:
    {"id": "optional-id", "text": "required", "source": "optional",
     "domain": "optional", "model": "optional", "any": "other -> metadata"}
"""

import argparse
import json
import os
import urllib.request
from pathlib import Path

DEFAULT_URL = os.environ.get("CONTEXT_STORE_URL", "http://localhost:8000")


def ingest_file(jsonl_path: Path, url: str = DEFAULT_URL) -> int:
    req = urllib.request.Request(
        f"{url.rstrip('/')}/ingest",
        data=jsonl_path.read_bytes(),
        method="POST",
        headers={"Content-Type": "application/x-ndjson"},
    )
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read())
    return result["count"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("jsonl_path", type=Path, help="Path to the input JSONL file")
    parser.add_argument("--url", default=DEFAULT_URL, help="context-store base URL (default: %(default)s)")
    args = parser.parse_args()

    n = ingest_file(args.jsonl_path, args.url)
    print(f"Tagged and ingested {n} document(s) from {args.jsonl_path} into {args.url}")
