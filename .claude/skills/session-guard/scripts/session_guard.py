#!/usr/bin/env python3
"""Check a developer's current session against the central decision store.

This is the "precedent" (and, where warranted, "grill") mode from
docs/SCENARIUSZ.md step 8 -- the half of the scenario the team's own docs
flag as designed but not written. A junior's agent queries the central store
for precedent set by others and either hands over the decision + rationale
(precedent), or, when the retrieved precedent's assumptions don't clearly
match the current situation, surfaces the constraint as a question instead
of a ready answer (grill). See SKILL.md for which mode applies when.

Talks to the store exactly the way db/cli.py's `find` command does:
db.client.DecisionStore.find_precedent(query_text=..., limit=...), ranked
BM25 first (real signal), then tag_overlap, then cosine similarity last
(mock_embed is measured noise -- see docs/HANDOVER.md #5). No project or
tag filter is applied here: the whole point of the central store is that
precedent from someone else's project is exactly what a junior facing a new
problem needs to find.

Reads the *current* session with common/sessions.py -- the same,
already-verified reader the extractor uses -- instead of hand-rolling
transcript parsing. Auto-finds the most recently modified session file for
the given provider (default: claude), so no path needs to be supplied by a
human.

This script only fetches; it does not judge. Comparing recent_moves against
precedent -- deciding what's compliant, what conflicts, precedent vs. grill,
and what to suggest instead -- is SKILL.md's job, not this script's.
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from db.client import DEFAULT_TOKEN, DEFAULT_URI, DecisionStore  # noqa: E402
from common.sessions import Message, session_files, iter_messages  # noqa: E402


def find_current_session(provider: str = "claude") -> Path:
    files = session_files(provider)
    if not files:
        raise FileNotFoundError(f"No {provider} session files found on this machine.")
    return max(files, key=lambda p: p.stat().st_mtime)


def load_session(path: Path, provider: str, recent: int) -> tuple[str, list[Message]]:
    """Messages from this one session file, via the shared reader.

    Scoped to the file's own directory (not a full home-directory scan) by
    passing it as `root` -- session_files/iter_messages then only see
    session files that live alongside this one.
    """
    messages = [m for m in iter_messages([provider], root=path.parent) if m.source_file == path]
    project = messages[0].project if messages else path.parent.name
    return project, messages[-recent:]


def _strip_decision_log(text: str) -> str:
    """Drop <decision_log> blocks from the query text.

    Otherwise a message that quotes the marker format (like this docstring's
    neighbors, or SKILL.md itself) gets treated as if it were a real logged
    decision -- the exact trap docs/HANDOVER.md #2c warns about, on the read
    side instead of the extractor's.
    """
    return re.sub(r"<decision_log>.*?</decision_log>", "", text, flags=re.DOTALL)


def check_session(
    provider: str = "claude",
    session_path: Path | None = None,
    top_k: int = 5,
    recent: int = 20,
    uri: str = DEFAULT_URI,
    token: str = DEFAULT_TOKEN,
) -> dict:
    session_path = session_path or find_current_session(provider)
    project, messages = load_session(session_path, provider, recent)

    query_text = "\n".join(_strip_decision_log(m.text) for m in messages)[-4000:]
    recent_moves = [{"role": m.role, "text": m.text} for m in messages]

    store = DecisionStore(uri=uri, token=token)
    precedent = store.find_precedent(query_text=query_text, limit=top_k) if query_text else []

    return {
        "project": project,
        "session_file": str(session_path),
        "recent_moves": recent_moves,
        "precedent": precedent,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "session_path",
        type=Path,
        nargs="?",
        default=None,
        help="Path to a session .jsonl file (omit to auto-find the current session)",
    )
    parser.add_argument("--provider", default="claude", choices=["claude", "gemini", "codex"])
    parser.add_argument("--top-k", type=int, default=5, help="Max precedent matches")
    parser.add_argument("--recent", type=int, default=20, help="How many recent messages to consider")
    parser.add_argument("--uri", default=DEFAULT_URI, help="quack:// URI of the central store (default: %(default)s)")
    parser.add_argument("--token", default=DEFAULT_TOKEN, help="Auth token for the store")
    args = parser.parse_args()

    result = check_session(args.provider, args.session_path, args.top_k, args.recent, args.uri, args.token)
    print(json.dumps(result, indent=2, default=str, ensure_ascii=False))
