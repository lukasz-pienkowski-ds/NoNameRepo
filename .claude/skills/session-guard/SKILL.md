---
name: session-guard
description: Check a developer's ongoing Claude Code session against this project's ingested precedent (conventions, decisions, gotchas) and validate whether their recent moves comply, not just answer questions about it. Use repeatedly during active work on a project with ingested context — after edits, commands, or design decisions — not only once at the start.
---

# Session Guard

Retrieves the precedent relevant to what a developer is *currently doing* in
a Claude Code session (not a generic query), then checks their recent moves
against it and reports compliance/violations with concrete fixes. This is
`project-context`'s sibling: `project-context` answers "what do I need to
know about this project", session-guard answers "is what just happened
actually consistent with that".

## When to use this skill

Use it proactively and repeatedly while a session is active on a project
with ingested context:
- After a batch of edits, a command run, or a design decision — not only once at the start of the session.
- Whenever you're about to say "looks good" or move on — check first.
- When the user asks you to review/validate progress against project conventions.

A single pass is a snapshot, not a verdict — keep re-checking as the session
progresses.

## How to run it

The context-store server must be running (`make up` — see the project
README). This skill's script is a plain HTTP client; it needs no Docker
access of its own, only network access to the server and read access to the
session transcript file.

```bash
make guard SESSION=<path-to-transcript.jsonl> [GDOMAIN=<override>]
# equivalent: python3 .claude/skills/session-guard/scripts/session_guard.py <path> [--domain ...] --url $CONTEXT_STORE_URL
```

The script infers `domain` from the transcript's `cwd` (project directory
name) unless overridden, builds a query from the session's recent
messages/tool-calls, and returns:

```json
{
  "domain": "...",
  "recent_moves": [{"type": "Edit", "detail": "path/or/command"}, ...],
  "context": {"count": ..., "topics": {...}, "documents": [...]},
  "extra_matches": [...]
}
```

`extra_matches` only appears when the domain's own context is thin
(`context.count` below a threshold) — those are whole-store matches from
other domains, included because generic precedent (e.g. "always upsert",
"never commit secrets") can still apply. Treat them as lower-confidence than
`context.documents`.

## How to validate — the actual point of this skill

Retrieval alone is not the deliverable. For each move in `recent_moves`,
check it against `context.documents` (and `extra_matches` if present):

1. **Classify each move**: ✅ compliant with a specific doc, ⚠️ conflicts with a specific doc, or ➖ not covered by any retrieved precedent.
2. **For every ⚠️**: name the move, name the doc id it conflicts with, quote or closely paraphrase what the precedent says, and propose the specific corrective change — a concrete edit or command, not general advice ("this conflicts with sess-002: don't add local run instructions — remove the non-Docker steps you just added to the README").
3. **Don't stay silent about ➖**: if a domain has real risk areas (security, data integrity, deployment) with no matching precedent, say so explicitly rather than treating silence as approval.
4. **Resolve conflicting precedent by recency** (later `ingested_at` wins), same as `project-context`.
5. **Prefer `context.documents` over `extra_matches`** when both are relevant — the domain-scoped precedent is the higher-confidence signal.
6. **When `context.count` is 0 and `extra_matches` is empty**: say plainly there's no established precedent for this domain yet — don't invent conventions to hold the developer to.
7. **Keep going**: after flagging something, note what to re-check on the next pass rather than treating this run as final sign-off.

## Current status: mock

Retrieval uses `mock_embed`/`mock_tag` from `common/embeddings.py`, run
server-side — see `query-context`'s SKILL.md for the same caveat.
`domain`/`model_name` are an assumed placeholder schema (see
`db/schema.sql`); transcript parsing (`load_transcript()` in
`scripts/session_guard.py`) assumes Claude Code's current JSONL shape
(`cwd`, `message.content` blocks) and is the one place to update if that
format changes.
