# Central decision store

The central half of the system: one DuckDB process that owns the decision
database and serves it to every developer machine over the `quack`
client/server protocol.

## Why a server and not a shared file

A DuckDB file allows exactly one writing process. The rest of this repo opens
`data/db/context.duckdb` directly, which is fine for one laptop and breaks the
moment three people write at once. Here a single process holds the file and
every write is funnelled through it, so writes are serialised by construction —
verified with three clients inserting concurrently.

The consequence is a rule, not a preference: **nothing else may open the
database file while the server runs**, not even a read-only script on the same
host. It fails with `Could not set lock on file`. Everything — the skill, the
embedding worker, the CLI — connects as a client.

## Works with any LLM CLI

Sessions are read through `sessions.py`, which normalises each tool's layout
into one stream of messages. The extractor never learns which CLI produced a
session; adding a fourth is one adapter, not a redesign.

| CLI | Location | Adapter |
|---|---|---|
| claude | `~/.claude/projects/**`, plus `$CLAUDE_CONFIG_DIR` and `~/.claude-*` | verified against real sessions |
| gemini | `~/.gemini/tmp/<project>/chats/**` | verified against real sessions |
| codex | `~/.codex/sessions/**` | **unverified** — written from the documented shape, no install available |

`python db/extract.py --detect` reports what is actually on the machine.

The differences are not cosmetic. Claude stores a `uuid` and `sessionId` on
every record; gemini keeps the session id on a header record only, and repeats
messages inside `$set` snapshots. Both use two different shapes for message
content, and disagree about which role uses which. Record ids are unique only
within one tool, so keys are namespaced: `claude:<uuid>`, `gemini:<id>`.

## Layout

The store is distributed across the repo's existing directories rather than
living in a folder of its own: `common/` for shared, importable pieces, `db/`
for the store and its access layer.

```
common/sessions.py       finds and normalises sessions from any supported CLI
common/marker.py         the <decision_log> contract and its parser
common/tags.py           the frozen tag vocabulary, shared with the skill

db/decisions_schema.sql  the `decisions` table
db/server.py             opens the database, loads quack, serves, validates the token
db/client.py             how everything else talks to the store
db/worker_embeddings.py  fills in NULL embeddings, asynchronously
db/extract.py            scan sessions -> decisions -> store
db/cli.py                status / load / find / confirm

test_smoke.py            offline checks (`make test`)
test_integration.py      checks that need a running store (`make test-integration`)
data/seed/decisions.jsonl  demo decisions
data/db/decisions.duckdb   the store itself (gitignored)

docker/Dockerfile        one image for every service, with quack baked in
docker-compose.yml       decision-store + embedding-worker
Makefile                 up / status / seed / find / detect / extract / test
```

## Running it

```bash
cp .env.example .env                    # set QUACK_TOKEN
make up                           # server + worker, detached
make seed                               # load demo decisions
make find TAGS="skalowanie wydajnosc"
make status
```

`make help` lists the rest.

Unlike the `ui` extension used elsewhere in this repo, `quack_serve` binds to
whatever address it is given, so a plain `ports:` mapping works and
`network_mode: host` is not needed.

## Connecting from a developer machine

```python
from client import DecisionStore

store = DecisionStore("quack://<central-host>:8888", token="...")
store.insert_decisions([{ "id": "<uuid of the source message>", ... }])
hits = store.find_precedent(tags=["skalowanie"], limit=3)
```

`QUACK_URI` and `QUACK_TOKEN` are read from the environment as defaults.

## Five things that will cost you an hour each

Found by testing, not by reading docs:

1. **The URI needs its scheme.** `quack_serve('127.0.0.1:8888')` fails with
   `Invalid DuckDB Quack RPC URI`. It must be `quack://127.0.0.1:8888`, on both
   ends, even though the transport underneath is HTTP.

2. **`quack_serve` will not bind `0.0.0.0` on its own:** *"Only localhost is
   allowed as a Quack RPC hostname by default."* Which is exactly what a
   container needs, so `server.py` sets `allow_other_hostname` whenever the host
   is not localhost. Heed the rest of that warning: the token is the only thing
   guarding the port, so on a real network put a reverse proxy with TLS in front
   rather than exposing this directly.

