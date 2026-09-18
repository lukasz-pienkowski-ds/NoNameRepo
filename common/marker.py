#!/usr/bin/env python3
"""The <decision_log> marker: its contract, and parsing it out of a message.

A marker must carry three things. This is not a formatting preference -- each
one answers a question the next person will have, and the record is worthless
without it:

  1. decision    -- what was decided
  2. assumptions -- technical AND business, the ones the decision rests on;
                    without them nobody can judge whether it transfers
  3. rationale   -- why this option, and why the others were rejected;
                    the code already shows what was done, never what was not

`parse()` enforces all three. An incomplete marker is reported, not quietly
stored: a precedent missing its assumptions is the kind that gets applied where
it does not belong.

Known limitation: anything that *talks about* markers contains one. Docs, the
skill file and chat messages explaining the format all get picked up by the
extractor. There is no reliable way to tell an example from the real thing, so
the rule is a convention: examples leave one required field empty.
"""

import json
import re

OPEN, CLOSE = "<decision_log>", "</decision_log>"
_BLOCK = re.compile(re.escape(OPEN) + r"\s*(.*?)\s*" + re.escape(CLOSE), re.DOTALL)

REQUIRED = ("decision", "assumptions", "rationale")

# Note the empty "rationale". That is deliberate: this template lives in a file
# that agents read, so a complete example here would be a valid marker sitting
# in someone's session, and the extractor would ingest the documentation as if
# it were a decision. This has already happened once, with an example quoted in
# a chat. Any marker shown in docs, skills or chat must leave one required field
# empty so it cannot parse.
TEMPLATE = """<decision_log>
{
  "decision": "what was decided, in one sentence",
  "assumptions": {
    "technical": ["imposed stack, scale, what the system already does"],
    "business": ["deadline, SLA, budget, regulatory constraint"]
  },
  "rationale": "",
  "rejected": [{"option": "the other way", "because": "why not"}],
  "tags": ["from tags.py, the closed vocabulary"],
  "type": "decision"
}
</decision_log>"""


class MarkerError(ValueError):
    """A marker was found but cannot be turned into a record."""


def find_blocks(text: str) -> list[str]:
    """Raw marker payloads in a message, in order. Cheap enough to run on every
    message; the SQL pre-filter is just `LIKE '%<decision_log>%'`."""
    return _BLOCK.findall(text) if OPEN in text else []


def _as_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    return [str(v).strip() for v in value if str(v).strip()]


def parse(payload: str) -> dict:
    """Turn one marker payload into record fields, or explain what is missing."""
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise MarkerError(f"marker is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise MarkerError("marker must be a JSON object")

    missing = [k for k in REQUIRED if not data.get(k)]
    if missing:
        raise MarkerError(
            f"marker is missing {', '.join(missing)} "
            f"(all of {', '.join(REQUIRED)} are required)"
        )

    assumptions = data["assumptions"]
    if isinstance(assumptions, dict):
        tech = _as_list(assumptions.get("technical"))
        biz = _as_list(assumptions.get("business"))
    else:
        # A flat list is accepted rather than rejected: losing the split is
        # better than losing the assumptions. Both halves get the same content
        # so neither query comes back empty.
        tech = biz = _as_list(assumptions)
    if not tech and not biz:
        raise MarkerError("assumptions are present but empty")

    rejected = data.get("rejected") or []
    rejected_options = [
        f"{r.get('option', '?')} — {r.get('because', 'no reason given')}"
        if isinstance(r, dict) else str(r)
        for r in rejected
    ]

    return {
        "decision_summary": str(data["decision"]).strip(),
        "assumptions_tech": tech,
        "assumptions_biz": biz,
        "rationale": str(data["rationale"]).strip(),
        "rejected_options": rejected_options,
        "tags": _as_list(data.get("tags")),
        "decision_type": data.get("type") or "decision",
    }
