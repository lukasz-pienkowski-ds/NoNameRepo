---
name: tag-session
description: Label the messages of the current Claude Code session with a domain and tags from a controlled vocabulary, and append them to the labeled session catalog as JSONL. Use only when the user explicitly asks for it — "tag this session", "label the session", "capture this conversation", "/tag-session". Never invoke it on your own initiative, and never mid-task: it reads the session transcript, so the more of the conversation that exists when it runs, the more it captures.
---

# Tag Session

Labels this session's messages so they can be retrieved later. Each human prompt and each assistant reply becomes one JSONL record carrying the message text verbatim plus a `domain` and `tags`. Nothing is summarized, condensed or interpreted here — pulling meaning out of these records is a separate job done downstream by the database side.

Records land in `~/.claude/labeled/<escaped-project-path>/<session-id>.jsonl`, mirroring how Claude Code names its own transcript directories. Each record carries its source message `uuid`, which means the catalog is its own state: run this again later in the same session and only the messages exchanged since will be labeled.

## Workflow

### Step 1 — Extract the messages

```bash
.venv/bin/python .claude/skills/tag-session/scripts/extract_messages.py
```

This finds the current session's transcript, keeps what the user and the assistant actually said, drops everything already labeled, and prints the result as JSON with a `uuid` for each. It also writes the full untruncated messages to a `messages.json` whose path it reports — the writer needs that path in step 3.

Four things count as a message: a human prompt, an assistant text reply, **the reason a user gave for rejecting a tool call**, and **the answers a user chose when asked a question**. The last two arrive in the transcript as tool results rather than prompts, but they are the user speaking, and they are often where a decision is actually made — a rejected plan with "no, do it the other way" in the reason carries more than the plan did. Tool calls, tool output, file contents, thinking blocks and editor context are all dropped.

Long messages are truncated **in this output only**; the stored record always holds the full text.

If it reports `to_label: 0`, everything is already captured. Say so and stop.

### Step 2 — Label every message

Read `references/taxonomy.md`, then assign to each message one `domain` and one to four `tags`.

Label what the message is **about**, not what it is. A message that says "yes, do that" is about nothing on its own — it does not inherit the topic of the message before it.

**`null` is a first-class answer and you will use it often.** Acknowledgements, approvals, typo corrections, "run it again", thanks, and tool-wrangling chatter carry no engineering content. Give them `"domain": null, "tags": []`. Forcing a plausible-looking domain onto a message that has none is the single thing that ruins retrieval later, because a search for `concurrency` should not surface someone saying "ok".

Tag the tradeoff axis rather than the technology — `cache-invalidation`, not `redis`. The technology stays in the message text.

Write the labels as a JSON array, one entry per message, and nothing else:

```json
[
  {"uuid": "a4987638-...", "domain": "process", "tags": ["config-management"]},
  {"uuid": "3a1c2dfe-...", "domain": null, "tags": []}
]
```

Cover every uuid the extractor returned. Save the array to a file in your scratchpad directory.

### Step 3 — Write the records

```bash
.venv/bin/python .claude/skills/tag-session/scripts/write_labels.py <labels.json> --messages <messages.json>
```

The writer validates every domain and tag against the vocabulary, joins them onto the extracted text, and appends to the catalog. It rejects unknown labels rather than storing them — if it complains, fix the labels and rerun; it will not double-write anything that already landed.

### Step 4 — Report

One line: how many records were written, how many messages were left unlabeled as `null`, and where the file is.

## Record shape

```json
{"uuid":"a4987638-...","username":"Igor Kolasa","role":"user","domain":"process","tags":["config-management"],"message":"..."}
```

`username` comes from `git config user.name` and identifies whose session this was, on both roles; `role` distinguishes the speaker.