3. **The token must be at least 4 characters, and there is no unauthenticated
   mode.** An empty or short token fails *after* `quack_serve` is already
   running, as a raw DuckDB exception. `server.py` checks up front and exits
   with a sentence instead.

4. **`docker compose run` starts a new container.** Anything talking to the
   running server has to go through `exec`, or it will find nothing listening
   on `127.0.0.1:8888`. The Makefile uses `exec`.

5. **If anyone adds `vss` back:** it has to be loaded by the server process
   itself at startup. Sending `INSTALL vss; LOAD vss` through `quack_query`
   returns `Success` and changes nothing. And HNSW on a persistent database
   needs `hnsw_enable_experimental_persistence`, which carries a data-loss
   warning.

## The record key is not ours to generate

`id` is the **uuid of the source message**, copied from the session `.jsonl`
file. `client.insert_decisions` rejects a record without one rather than
filling it in, because a generated id defeats the entire point.

Sessions are append-only files re-read in full on every extractor run.
Measured on three key choices, with a session containing two decisions:

| Key | After a few runs | |
|---|---|---|
| `sessionId`, or `sessionId` + developer | **1 row out of 2** — the rest vanish silently | sessions hold ~32 assistant messages on average, so decisions collide |
| `uuid()` generated at insert time | every decision duplicated per run | `ON CONFLICT` has nothing stable to match |
| **uuid of the source message** | exactly 2 rows, however many runs | ✅ |

Silent loss is the worse failure of the two, which is why the session-level key
is the trap rather than the obvious choice.

## Retrieval: core functions only, no vss

`array_cosine_similarity` is a **core DuckDB function** -- verified returning
results with no extension loaded at all. So the server loads `quack` and
nothing else: no vss, no experimental flag, one less download that can fail at
container start.

vss would only buy an HNSW index, which at a few dozen rows costs more to
maintain than the full scan it replaces. Rows still waiting for the embedding
worker score 0 rather than dropping out of results.

### BM25 leads the ranking

Text search is DuckDB's own FTS index over `decision_summary` and `rationale`.
It is a real relevance signal, so it sorts first; tag overlap comes next.

The placeholder embeddings sort last and contribute nothing. `mock_embed` sums
hashed bytes without sign variation, so every vector points roughly the same
way and cosine lands in a ~0.95-0.98 band for **any** pair of texts:

```
partycjonowanie  vs  cache TTL                       0.9768
partycjonowanie  vs  "rudy kot spi na parapecie"     0.9801   <-- higher
```

Same query, before and after BM25 went in:

| Ranking | Top hit for "dostawca ponawia webhooki, podwojne obciazenia" |
|---|---|
| cosine over mock_embed | "Migracja w dwoch przebiegach" — wrong, and the right answer was not in the top 3 |
| BM25 | "Idempotency-key na zapisach z zewnatrz", score 3.77, everything else 0 |

`--min-relevance` is therefore a threshold that means something, and is what
makes "no hits" a real answer. `--min-similarity` stays for the day a real
embedding model replaces `mock_embed`; today it cannot separate anything.

**What BM25 does not do:** it matches shared words, not meaning. Asking with
synonyms ("kolejka komunikatow" for "webhooki") will not find the record.

### The index lives on the server and has to be rebuilt

Measured, not assumed:

- It is six ordinary tables inside the database file, so it **survives restarts**
  — no experimental flag, unlike HNSW.
- It does **not** update itself. A row inserted after the last rebuild scores
  NULL. `worker_embeddings.py` rebuilds after every batch it embeds, which is
  exactly the set of new or edited rows.
- Rebuild cost: 0.08 s at 500 rows, 0.29 s at 50k.
- Clients need nothing: no index, no `fts` extension, no database file. The
  server auto-loads `fts` on demand — unlike `vss`, which had to be loaded at
  startup or `CREATE INDEX` failed.
