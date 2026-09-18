#!/usr/bin/env python3
"""Extract the labelable messages from a Claude Code session transcript.

Keeps human prompts and assistant text replies; drops attachments, tool calls,
tool results, thinking blocks and bookkeeping records. Messages already present
in the session's catalog are skipped, so a second run only returns what is new.

Writes the full messages (untruncated) to a JSON file for write_labels.py, and
prints a compact view to stdout for the model to label.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

CATALOG_ROOT = Path.home() / ".claude" / "labeled"
PROJECTS_ROOT = Path.home() / ".claude" / "projects"

# Editor and harness context wrapped around a prompt is not part of what the
# user said, and an <ide_selection> blob dwarfs most messages.
NOISE_BLOCKS = re.compile(
    r"<(ide_selection|ide_opened_file|ide_diagnostics|system-reminder)>.*?</\1>",
    re.DOTALL,
)

# When the user rejects a tool call they usually say why, and when they answer a
# question they are making a decision. Both arrive as tool results rather than
# prompts, and both are the user speaking.
DENIAL_REASON = re.compile(r"reason for the rejection:\s*(.+)", re.DOTALL)
ANSWER_BOILERPLATE = (
    "Your questions have been answered: ",
    "The user answered: ",
)
ANSWER_TRAILERS = (
    " You can now continue with these answers in mind.",
    " Read the answers carefully — they may request clarification, changes, "
    "or that you not proceed — and follow what they actually say.",
)


def escape_project(cwd: Path) -> str:
    """Mirror Claude Code's own project directory naming: / becomes -."""
    return str(cwd).replace("/", "-")


def resolve_transcript(cwd: Path, session: str | None, transcript: Path | None) -> Path:
    if transcript:
        return transcript
    project_dir = PROJECTS_ROOT / escape_project(cwd)
    if session:
        return project_dir / f"{session}.jsonl"
    candidates = sorted(
        project_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    if not candidates:
        sys.exit(f"No transcripts found in {project_dir}")
    return candidates[0]


def resolve_username(cwd: Path) -> str:
    for args in (["git", "config", "user.name"], ["git", "config", "user.email"]):
        try:
            out = subprocess.run(
                args, cwd=cwd, capture_output=True, text=True, timeout=5
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    return os.environ.get("USER", "unknown")


def already_labeled(catalog: Path) -> set[str]:
    """uuids already written for this session — the catalog is its own state."""
    if not catalog.exists():
        return set()
    seen = set()
    with catalog.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                seen.add(json.loads(line)["uuid"])
            except (json.JSONDecodeError, KeyError):
                continue
    return seen


def user_text(record: dict) -> str | None:
    """What the user said in this record — a prompt, a rejection, or an answer."""
    if record.get("isMeta") or record.get("turnCompanion"):
        return None
    if record.get("origin", {}).get("kind") == "human" and not record.get("toolUseResult"):
        blocks = record.get("message", {}).get("content", [])
        if isinstance(blocks, str):
            return clean(blocks)
        parts = [b.get("text", "") for b in blocks if b.get("type") == "text"]
        return clean("\n\n".join(p for p in parts if p))
    return denial_text(record) or answer_text(record)


def tool_result_text(record: dict) -> str | None:
    blocks = record.get("message", {}).get("content", [])
    if not isinstance(blocks, list):
        return None
    for block in blocks:
        if block.get("type") == "tool_result" and isinstance(block.get("content"), str):
            return block["content"]
    return None


def denial_text(record: dict) -> str | None:
    """The reason the user gave for rejecting a tool call, if they gave one."""
    if not record.get("toolDenialKind"):
        return None
    result = record.get("toolUseResult")
    source = result if isinstance(result, str) else tool_result_text(record)
    if not source:
        return None
    match = DENIAL_REASON.search(source)
    return clean(match.group(1)) if match else None


def answer_text(record: dict) -> str | None:
    """The choices the user made when answering a question."""
    result = record.get("toolUseResult")
    if not isinstance(result, dict) or "questions" not in result:
        return None
    text = tool_result_text(record)
    if not text:
        return None
    for prefix in ANSWER_BOILERPLATE:
        if text.startswith(prefix):
            text = text[len(prefix) :]
    for trailer in ANSWER_TRAILERS:
        text = text.replace(trailer, "")
    return clean(text)


def clean(text: str) -> str | None:
    text = NOISE_BLOCKS.sub("", text).strip()
    return text or None


def assistant_text(record: dict) -> str | None:
    """Text of one assistant content block, or None if it is not a text block."""
    if record.get("isSidechain"):
        return None
    blocks = record.get("message", {}).get("content", [])
    if isinstance(blocks, str):
        return blocks.strip() or None
    parts = [b.get("text", "") for b in blocks if b.get("type") == "text"]
    return "\n\n".join(p for p in parts if p).strip() or None


def extract(transcript: Path, username: str) -> list[dict]:
    """One record per human prompt and per assistant reply, in transcript order.

    An assistant reply arrives split across several lines, one per content block,
    sharing a requestId and ordered by apiBlockIndex. Those are joined back into
    a single message keyed by the first block's uuid.
    """
    messages: list[dict] = []
    assistant_index: dict[str, int] = {}

    with transcript.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            kind = record.get("type")
            if kind == "user":
                text = user_text(record)
                if text:
                    messages.append(
                        {
                            "uuid": record["uuid"],
                            "role": "user",
                            "username": username,
                            "message": text,
                        }
                    )
            elif kind == "assistant":
                text = assistant_text(record)
                if not text:
                    continue
                request_id = record.get("requestId") or record["uuid"]
                if request_id in assistant_index:
                    pos = assistant_index[request_id]
                    messages[pos]["message"] += "\n\n" + text
                else:
                    assistant_index[request_id] = len(messages)
                    messages.append(
                        {
                            "uuid": record["uuid"],
                            "role": "assistant",
                            "username": username,
                            "message": text,
                        }
                    )

    return messages


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", help="Session id; defaults to the newest transcript")
    parser.add_argument("--transcript", type=Path, help="Explicit transcript path")
    parser.add_argument("--cwd", type=Path, default=Path.cwd(), help="Project directory")
    parser.add_argument("--out", type=Path, help="Where to write the full messages JSON")
    parser.add_argument(
        "--max-chars",
        type=int,
        default=2000,
        help="Truncation applied to the stdout view only (0 disables)",
    )
    args = parser.parse_args()

    cwd = args.cwd.resolve()
    transcript = resolve_transcript(cwd, args.session, args.transcript)
    if not transcript.exists():
        sys.exit(f"Transcript not found: {transcript}")

    session_id = transcript.stem
    catalog = CATALOG_ROOT / escape_project(cwd) / f"{session_id}.jsonl"
    seen = already_labeled(catalog)

    username = resolve_username(cwd)
    messages = [m for m in extract(transcript, username) if m["uuid"] not in seen]

    out_path = args.out or (
        Path(tempfile.gettempdir()) / "tag-session" / f"{session_id}.messages.json"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "session_id": session_id,
        "cwd": str(cwd),
        "catalog": str(catalog),
        "messages": messages,
    }
    out_path.write_text(json.dumps(payload, indent=2))

    view = []
    for m in messages:
        text = m["message"]
        if args.max_chars and len(text) > args.max_chars:
            text = text[: args.max_chars] + f"... [truncated, {len(m['message'])} chars]"
        view.append({"uuid": m["uuid"], "role": m["role"], "text": text})

    print(
        json.dumps(
            {
                "session_id": session_id,
                "messages_file": str(out_path),
                "already_labeled": len(seen),
                "to_label": len(messages),
                "messages": view,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
