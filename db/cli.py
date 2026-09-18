#!/usr/bin/env python3
"""Command-line access to the central decision store.

Thin wrapper over client.py, for smoke-testing the server, seeding demo data
and closing the review loop by hand.

    python db/cli.py status
    python db/cli.py load data/seed/decisions.jsonl
    python db/cli.py find --tags skalowanie wydajnosc
    python db/cli.py confirm <decision-id>
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db.client import DEFAULT_TOKEN, DEFAULT_URI, DecisionStore  # noqa: E402
from common.tags import STATUSES, unknown_tags  # noqa: E402


def cmd_status(store: DecisionStore, args) -> int:
    rows = store.sql(
        "SELECT count(*), count(embedding), "
        "count(*) FILTER (WHERE status = 'confirmed') FROM decisions"
    )
    total, embedded, confirmed = rows[0]
    print(f"decisions: {total}")
    print(f"embedded:  {embedded} ({total - embedded} awaiting the worker)")
    print(f"confirmed: {confirmed}")
    return 0


def cmd_load(store: DecisionStore, args) -> int:
    records = []
    for lineno, line in enumerate(Path(args.jsonl_path).read_text().splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        record = json.loads(line)
        bad = unknown_tags(record.get("tags") or [])
        if bad:
            # Fail loudly rather than write a tag nothing will ever query for.
            raise SystemExit(f"{args.jsonl_path}:{lineno}: tags outside the vocabulary: {bad}")
        records.append(record)

    sent = store.insert_decisions(records)
    print(f"upserted {sent} decision(s) from {args.jsonl_path}")
    return 0


def cmd_find(store: DecisionStore, args) -> int:
    bad = unknown_tags(args.tags or [])
    if bad:
        raise SystemExit(f"tags outside the vocabulary: {bad}")

    hits = store.find_precedent(
        query_text=args.query,
        tags=args.tags,
        limit=args.limit,
        exclude_developer=args.exclude_developer,
        min_similarity=args.min_similarity,
    )
    if not hits:
        # Not an error. A wrong precedent mid-work is worse than none.
        print("no precedent above the threshold")
        return 0
    print(json.dumps(hits, indent=2, default=str, ensure_ascii=False))
    return 0


def cmd_confirm(store: DecisionStore, args) -> int:
    if args.status not in STATUSES:
        raise SystemExit(f"status must be one of {STATUSES}")
    store.set_status(args.decision_id, args.status)
    print(f"{args.decision_id} -> {args.status}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--uri", default=DEFAULT_URI, help="Central server (env: QUACK_URI)")
    parser.add_argument("--token", default=DEFAULT_TOKEN, help="Auth token (env: QUACK_TOKEN)")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="row counts on the central store").set_defaults(fn=cmd_status)

    p_load = sub.add_parser("load", help="upsert decision records from a JSONL file")
    p_load.add_argument("jsonl_path")
    p_load.set_defaults(fn=cmd_load)

    p_find = sub.add_parser("find", help="find precedents by tag and/or similarity")
    p_find.add_argument("--query", default=None, help="situation text; ranks by cosine similarity")
    p_find.add_argument("--tags", nargs="*", default=[])
    p_find.add_argument("--min-similarity", type=float, default=0.0)
    p_find.add_argument("--limit", type=int, default=3)
    p_find.add_argument("--exclude-developer", default=None)
    p_find.set_defaults(fn=cmd_find)

    p_confirm = sub.add_parser("confirm", help="set a decision's status after review")
    p_confirm.add_argument("decision_id")
    p_confirm.add_argument("--status", default="confirmed")
    p_confirm.set_defaults(fn=cmd_confirm)

    args = parser.parse_args()
    return args.fn(DecisionStore(args.uri, args.token), args)


if __name__ == "__main__":
    raise SystemExit(main())
