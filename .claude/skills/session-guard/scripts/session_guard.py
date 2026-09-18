#!/usr/bin/env python3
"""Check a developer's Claude Code session against this project's precedent.

Parses a session transcript (JSONL, Claude Code's own format), derives a
domain and a "what's been happening" query from it, and asks the
context-store server for the matching precedent — grouped by topic
(server's /context) and, if that domain has little of its own context, also
ranked across the whole store (server's /query) so cross-project precedent
isn't missed.

This script only fetches; it does not judge. It hands back:
  - recent_moves: the developer's last N tool actions (edits, writes, bash
    commands) extracted from the transcript, each as {"type", "detail"}
  - context: this domain's precedent, ranked by relevance to recent_moves
  - extra_matches: whole-store matches, only included as a fallback when the
    domain's own context is thin (see --extra-threshold)

Comparing recent_moves against context/extra_matches — deciding what's
compliant, what conflicts, and what to suggest instead — is the actual job
of session-guard/SKILL.md, not this script.

TODO(real-transcript-schema): field names below (`cwd`, `message.content`,
tool_use blocks) match Claude Code's current transcript format as observed;
if that format changes, only the parsing in load_transcript() needs to.
"""

import argparse
import json
import os
import urllib.request
from pathlib import Path

DEFAULT_URL = os.environ.get("CONTEXT_STORE_URL", "http://localhost:8000")


def load_transcript(path: Path, recent: int) -> tuple[str | None, list[dict], str]:
    domain = None
    moves = []
    texts = []

    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue

            if domain is None and rec.get("cwd"):
                domain = Path(rec["cwd"]).name

            content = (rec.get("message") or {}).get("content")
            if isinstance(content, str):
                texts.append(content)
            elif isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") == "text" and block.get("text"):
                        texts.append(block["text"])
                    elif block.get("type") == "tool_use":
                        inp = block.get("input", {}) or {}
                        detail = (
                            inp.get("file_path")
                            or inp.get("path")
                            or inp.get("command")
                            or json.dumps(inp)[:200]
                        )
                        moves.append({"type": block.get("name", "tool"), "detail": detail})

    moves = moves[-recent:]
    query_text = "\n".join(texts[-recent:] + [m["detail"] for m in moves])[-4000:]
    return domain, moves, query_text


def _post(url: str, path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        f"{url.rstrip('/')}{path}",
        data=json.dumps(payload).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def check_session(
    transcript_path: Path,
    domain: str | None = None,
    top_k: int = 5,
    recent: int = 20,
    extra_threshold: int = 3,
    url: str = DEFAULT_URL,
) -> dict:
    inferred_domain, moves, query_text = load_transcript(transcript_path, recent)
    domain = domain or inferred_domain
    if not domain:
        raise ValueError(
            "Could not infer a domain from the transcript (no 'cwd' field found) — pass --domain explicitly."
        )

    context = _post(url, "/context", {"domain": domain, "query": query_text})

    extra_matches = []
    if context["count"] < extra_threshold and query_text:
        seen = {d["id"] for d in context["documents"]}
        for m in _post(url, "/query", {"text": query_text, "top_k": top_k}):
            if m["id"] not in seen:
                extra_matches.append(m)

    return {
        "domain": domain,
        "recent_moves": moves,
        "context": context,
        "extra_matches": extra_matches,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("transcript_path", type=Path, help="Path to a Claude Code session .jsonl transcript")
    parser.add_argument("--domain", default=None, help="Override the domain inferred from the transcript's cwd")
    parser.add_argument("--top-k", type=int, default=5, help="Max whole-store fallback matches")
    parser.add_argument("--recent", type=int, default=20, help="How many recent messages/tool-calls to consider")
    parser.add_argument(
        "--extra-threshold",
        type=int,
        default=3,
        help="Fetch whole-store fallback matches when domain context count is below this",
    )
    parser.add_argument("--url", default=DEFAULT_URL, help="context-store base URL (default: %(default)s)")
    args = parser.parse_args()

    result = check_session(
        args.transcript_path, args.domain, args.top_k, args.recent, args.extra_threshold, args.url
    )
    print(json.dumps(result, indent=2, default=str))
