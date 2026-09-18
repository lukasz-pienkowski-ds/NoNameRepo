# hackaton_26

Template project: a DuckDB-backed context store built from JSONL data, run
in Docker, fed and queried via two Claude Code skills, browsable over a
network port via DuckDB's built-in web UI.

## Layout

```
Makefile                               make targets wrapping docker compose (build/init/ingest/query/ui)
pyproject.toml, uv.lock                Project deps, installed with uv inside the Docker image
db/schema.sql                          DuckDB table definition (documents, with a fixed-size embedding column)
db/init_db.py                          Creates/opens data/db/context.duckdb and applies the schema
db/serve_ui.py                         Serves DuckDB's web UI/SQL console on a port (default 4213)
common/embeddings.py                   Mock tagging + embedding functions (swap these for real models later)
data/raw/sample.jsonl                  Example input data
data/db/context.duckdb                 Generated DuckDB file (gitignored)
docker/Dockerfile, docker-compose.yml  Container(s) to run the scripts/UI server below without a local Python env
.claude/skills/tag-and-ingest/         Skill: tag + embed a JSONL file, upsert into DuckDB
.claude/skills/query-context/          Skill: retrieve top-k similar documents for a query
```

## Status

This is a mock/scaffold: tagging and embeddings in `common/embeddings.py`
are deterministic placeholders (keyword matching + a hashed pseudo-vector),
not a real model. They make the ingest → store → query pipeline runnable
end to end; swap that one file for a real embedding/tagging model later
without touching the schema, scripts, or skills.

## Quickstart (Docker, via Makefile)

```bash
make init                                    # create data/db/context.duckdb
make ingest                                  # tag+embed data/raw/sample.jsonl into it
make ingest FILE=data/raw/other.jsonl        # or ingest your own JSONL file
make query Q="how does docker compose work"  # top-5 similar docs, as JSON
make ui                                      # web SQL console at http://localhost:4213
```

`make help` lists all targets. Everything runs inside the `docker/Dockerfile`
image (Python + uv-installed deps); nothing needs to be installed on the
host besides Docker.

The equivalent raw `docker compose` commands, if you'd rather skip make:

```bash
docker compose build
docker compose run --rm context-store python db/init_db.py
docker compose run --rm context-store python .claude/skills/tag-and-ingest/scripts/ingest.py data/raw/sample.jsonl
docker compose run --rm context-store python .claude/skills/query-context/scripts/query.py "how does docker compose work"
docker compose up context-ui   # web UI on http://localhost:4213 (runs until stopped)
```

`context-ui` uses `network_mode: host` (Linux only) because DuckDB's `ui`
extension only binds to 127.0.0.1 inside its own process — a normal
`ports:` mapping wouldn't be reachable from the host.

## Skills

- **tag-and-ingest**: point it at a JSONL file of `{"text": ...}` records; it tags and embeds each one and upserts it into `documents`.
- **query-context**: give it a query string; it embeds the query and returns the top-k most similar documents by cosine similarity, for use as grounding context.
