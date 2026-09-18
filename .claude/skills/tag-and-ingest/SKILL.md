---
name: tag-and-ingest
description: Tag and embed a JSONL file of documents, then upsert them into the DuckDB context store. Use when the user has new or updated JSONL context data that needs to be added to, or refreshed in, the knowledge base.
---

# Tag and Ingest

Sends documents from a local JSONL file to the context-store server, which
tags and embeds each one and upserts it into the shared `documents` table.
The server owns the DuckDB file — this skill never touches it directly, only
talks to the server over HTTP, so it works the same way whether that server
is local docker-compose or a remote host.

## When to use this skill

The user has a JSONL file (or asks you to add/refresh context data) that
should become part of the queryable context store used by the
`query-context` skill.

## Input format

Each line of the JSONL file is a JSON object:

```json
{"id": "optional-id", "text": "required document text", "source": "optional-label", "domain": "optional-project-name", "model": "optional-model-name", "any": "other fields become metadata"}
```

`id` and `source` are optional — if omitted, an id is derived from the file
name and line number. `domain`/`model` are also optional; set them when the
data represents a specific project/model so `project-context` can filter by
them later.

## How to run it

The context-store server must be running first (`make up` starts it at
`http://localhost:8000` — see the project README). This skill's script is a
plain HTTP client; it needs no Docker access of its own, only network
access to the server.

```bash
make ingest FILE=<path-to-file.jsonl>
# equivalent: python3 .claude/skills/tag-and-ingest/scripts/ingest.py <path-to-file.jsonl> --url $CONTEXT_STORE_URL
```

Set `CONTEXT_STORE_URL` (default `http://localhost:8000`) to point at a
different server — e.g. `make ingest FILE=... CONTEXT_STORE_URL=http://1.2.3.4:8000`.

This will:
1. POST the JSONL file's contents to the server's `/ingest` endpoint.
2. The server generates tags and an embedding per line, then upserts (by `id`) into the `documents` table.
3. Print how many documents were ingested.

## Browsing the store

Run `make ui` (or `docker compose up context-ui`) and open http://localhost:4213 for a read-only SQL console over the `documents` table.

## Current status: mock

Tagging (`mock_tag`) and embeddings (`mock_embed`), defined in
`common/embeddings.py` and run server-side, are placeholder implementations
— keyword matching and a hashed pseudo-vector, respectively. They exist to
make the ingest → store → query pipeline runnable end to end. When a real
tagging/embedding model is wired in, only `common/embeddings.py` needs to
change; this skill's client script, the server's HTTP contract, and the
schema all stay the same.
