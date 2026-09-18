#!/usr/bin/env python3
"""Ask the context-store server for a project's context, grouped by topic.

Talks to the context store over HTTP (CONTEXT_STORE_URL env var, or --url) —
no local DuckDB file, embedding, or filtering code needed here, the server
does all of it. Falls back to all models for the domain if a --model filter
matches nothing, and flags that in the response (see project-context/SKILL.md
for how to handle that flag).

TODO(real-schema): domain/model_name are an assumed placeholder schema (see
db/schema.sql), owned entirely by the server now.
"""

import argparse
import json
import os
import urllib.request

DEFAULT_URL = os.environ.get("CONTEXT_STORE_URL", "http://localhost:8000")


def get_project_context(
    domain: str,
    model: str | None = None,
    tags: list[str] | None = None,
    query: str | None = None,
    url: str = DEFAULT_URL,
) -> dict:
    payload = json.dumps({"domain": domain, "model": model, "tags": tags, "query": query}).encode()
    req = urllib.request.Request(
        f"{url.rstrip('/')}/context",
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("domain", help="Project/domain to load context for")
    parser.add_argument("--model", default=None, help="Filter to a model_name; falls back to all models if none match")
    parser.add_argument("--tags", default=None, help="Comma-separated tags to filter by")
    parser.add_argument("--query", default=None, help="Optional free-text query to rank results by similarity")
    parser.add_argument("--url", default=DEFAULT_URL, help="context-store base URL (default: %(default)s)")
    args = parser.parse_args()

    tag_list = [t.strip() for t in args.tags.split(",")] if args.tags else None
    result = get_project_context(args.domain, args.model, tag_list, args.query, args.url)
    print(json.dumps(result, indent=2, default=str))
