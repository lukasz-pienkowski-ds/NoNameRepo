# hackaton_26

Template project: a DuckDB-backed context store served over HTTP by a small
API (`db/server.py`), fed and queried by Claude Code skills that are plain
network clients — the store can be this repo's docker-compose stack, or a
real server somewhere else (`ip:port`); the skills don't care which.

## Layout

```
Makefile                               make targets: build/up/down the server, ingest/query/context/guard clients, ui
pyproject.toml, uv.lock                Server-side deps (duckdb), installed with uv inside the Docker image
db/schema.sql                          DuckDB table definition (documents, incl. an ASSUMED domain/model_name pair)
db/init_db.py                          Creates/opens data/db/context.duckdb and applies the schema
db/store.py                            Server-side ingest/query/context logic (plain functions over a DuckDB connection)
db/server.py                           HTTP JSON API in front of the store (/health, /ingest, /query, /context)
db/serve_ui.py                         Serves DuckDB's web UI/SQL console on a port (default 4213), read-only
common/embeddings.py                   Mock tagging + embedding functions (swap these for real models later), server-side only
data/raw/sample.jsonl                  Example input data (generic topics)
data/raw/sample_sessions.jsonl         Example input data shaped like tagged Claude Code sessions (domain/model)
data/db/context.duckdb                 Generated DuckDB file (gitignored), owned by the server process
docker/Dockerfile, docker-compose.yml  Runs db/server.py (and db/serve_ui.py) without a local Python env
.claude/skills/tag-and-ingest/         Skill: POST a JSONL file to the server to be tagged, embedded, and upserted
.claude/skills/query-context/          Skill: POST a query, get back top-k similar documents
.claude/skills/project-context/        Skill: POST a domain, get back its grouped context + how to apply it
.claude/skills/session-guard/          Skill: check a dev's session transcript against retrieved precedent, flag conflicts
```

## Status

This is a mock/scaffold: tagging and embeddings in `common/embeddings.py`
are deterministic placeholders (keyword matching + a hashed pseudo-vector),
not a real model. They make the ingest → store → query pipeline runnable
end to end; swap that one file for a real embedding/tagging model later
without touching the schema, the server, or the skills.

The `domain` and `model_name` columns on `documents` (see `db/schema.sql`)
are an **assumed placeholder schema**, guessed at ahead of the real
ingestion schema that will populate this table from tagged/embedded Claude
Code session JSONL. When that schema is delivered, `db/schema.sql` and
`db/store.py` are the only files that reference those column names —
nothing else depends on their shape.

## Architecture: client/server, not docker-exec

The store is **not** something skills reach by running inside a container.
`db/server.py` is a long-running HTTP JSON API that owns the DuckDB file,
the schema, and the tagging/embedding logic. Skills
(`.claude/skills/*/scripts/*.py`) are plain-stdlib HTTP clients — no
`duckdb` import, no filesystem access to the `.duckdb` file, no Docker
requirement of their own. They just POST to `CONTEXT_STORE_URL`, wherever
that happens to point:

- pointed at `http://localhost:8000`, that's this repo's own docker-compose `context-store` service
- pointed at `http://some-host:8000`, that's a `db/server.py` running on any other machine — same skill code, no changes needed

Only the **server** needs Docker (or a Python host with `duckdb` installed);
the skills that consume it need nothing but the standard library and
network access.

## Quickstart (via Makefile)

```bash
make up                                      # build + start context-store at http://localhost:8000
make ingest                                  # tag+embed data/raw/sample.jsonl, POST it to the server
make ingest FILE=data/raw/sample_sessions.jsonl  # or ingest the mock session data
make query Q="how does docker compose work"  # top-5 similar docs, as JSON
make context DOMAIN=hackaton_26              # this project's context, grouped by topic
make context DOMAIN=billing-service MODEL=claude-sonnet-5
make guard SESSION=<path-to-transcript.jsonl>  # check a dev session's moves against precedent
make ui                                      # web SQL console at http://localhost:4213 (read-only)
make down                                    # stop the server
```

`make help` lists all targets. `CONTEXT_STORE_URL` (default
`http://localhost:8000`) controls where `ingest`/`query`/`context`/`guard`
connect — override it to point at a remote server instead:
`make query Q="..." CONTEXT_STORE_URL=http://1.2.3.4:8000`.

The equivalent raw commands, if you'd rather skip make:

```bash
docker compose up -d --build context-store   # starts the API on http://localhost:8000
python3 .claude/skills/tag-and-ingest/scripts/ingest.py data/raw/sample_sessions.jsonl --url http://localhost:8000
python3 .claude/skills/query-context/scripts/query.py "how does docker compose work" --url http://localhost:8000
python3 .claude/skills/project-context/scripts/project_context.py hackaton_26 --url http://localhost:8000
python3 .claude/skills/session-guard/scripts/session_guard.py <transcript.jsonl> --url http://localhost:8000
docker compose up context-ui                 # web UI on http://localhost:4213 (runs until stopped)
```

`context-ui` uses `network_mode: host` (Linux only) because DuckDB's `ui`
extension only binds to 127.0.0.1 inside its own process — a normal
`ports:` mapping wouldn't be reachable from the host.

## Skills

- **tag-and-ingest**: point it at a local JSONL file of `{"text": ...}` records (optionally with `domain`/`model`); it POSTs the file to the server, which tags and embeds each line and upserts it into `documents`.
- **query-context**: give it a query string; the server embeds it and returns the top-k most similar documents by cosine similarity, for use as grounding context. Generic, whole-store search.
- **project-context**: give it a domain (and optionally a model/tags/query); it returns that project's context grouped by topic, and tells the agent how to apply it: follow existing conventions as precedent, resolve conflicts by recency, cite doc ids, and say plainly when a domain has no context yet instead of inventing conventions.
- **session-guard**: point it at a developer's Claude Code session transcript; it infers the domain from the session's working directory, builds a retrieval query from recent messages/tool-calls, and fetches the matching precedent. Its job isn't just to answer — it checks the developer's recent moves against that precedent and reports compliance/violations with concrete, cited fixes, repeatedly over the course of a session rather than once.
