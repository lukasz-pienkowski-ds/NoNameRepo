#!/usr/bin/env python3
"""Ask the context-store server for the top-k most similar documents.

Talks to the context store over HTTP (CONTEXT_STORE_URL env var, or --url) —
no local DuckDB file or embedding code needed here, the server does both.
"""

import argparse
import json
import os
import urllib.request

DEFAULT_URL = os.environ.get("CONTEXT_STORE_URL", "http://localhost:8000")


def query(text: str, top_k: int = 5, url: str = DEFAULT_URL) -> list[dict]:
    payload = json.dumps({"text": text, "top_k": top_k}).encode()
    req = urllib.request.Request(
        f"{url.rstrip('/')}/query",
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query_text", help="Text to find similar context documents for")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--url", default=DEFAULT_URL, help="context-store base URL (default: %(default)s)")
    args = parser.parse_args()

    results = query(args.query_text, args.top_k, args.url)
    print(json.dumps(results, indent=2, default=str))