- The syntax is `overwrite=1`, **not** `overwrite:=1`. The colon form is
  rejected, and with stderr redirected it looks like a fast success that leaves
  no index behind.

## Embeddings are computed here, asynchronously

Developer machines never compute vectors. An insert lands with `embedding NULL`
and is immediately searchable by tag; `worker_embeddings.py` fills the vector in
afterwards.

**`embedding IS NULL` is the queue.** No task table — a row states its own
status. Editing a decision's summary resets its embedding to `NULL`, so a
changed record re-queues itself instead of keeping a vector describing text that
is no longer there.

Computing inline at write time would mean every insert waits for inference, and
a model that is down blocks writes — that is, loses decisions. This way the
model can be unavailable for an hour and nothing breaks.

One thing to settle before a real model lands: a query has to be embedded with
the **same** model as the stored rows. `client.py` does that locally, which is
free while `mock_embed` is pure Python. With a model that only runs on the
central host, semantic search from a laptop needs a different answer -- either
the model ships to every machine, or retrieval from a laptop stays tag-only, or
the server grows a query endpoint.

One thing to settle before a real model lands: a query must be embedded with
the **same** model as the stored rows. `client.py` does that locally, which is
free while `mock_embed` is pure Python. With a model that only runs on the
central host, semantic search from a laptop needs a different answer — the model
ships to every machine, retrieval from a laptop stays tag-only, or the server
grows a query endpoint.

`mock_embed` from `common/embeddings.py` is the project's designated swap point.
Replacing it with a real model also means changing `EMBEDDING_DIM` there **and**
the `FLOAT[n]` column in `schema.sql`, then recomputing every vector: fixed-size
arrays cannot change width in place. Pick the model before fixing the number.

## A marker carries three things, or it is not stored

`marker.py` requires all three, and reports what is missing rather than storing
a partial record:

1. **decision** — what was decided
2. **assumptions** — technical *and* business; without them nobody can judge
   whether the precedent transfers to their situation
3. **rationale** — why this option, and why the others were rejected; the code
   already shows what was done, never what was not

A decision without its assumptions is the kind that gets applied where it does
not belong, which is worse than not finding one at all.

**Known limitation:** anything that *talks about* markers contains one. This
README, the skill file and any chat explaining the format are all ingestable.
There is no reliable way to tell an example from the real thing — it has already
happened once, with an example quoted in a conversation. The convention is that
examples leave one required field empty so they cannot parse; `marker.TEMPLATE`
does exactly that.

## Tags are validated, not trusted

`tags.py` holds the frozen vocabulary. `cli.py` rejects anything outside it at
load and at query time, so drift ("kolejki" vs "messaging" vs "queue") surfaces
as an error at write time instead of as a query that silently returns nothing.

Adding a tag is a team decision.

## No hits is an answer

`find_precedent` returns an empty list when nothing clears the threshold, and
callers should say so rather than reach for the closest match. Mid-work, a wrong
precedent does more damage than a missing one, because the agent delivers it in
the register of *"the team already solved this"*.

## Status

Both test files live in the repo and are runnable by anyone:
`make test` (30 offline assertions) and `make test-integration` (23 against a
running store). The integration file writes only under its own project name and
deletes it afterwards, so it is safe against a store holding real decisions; it
skips with exit 0 when no store is reachable, but fails loudly on a rejected
token, since that is a typo rather than an absent server.

Verified end to end, natively **and through Docker**: image build, healthcheck,
the worker picking up new rows on its own, host access over the published port
in both directions, data surviving `down` + `up`, schema, seeding, idempotent
re-ingest, tag search and ranking, similarity ranking, search working before any
vector exists, the similarity threshold, the review loop, tag validation,
records rejected for a missing id, the empty-result path, and 30 concurrent
inserts from 3 clients (30/30, 10 each).

Not verified: **access from a second machine**. Everything so far was host to
container on one computer. That is the first thing to check once the team is in
the same room.

`SCENARIUSZ.md` (Polish) maps the end-to-end scenario onto what is tested and
what is missing. `HANDOVER.md` (Polish) covers the reasoning behind these choices and what to
re-read when picking this up cold.
