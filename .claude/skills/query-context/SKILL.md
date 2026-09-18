---
name: query-context
description: Retrieve the most relevant documents from the DuckDB context store for a given query, for use as grounding context in an answer. Use when the user asks a question that the ingested JSONL context data might answer.
---

# Query Context

Looks up the top-k most similar documents to a query from the shared DuckDB
context store at `data/db/context.duckdb`, built by the `tag-and-ingest`
skill.

## When to use this skill

Before answering a question that the project's ingested context data (see
`data/raw/*.jsonl`) might help with, retrieve relevant documents with this
skill and ground your answer in them.

## How to run it

This project only runs via Docker — there is no local (non-Docker) path.

```bash
make query Q="<query text>" TOPK=5
# equivalent: docker compose run --rm context-store python .claude/skills/query-context/scripts/query.py "<query text>" --top-k 5
```

Prints a JSON array of `{id, text, tags, metadata, score}`, ranked by cosine
similarity (highest first).

## Current status: mock

The similarity ranking uses `mock_embed` from `common/embeddings.py`, a
deterministic hashed pseudo-embedding — it is NOT semantically meaningful
yet, so results should be treated as a pipeline smoke test rather than
real relevance ranking. Once `common/embeddings.py` is upgraded to a real
embedding model (used consistently by both this skill and `tag-and-ingest`),
retrieval quality will reflect actual semantic similarity with no other
changes needed here.
