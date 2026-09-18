#!/usr/bin/env python3
"""Scan agent sessions from any supported CLI and push decisions to the store.

    python db/extract.py --detect                 # what is on this machine
    python db/extract.py --dry-run                # parse, show, write nothing
    python db/extract.py --provider claude gemini # scan and upsert

Provider-neutral by construction: sessions.py normalises the differences, this
script only knows about markers. Adding a fourth CLI is one adapter, not a
change here.

Re-running is safe and expected -- sessions are append-only files that get read
in full every time, and the record key comes from the message, so an unchanged
decision upserts onto itself.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db.client import DEFAULT_TOKEN, DEFAULT_URI, DecisionStore  # noqa: E402
from common.marker import MarkerError, find_blocks, parse  # noqa: E402
from common.sessions import PROVIDERS, detect, iter_messages  # noqa: E402
from common.tags import unknown_tags  # noqa: E402


def collect(providers: list[str] | None, developer: str, seniority: str,
            root: Path | None = None) -> tuple[list[dict], list[str]]:
    # Keyed by id, not a list: the same message legitimately shows up more than
    # once in a scan (gemini repeats messages inside "$set" snapshots), and the
    # id is what makes re-reading a session harmless in the first place.
    records: dict[str, dict] = {}
    problems: list[str] = []

    for message in iter_messages(providers, root):
        for index, payload in enumerate(find_blocks(message.text)):
            where = f"{message.source_file.name} [{message.decision_id}]"
            try:
                fields = parse(payload)
            except MarkerError as exc:
                problems.append(f"{where}: {exc}")
                continue

            bad = unknown_tags(fields["tags"])
            if bad:
                problems.append(f"{where}: tags outside the vocabulary: {bad}")
                continue

            # Several markers in one message would collide on the message id
            # alone, so the block's position disambiguates them.
            decision_id = message.decision_id if index == 0 else f"{message.decision_id}#{index}"
            records[decision_id] = {
                "id": decision_id,
                "developer_id": developer,
                "provider": message.provider,
                "seniority_level": seniority,
                "project": message.project,
                "session_uuid": message.session_id,
                "status": "unknown",
                **fields,
            }
    return list(records.values()), problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--detect", action="store_true", help="list providers found on this machine and exit")
    parser.add_argument("--provider", nargs="*", default=None, choices=list(PROVIDERS))
    parser.add_argument("--root", type=Path, default=None,
                        help="read sessions from this directory instead of the CLI's own")
    parser.add_argument("--developer", default="unknown")
    parser.add_argument("--seniority", default="senior", choices=["junior", "mid", "senior"])
    parser.add_argument("--dry-run", action="store_true", help="parse and print, write nothing")
    parser.add_argument("--uri", default=DEFAULT_URI)
    parser.add_argument("--token", default=DEFAULT_TOKEN)
    args = parser.parse_args()

    if args.detect:
        for name, count in detect(args.root).items():
            mark = "" if PROVIDERS[name]["verified"] else "  [adapter unverified]"
            print(f"{name:8} {count:4} session file(s){mark}")
        return 0

    records, problems = collect(args.provider, args.developer, args.seniority, args.root)

    for problem in problems:
        # Loud, because a rejected marker is a decision that will not be there
        # when someone looks for it.
        print(f"skipped  {problem}", file=sys.stderr)

    if args.dry_run:
        print(json.dumps(records, indent=2, ensure_ascii=False))
        print(f"\n{len(records)} decision(s) parsed, {len(problems)} skipped (dry run)", file=sys.stderr)
        return 0

    if not records:
        print(f"no decisions found ({len(problems)} marker(s) skipped)")
        return 0

    sent = DecisionStore(args.uri, args.token).insert_decisions(records)
    by_provider: dict[str, int] = {}
    for record in records:
        by_provider[record["provider"]] = by_provider.get(record["provider"], 0) + 1
    print(f"upserted {sent} decision(s): " + ", ".join(f"{k}={v}" for k, v in sorted(by_provider.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
