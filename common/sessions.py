#!/usr/bin/env python3
"""Find and normalise agent session files, whatever CLI produced them.

Each CLI writes JSONL, and that is where the similarity ends: different
locations, different record shapes, different names for the same thing. This
module hides that behind one iterator of `Message` objects so the extractor
never has to know which tool a session came from.

Verified against real sessions on disk for claude and gemini. The codex adapter
is written from its documented layout but **unverified** -- no codex install was
available. It is registered anyway so it costs one file to fix rather than one
design to change; `detect()` reports which providers actually have data.
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


@dataclass(frozen=True)
class Message:
    """One message from a session, in provider-neutral form."""

    provider: str
    session_id: str
    message_id: str   # stable across re-reads; becomes the decision's primary key
    role: str         # "user" | "assistant"
    text: str
    project: str
    source_file: Path
    timestamp: str | None = None

    @property
    def decision_id(self) -> str:
        """Namespaced key. Message ids are only unique within a provider."""
        return f"{self.provider}:{self.message_id}"


def _texts(content) -> list[str]:
    """Pull plain text out of a content field.

    Both claude and gemini use two shapes for this -- a list of typed blocks
    and a bare string -- and they disagree about which role uses which. Handling
    only the list shape silently drops whole sides of the conversation: on real
    claude sessions that is 58 of 141 user messages, which is where the human's
    own words live.
    """
    if content is None:
        return []
    if isinstance(content, str):
        return [content] if content.strip() else []
    if isinstance(content, dict):
        content = [content]
    out = []
    for block in content:
        if isinstance(block, str):
            if block.strip():
                out.append(block)
        elif isinstance(block, dict):
            # Skip tool_use / tool_result / thinking: noise, and for tool_result
            # potentially large. Only authored prose carries decisions.
            if block.get("type") in (None, "text") and isinstance(block.get("text"), str):
                if block["text"].strip():
                    out.append(block["text"])
    return out


def _read_jsonl(path: Path) -> Iterator[dict]:
    try:
        with path.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue  # a session being written to can end mid-line
                if isinstance(record, dict):
                    yield record
    except OSError:
        return


# -- claude ---------------------------------------------------------------

def _claude_roots() -> list[Path]:
    roots = [Path.home() / ".claude" / "projects"]
    # CLAUDE_CONFIG_DIR relocates the whole tree; several may coexist on one
    # machine (this one has ~/.claude and ~/.claude-fo), so take them all.
    if os.environ.get("CLAUDE_CONFIG_DIR"):
        roots.append(Path(os.environ["CLAUDE_CONFIG_DIR"]) / "projects")
    roots += sorted(Path.home().glob(".claude-*/projects"))
    return roots


def _claude_messages(path: Path) -> Iterator[Message]:
    project = path.parent.name
    for record in _read_jsonl(path):
        if record.get("type") not in ("user", "assistant"):
            continue
        if record.get("isSidechain"):
            continue
        message_id = record.get("uuid")
        if not message_id:
            continue
        message = record.get("message") or {}
        for text in _texts(message.get("content")):
            yield Message(
                provider="claude",
                session_id=record.get("sessionId") or path.stem,
                message_id=message_id,
                role=record["type"],
                text=text,
                project=project,
                source_file=path,
                timestamp=record.get("timestamp"),
            )


# -- gemini ---------------------------------------------------------------

def _gemini_messages(path: Path) -> Iterator[Message]:
    # ~/.gemini/tmp/<project>/chats/<file>, with subagent sessions nested one
    # level deeper, so counting parents backwards yields "chats" rather than the
    # project. Anchor on the "chats" segment instead: it is the one fixed point
    # in both layouts. Anchoring on "tmp" looks equivalent and is not -- inside a
    # container the path starts with /tmp and the first match is the wrong one.
    parts = path.parts
    project = parts[len(parts) - 1 - parts[::-1].index("chats") - 1] if "chats" in parts else path.parent.name
    session_id = path.stem
    for record in _read_jsonl(path):
        # The session id lives on a header record, not on every message the way
        # claude does it. Read it once and carry it.
        if "sessionId" in record and "kind" in record:
            session_id = record["sessionId"]
            continue

        # Messages arrive both as their own records and inside a "$set"
        # snapshot of the whole list. Walking both is safe: the ids repeat, and
        # repeated ids are exactly what the upsert is for.
        batch = []
        if isinstance(record.get("$set"), dict):
            batch = record["$set"].get("messages") or []
        elif record.get("id") and record.get("type"):
            batch = [record]

        for item in batch:
            if not isinstance(item, dict):
                continue
            role = "assistant" if item.get("type") == "gemini" else item.get("type")
            if role not in ("user", "assistant"):
                continue
            message_id = item.get("id")
            if not message_id:
                continue
            for text in _texts(item.get("content")):
                yield Message(
                    provider="gemini",
                    session_id=session_id,
                    message_id=message_id,
                    role=role,
                    text=text,
                    project=project,
                    source_file=path,
                    timestamp=item.get("timestamp"),
                )


# -- codex (UNVERIFIED) ---------------------------------------------------

def _codex_messages(path: Path) -> Iterator[Message]:
    """Adapter for codex rollout files. Never run against real data.

    Written against the documented rollout shape: records carrying a `type` and
    a `payload`, with messages as role/content. Treat every field name here as a
    guess until someone points it at a real ~/.codex/sessions tree.
    """
    project = path.parent.name
    for index, record in enumerate(_read_jsonl(path)):
        payload = record.get("payload") if isinstance(record.get("payload"), dict) else record
        role = payload.get("role") or payload.get("type")
        if role == "model":
            role = "assistant"
        if role not in ("user", "assistant"):
            continue
        # Rollout records are not known to carry per-message ids, so fall back
        # to file plus position. Sessions are append-only, so position is stable.
        message_id = payload.get("id") or record.get("id") or f"{path.stem}#{index}"
        for text in _texts(payload.get("content") or payload.get("text")):
            yield Message(
                provider="codex",
                session_id=record.get("session_id") or path.stem,
                message_id=str(message_id),
                role=role,
                text=text,
                project=project,
                source_file=path,
                timestamp=record.get("timestamp"),
            )


PROVIDERS = {
    "claude": {"roots": _claude_roots, "glob": "**/*.jsonl", "reader": _claude_messages,
               "verified": True},
    "gemini": {"roots": lambda: [Path.home() / ".gemini" / "tmp"], "glob": "**/chats/**/*.jsonl",
               "reader": _gemini_messages, "verified": True},
    "codex": {"roots": lambda: [Path.home() / ".codex" / "sessions"], "glob": "**/*.jsonl",
              "reader": _codex_messages, "verified": False},
}


def session_files(provider: str) -> list[Path]:
    spec = PROVIDERS[provider]
    files: list[Path] = []
    for root in spec["roots"]():
        if root.is_dir():
            files.extend(sorted(root.glob(spec["glob"])))
    return files


def detect() -> dict[str, int]:
    """Which providers actually have sessions on this machine, and how many."""
    return {name: len(session_files(name)) for name in PROVIDERS}


def iter_messages(providers: list[str] | None = None) -> Iterator[Message]:
    for name in providers or list(PROVIDERS):
        if name not in PROVIDERS:
            raise ValueError(f"unknown provider {name!r}; known: {sorted(PROVIDERS)}")
        reader = PROVIDERS[name]["reader"]
        for path in session_files(name):
            yield from reader(path)


if __name__ == "__main__":
    for name, count in detect().items():
        mark = "" if PROVIDERS[name]["verified"] else "  [adapter unverified]"
        print(f"{name:8} {count:4} session file(s){mark}")
