#!/usr/bin/env python3
"""Join model-assigned labels onto extracted messages and append them to the catalog.

Reads the labels as a JSON array of {uuid, domain, tags}, validates every label
against references/taxonomy.md, and appends one record per message to
~/.claude/labeled/<escaped-project>/<session-id>.jsonl.

Message text is copied verbatim from the extraction, never from the labels.
"""

import argparse
import json
import re
import sys
from pathlib import Path

TAXONOMY = Path(__file__).resolve().parent.parent / "references" / "taxonomy.md"
MAX_TAGS = 4


def load_vocabulary(path: Path) -> tuple[set[str], set[str]]:
    """Domains are the bulleted list; tags are the backticked names under ## Tags."""
    text = path.read_text()
    domains, tags = set(), set()
    section = None
    for line in text.splitlines():
        if line.startswith("## "):
            heading = line[3:].lower()
            section = "domains" if heading.startswith("domains") else (
                "tags" if heading.startswith("tags") else None
            )
            continue
        if section == "domains":
            match = re.match(r"^- `([a-z0-9-]+)`", line)
            if match:
                domains.add(match.group(1))
        elif section == "tags":
            tags.update(re.findall(r"`([a-z0-9-]+)`", line))
    if not domains or not tags:
        sys.exit(f"Could not parse the vocabulary from {path}")
    return domains, tags


def validate(label: dict, domains: set[str], tags: set[str]) -> list[str]:
    errors = []
    domain = label.get("domain")
    if domain is not None and domain not in domains:
        errors.append(f"unknown domain {domain!r}")

    label_tags = label.get("tags", [])
    if not isinstance(label_tags, list):
        errors.append("tags must be a list")
        return errors
    if len(label_tags) > MAX_TAGS:
        errors.append(f"{len(label_tags)} tags, max is {MAX_TAGS}")
    for tag in label_tags:
        if tag.startswith("new:"):
            continue
        if tag not in tags:
            errors.append(f"unknown tag {tag!r}")

    if domain is None and label_tags:
        errors.append("tags given without a domain")
    if domain is not None and not label_tags:
        errors.append("domain given without tags")
    return errors


def existing_uuids(catalog: Path) -> set[str]:
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("labels", nargs="?", type=Path, help="JSON file; omit to read stdin")
    parser.add_argument("--messages", type=Path, required=True, help="messages.json from extract")
    parser.add_argument("--catalog", type=Path, help="Override the catalog path")
    args = parser.parse_args()

    raw = args.labels.read_text() if args.labels else sys.stdin.read()
    try:
        labels = json.loads(raw)
    except json.JSONDecodeError as exc:
        sys.exit(f"Labels are not valid JSON: {exc}")
    if not isinstance(labels, list):
        sys.exit("Labels must be a JSON array of {uuid, domain, tags}")

    payload = json.loads(args.messages.read_text())
    messages = {m["uuid"]: m for m in payload["messages"]}
    catalog = args.catalog or Path(payload["catalog"])

    domains, tags = load_vocabulary(TAXONOMY)
    already = existing_uuids(catalog)

    records, problems, skipped = [], [], 0
    attempted = set()
    for label in labels:
        uuid = label.get("uuid")
        attempted.add(uuid)
        if uuid not in messages:
            problems.append(f"{uuid}: not in the extracted messages")
            continue
        if uuid in already:
            skipped += 1
            continue
        errors = validate(label, domains, tags)
        if errors:
            problems.append(f"{uuid}: " + "; ".join(errors))
            continue
        message = messages[uuid]
        records.append(
            {
                "uuid": uuid,
                "username": message["username"],
                "role": message["role"],
                "domain": label.get("domain"),
                "tags": label.get("tags", []),
                "message": message["message"],
            }
        )
        already.add(uuid)

    if problems:
        print("Rejected:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)

    missing = set(messages) - attempted - already
    if missing:
        print(f"No label supplied for {len(missing)} message(s)", file=sys.stderr)

    if records:
        catalog.parent.mkdir(parents=True, exist_ok=True)
        with catalog.open("a") as f:
            for record in records:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"Wrote {len(records)} record(s) to {catalog}")
    if skipped:
        print(f"Skipped {skipped} already-labeled message(s)")
    if problems:
        sys.exit(1)


if __name__ == "__main__":
    main()
