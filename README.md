# NoNameRepo — central decision store

Decisions taken while working with an agent, harvested from session logs and
shared across the team. One DuckDB process owns the database and serves it to
every machine over the `quack` protocol.

Built for the "DuckLake & Grill-Me" hackathon: senior developers' decisions are
collected automatically from their agent sessions, and a junior's agent later
uses them to ask the right question rather than hand over the answer.

## Layout

```
common/sessions.py         Reads agent sessions from any CLI (claude/gemini/codex)
common/marker.py           The <decision_log> contract and its parser
common/tags.py             Frozen tag vocabulary, shared with the skill
common/embeddings.py       mock_embed — the designated swap point for a real model

db/decisions_schema.sql    The `decisions` table
db/server.py               The store itself, served over quack
db/client.py               How every machine talks to it
db/worker_embeddings.py    Fills in missing embeddings, asynchronously
db/extract.py              Scan agent sessions -> decisions -> store
db/cli.py                  status / load / find / confirm

test_smoke.py              30 offline checks (`make test`)
test_integration.py        23 checks against a running store (`make test-integration`)
data/seed/decisions.jsonl  Demo decisions
docs/                      CENTRAL-STORE.md, HANDOVER.md, SCENARIUSZ.md
```

## Quickstart

```bash
cp .env.example .env     # set QUACK_TOKEN (4 characters minimum)
make up                  # store + embedding worker
make seed                # load demo decisions
make find TAGS=persystencja
make detect              # which LLM CLIs have sessions on this machine
make extract             # harvest decisions from them
make test-all            # 30 offline + 23 integration checks
```

Then search by describing a situation in your own words:

```bash
.venv/bin/python db/cli.py find --query "dostawca ponawia webhooki i dostajemy podwojne obciazenia"
```

Ranking is BM25 over DuckDB's own full-text index — shared words, not meaning.
`DEMO.md` walks through the whole scenario.

`make help` lists the rest. Everything runs in the `docker/Dockerfile` image;
nothing is needed on the host besides Docker.

## Why a server and not a shared file

A DuckDB file allows exactly one writing process, so three laptops pointing at a
shared file deadlock or corrupt it. Here a single process owns the file and
every write is funnelled through it, which serialises them by construction.

The consequence is a rule: **nothing else may open
`data/db/decisions.duckdb` while the store runs** — not even a read-only script
on the same host. It fails with `Could not set lock on file`. Everything
connects as a client.

## Status

The store, the session readers and the extractor are done and tested. The skill
that emits `<decision_log>` markers, and the grill/precedent modes that read
them back, are designed but not written — see `docs/SCENARIUSZ.md` for exactly
which steps are covered and which are not.

`docs/CENTRAL-STORE.md` is the technical reference. `docs/HANDOVER.md` (PL)
explains the reasoning and the traps. `docs/SCENARIUSZ.md` (PL) maps the
scenario onto test coverage.
