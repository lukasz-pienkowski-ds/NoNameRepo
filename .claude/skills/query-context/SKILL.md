---
name: query-context
description: Retrieve the most relevant documents from the DuckDB context store for a given query, for use as grounding context in an answer. Use when the user asks a question that the ingested JSONL context data might answer.
---

# Query Context

Asks the context-store server for the top-k most similar documents to a
query, from the shared store built by the `tag-and-ingest` skill. This skill
never touches the DuckDB file itself — it's a plain HTTP client to the
server, which can be local docker-compose or a remote host.

## When to use this skill

Before answering a question that the project's ingested context data (see
`data/raw/*.jsonl`) might help with, retrieve relevant documents with this
skill and ground your answer in them.

## How to run it

The context-store server must be running first (`make up` starts it at
`http://localhost:8000` — see the project README). This skill's script is a
plain HTTP client; it needs no Docker access of its own, only network
access to the server.

```bash
make query Q="<query text>" TOPK=5
# equivalent: python3 .claude/skills/query-context/scripts/query.py "<query text>" --top-k 5 --url $CONTEXT_STORE_URL
```

Set `CONTEXT_STORE_URL` (default `http://localhost:8000`) to point at a
different server — e.g. `make query Q="..." CONTEXT_STORE_URL=http://1.2.3.4:8000`.

Prints a JSON array of `{id, text, tags, metadata, score}`, ranked by cosine
similarity (highest first).

## Current status: mock

The similarity ranking uses `mock_embed` from `common/embeddings.py`,
run server-side, a deterministic hashed pseudo-embedding — it is NOT
semantically meaningful yet, so results should be treated as a pipeline
smoke test rather than real relevance ranking. Once `common/embeddings.py`
is upgraded to a real embedding model on the server, retrieval quality will
reflect actual semantic similarity with no changes needed to this skill.
