---
name: session-guard
description: Check what's happening in the current agent session against precedent in the central decision store (db/client.py, over quack) and either hand over the matching decision or, when it doesn't clearly transfer, ask about the constraint instead. Use repeatedly during active work on any project — after edits, commands, or design decisions — not only once at the start.
---

# Session Guard

Implements the "precedent" and "grill" retrieval modes from
`docs/SCENARIUSZ.md` step 8 — the part of the team's scenario the docs
explicitly flag as designed but not yet written ("to połowa demo"). A
developer's agent queries the central decision store for precedent set by
someone else, possibly on a different project entirely, and uses it two
ways depending on how well it fits:

- **Precedent mode**: the retrieved decision's assumptions clearly match the
  current situation → hand over the decision, its rationale, and who made
  it. This is what a junior facing a familiar problem needs.
- **Grill mode**: the retrieved decision is topically related but its
  assumptions don't clearly hold here → don't hand over the old answer as if
  it applied. Surface the constraint as a question instead ("the precedent
  for X assumed <assumption> — does that hold here, or does this need its
  own decision?"). Handing over a precedent whose assumptions don't
  transfer is worse than finding nothing (`docs/HANDOVER.md` #8), because
  it's presented as "the team already solved this."

Nothing needs to be supplied by the user to run this — no session path, no
project name, no `make` target. Run the script yourself against your own
current session; it finds its own session file and infers its own project.

## When to use this skill

Use it proactively and repeatedly while working with an agent:
- After a batch of edits, a command run, or a design decision — not only once at the start of the session.
- Whenever you're about to say "looks good" or move on — check first.
- When the user asks you to review/validate progress against team precedent.

A single pass is a snapshot, not a verdict — keep re-checking as the session
progresses.

## How to run it

```bash
uv run python .claude/skills/session-guard/scripts/session_guard.py --uri "${QUACK_URI:-quack://127.0.0.1:8888}" --token "${QUACK_TOKEN:?set QUACK_TOKEN}"
```

`--uri`/`--token` default to the `QUACK_URI`/`QUACK_TOKEN` environment
variables (the same ones `db/cli.py` and `db/client.py` use — `client.py`
also reads `.env` in the repo root, so sourcing that file works too). With
no `session_path` argument, the script finds the current session's own
transcript automatically — the most recently modified file for `--provider`
(default `claude`; also supports `gemini`/`codex`) via
`common/sessions.py`'s own session discovery. Needs `duckdb` installed
locally (the `quack` extension loads into it), so run it with `uv run`, not
a bare system python3.

It returns:

```json
{
  "project": "...",
  "session_file": "/path/it/found/automatically.jsonl",
  "recent_moves": [{"role": "user"|"assistant", "text": "..."}, ...],
  "precedent": [
    {"id": "...", "developer_id": "...", "decision_summary": "...",
     "assumptions_tech": [...], "assumptions_biz": [...], "rationale": "...",
     "rejected_options": [...], "tags": [...], "status": "...",
     "relevance": 0.0, "tag_overlap": 0, "similarity": 0.0}
  ]
}
```

`precedent` is ranked BM25-first (`relevance` — the one real signal today),
then `tag_overlap`, then `similarity` last (`mock_embed` is measured noise —
see `docs/HANDOVER.md` #5; don't re-sort by `similarity`, that reintroduces
exactly the ranking bug the team already found and fixed). An empty list is
a valid, common answer — no tag filter is applied here, so an empty result
means nothing in the whole store is textually relevant, not that this one
project lacks precedent.

## How to judge it — the actual point of this skill

Retrieval alone is not the deliverable. For each item in `precedent`,
ordered as returned:

1. **Check whether its assumptions transfer.** Compare `assumptions_tech`/`assumptions_biz` against what you can see of the current situation. If they clearly hold → **precedent mode**. If they clearly don't, or you can't tell → **grill mode**.
2. **Precedent mode**: state the decision (`decision_summary`), its rationale, `developer_id` as who made it, and `rejected_options` if relevant to why an alternative the developer is considering was already tried and dropped. Cite the `id`.
3. **Grill mode**: name the assumption the precedent depends on, ask directly whether it holds here, and don't present the old decision as settled for this situation until it's confirmed. Cite the `id` you're grilling against.
4. **Weigh `status`**: `confirmed` precedent is stronger than `unknown` (nobody's closed the review loop on it yet); `rejected` means it was tried and abandoned — cite it as a warning, not as guidance to follow.
5. **Multiple relevant hits with conflicting decisions**: prefer the more recent `created_at`, but say explicitly that an older, conflicting decision exists rather than silently dropping it.
6. **Nothing came back**: say plainly that no team precedent covers this yet — don't invent conventions to hold the developer to. This is expected early on, not a failure of the skill.
7. **Keep going**: after judging, note what to re-check on the next pass rather than treating this run as final sign-off.

## Current status

`common/embeddings.py`'s `mock_embed` remains a placeholder (a deterministic
hashed pseudo-vector — see `docs/HANDOVER.md` #5 for the measured noise
floor), which is exactly why this skill leans on BM25 relevance rather than
similarity. When a real embedding model replaces it, `similarity` becomes
meaningful and worth weighing again — nothing here needs to change to pick
that up, since `find_precedent` already returns it.
