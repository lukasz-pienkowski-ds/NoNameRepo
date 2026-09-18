---
name: tag-and-ingest
description: Tag and embed a JSONL file of documents, then upsert them into the DuckDB context store. Use when the user has new or updated JSONL context data that needs to be added to, or refreshed in, the knowledge base.
---

# Tag and Ingest

Adds documents from a JSONL file to the shared DuckDB context store at
`data/db/context.duckdb`, tagging and embedding each one along the way.

## When to use this skill

The user has a JSONL file (or asks you to add/refresh context data) that
should become part of the queryable context store used by the
`query-context` skill.

## Input format

Each line of the JSONL file is a JSON object:

```json
{"id": "optional-id", "text": "required document text", "source": "optional-label", "any": "other fields become metadata"}
```

`id` and `source` are optional — if omitted, an id is derived from the file
name and line number.

## How to run it

This project only runs via Docker — there is no local (non-Docker) path.

```bash
make ingest FILE=<path-to-file.jsonl>
# equivalent: docker compose run --rm context-store python .claude/skills/tag-and-ingest/scripts/ingest.py <path-to-file.jsonl>
```

This will:
1. Build the image and create `data/db/context.duckdb` (applying `db/schema.sql`) if it doesn't exist yet.
2. For each line: generate tags and an embedding, then `INSERT ... ON CONFLICT` (upsert by `id`) into the `documents` table.
3. Print how many documents were ingested.

## Browsing the store

Run `make ui` (or `docker compose up context-ui`) and open http://localhost:4213 for a SQL console over the `documents` table.

## Current status: mock

Tagging (`mock_tag`) and embeddings (`mock_embed`), defined in
`common/embeddings.py`, are placeholder implementations — keyword matching
and a hashed pseudo-vector, respectively. They exist to make the ingest →
store → query pipeline runnable end to end. When a real tagging/embedding
model is wired in, only `common/embeddings.py` needs to change; this script
and the schema stay the same.
