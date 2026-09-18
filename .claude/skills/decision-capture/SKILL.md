---
name: decision-capture
description: Capture a short, structured record of an engineering decision made during the session — the problem, the decision, and its domain and tags — and write it to a local JSON file. Use this skill whenever the session reaches a real fork in the road: choosing between design patterns, libraries, data models, sync vs async, a migration strategy, an auth or caching approach, a retry/consistency policy, or any choice that was hard enough to argue about and would cost someone else a day to rediscover. Trigger it proactively — when the user says things like "let's go with X instead of Y", "I think we should use...", "which approach is better here", "that didn't work, try another way", or when a comparison of approaches has just concluded — even if nobody asks for documentation. Do not use it for routine implementation, naming, formatting, or decisions that are trivially reversible and locally scoped.
---

# Decision Capture

A session with an agent already contains the most valuable artifact a team produces: the reasoning behind a choice, including the paths that were abandoned and the reason they were abandoned. That reasoning normally dies on one laptop. This skill turns it into a small, structured JSON record.

This is a trial version: capture and extraction only. Nothing is read from or written to a shared database.

**Better nothing than something unreliable.** A weak record about a critical decision is worse than silence, because the next reader will take it as "the team already solved this". When a decision does not clear the quality bar, skip it and say so in one line.

## Workflow

### Step 1 — Decide whether this is worth capturing

Apply the bar in `references/quality-bar.md`. In short, capture when the decision was **contested** (a real alternative existed), **costly to reverse or to rediscover**, and **legible outside this repo**. Skip the rest. Most sessions produce zero records; some produce one. Producing three is a signal the bar is being applied too loosely.

### Step 2 — Compact the session down to the decision

Reread the part of the session leading to the fork and extract only:

- the problem as it was actually encountered, including the symptom that surfaced it
- the hard constraints that actually bounded the choice (latency budget, mandated stack, deadline, compliance, team skill, existing data volume)
- the options that were seriously considered, including ones tried and abandoned mid-implementation
- the choice and the reason it beat the alternatives

Discard tooling noise, file listings, syntax errors, and everything the agent got wrong for reasons unrelated to the decision.

### Step 3 — Tag it

Pick exactly one `domain` and one to four `tags` from the controlled vocabulary in `references/taxonomy.md`. The vocabulary exists so retrieval works across projects; inventing a new label per session makes the records unsearchable. If nothing fits, choose the closest one and add a proposal prefixed `new:` for later curation.

### Step 4 — Write the JSON file

Get the author from `git config user.name` (fall back to `git config user.email`). Then write one file per decision to `.decisions/<YYYY-MM-DD>-<short-slug>.json` in the repo root, creating the directory if needed:

```json
{
  "author": "Igor Kolasa",
  "domain": "concurrency",
  "tags": ["async-vs-sync", "third-party-api-limits"],
  "summary": "An ETL step spent ~90% of wall time waiting on a third-party HTTP API rated at 20 req/s. Moved the fetch layer to async with a semaphore-bounded pool and kept the transform layer synchronous because it was CPU-bound; threads were rejected because the codebase was already on an async web framework."
}
```

`summary` is the whole record: one paragraph covering the problem, the constraint that bound it, the option chosen, and why the alternatives lost. Aim for three to six sentences — long enough that someone else can act on it, short enough to read in under a minute.

Then tell the developer in one line what was written and where.

## When not to capture

Silence is the correct output for: naming and formatting, library choices with one obvious answer, anything reversible in under an hour with local blast radius, decisions driven purely by an explicit client mandate with no reasoning to transfer, and the third near-duplicate record in one session. If the developer asks for a record that does not clear the bar, say plainly that it would add noise, and offer to capture it anyway if they still want it.
