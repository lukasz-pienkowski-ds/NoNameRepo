---
name: project-context
description: Load a project's ingested context (from tagged Claude Code sessions) grouped by topic, and apply it as operating guidance — conventions, gotchas, and past decisions — not just as an answer to a question. Use at the start of work on a project whose domain has ingested context, or whenever unsure how this codebase expects something to be done.
---

# Project Context

Asks the context-store server for everything ingested under a given
`domain`, grouped by topic (tag), and tells you how to actually use it: as
precedent that shapes how you work on this project, not as trivia to recite
back. This skill never touches the DuckDB file itself — it's a plain HTTP
client to the server, which can be local docker-compose or a remote host.

## When to use this skill

Use it proactively, before starting non-trivial work on a project that has
ingested context — not only when the user asks a question. The context
comes from tagged, embedded Claude Code sessions on this domain, so it
captures conventions, gotchas, and decisions previous sessions already
worked out.

## How to run it

The context-store server must be running first (`make up` starts it at
`http://localhost:8000` — see the project README). This skill's script is a
plain HTTP client; it needs no Docker access of its own, only network
access to the server.

```bash
make context DOMAIN=<domain> [MODEL=<model_name>] [TAGS=<tag1,tag2>] [CTXQ="<query text>"]
# equivalent: python3 .claude/skills/project-context/scripts/project_context.py <domain> [--model ...] [--tags ...] [--query ...] --url $CONTEXT_STORE_URL
```

Set `CONTEXT_STORE_URL` (default `http://localhost:8000`) to point at a
different server — e.g. `make context DOMAIN=... CONTEXT_STORE_URL=http://1.2.3.4:8000`.

Prints JSON: `{domain, requested_model, used_model_fallback, count, topics, documents}`.

- `topics` maps each tag to the document ids under it — use this to scan what's covered before reading full text.
- `MODEL` filters to context produced by a specific model. If nothing matches, the server automatically falls back to all models for that domain and sets `used_model_fallback: true` — **when you see that flag, say so** ("no model-specific context for X, showing all context for this domain") rather than presenting the fallback results as if they were the requested match.
- `CTXQ` ranks results by similarity to a query instead of recency — use it to narrow a large domain's context to what's relevant to the current task.

## How to apply the results

This is the actual point of the skill — retrieval alone doesn't help unless
you act on it:

1. **Treat entries as precedent, not trivia.** If context says a project always upserts instead of inserting, or always runs through Docker, follow that convention in the code/instructions you produce — don't just mention it if asked.
2. **Resolve conflicts by recency.** If two documents disagree (e.g. an old decision vs. a newer one), prefer the one with the later `ingested_at`/source date and say you did so.
3. **Cite doc ids.** When a piece of guidance changes what you do, name the `id` it came from, so the user can trace it back to the source session.
4. **Say plainly when a domain has no context yet** (`count: 0`) instead of inventing conventions or staying silent about the gap — an empty result is information, not a failure.
5. **Flag model-fallback results** (`used_model_fallback: true`) as above, since they may reflect a different model's conventions than the current one.

## Current status: mock

Retrieval uses `mock_embed`/`mock_tag` from `common/embeddings.py`, run
server-side — see `query-context`'s SKILL.md for the same caveat.
`domain`/`model_name` are also an assumed placeholder schema (see
`db/schema.sql`) pending the real ingestion schema; only `db/schema.sql` and
`db/store.py` reference those column names.
