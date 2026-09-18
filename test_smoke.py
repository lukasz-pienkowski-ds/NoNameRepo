#!/usr/bin/env python3
"""Runnable checks for the parts that do not need a live server.

    python test_smoke.py

No test framework on purpose -- the project has no test dependency and this
has to run inside the same image as everything else. Exit code is the result.

Session fixtures are written in each CLI's real on-disk shape, taken from
actual files: claude puts one message per line with a uuid and splits content
between a block list and a bare string; gemini keeps the session id on a header
record and repeats messages inside "$set" snapshots.
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import sessions  # noqa: E402
from common.marker import MarkerError, find_blocks, parse  # noqa: E402

PASS, FAIL = [], []


def check(name: str, got, want) -> None:
    (PASS if got == want else FAIL).append(name)
    print(f"  {'OK  ' if got == want else 'FAIL'} {name}" + ("" if got == want else f"  ({got!r} != {want!r})"))


def marker(decision="wybrano X", tech=None, biz=None, rationale="bo Y", tags=None, **extra):
    body = {
        "decision": decision,
        "assumptions": {"technical": tech or ["java 17"], "business": biz or ["SLA 99.9"]},
        "rationale": rationale,
        "tags": tags if tags is not None else ["skalowanie"],
        **extra,
    }
    return "<decision_log>" + json.dumps(body, ensure_ascii=False) + "</decision_log>"


def test_marker_contract():
    print("\n[kontrakt znacznika]")
    fields = parse(find_blocks("tekst " + marker() + " dalej")[0])
    check("decyzja wyciagnieta", fields["decision_summary"], "wybrano X")
    check("zalozenia techniczne", fields["assumptions_tech"], ["java 17"])
    check("zalozenia biznesowe", fields["assumptions_biz"], ["SLA 99.9"])
    check("uzasadnienie", fields["rationale"], "bo Y")

    rejected = parse(find_blocks(marker(rejected=[{"option": "kolejka", "because": "za wolna"}]))[0])
    check("odrzucone opcje", rejected["rejected_options"], ["kolejka — za wolna"])

    for missing in ("decision", "assumptions", "rationale"):
        body = json.loads(find_blocks(marker())[0])
        del body[missing]
        payload = json.dumps(body)
        try:
            parse(payload)
            check(f"brak '{missing}' odrzucony", "przeszlo", "MarkerError")
        except MarkerError as exc:
            check(f"brak '{missing}' odrzucony", missing in str(exc), True)

    try:
        parse("{nie json")
        check("zly JSON odrzucony", "przeszlo", "MarkerError")
    except MarkerError:
        check("zly JSON odrzucony", True, True)

    flat = parse(find_blocks(marker())[0].replace(
        '"assumptions": {"technical": ["java 17"], "business": ["SLA 99.9"]}',
        '"assumptions": ["plaska lista"]'))
    check("plaska lista zalozen przyjeta", flat["assumptions_tech"], ["plaska lista"])

    check("dwa znaczniki w wiadomosci", len(find_blocks(marker() + " i " + marker("druga"))), 2)
    check("brak znacznika", find_blocks("zwykly tekst"), [])


def write_fixtures(root: Path):
    """Two sessions per CLI, in the exact on-disk shapes observed."""
    claude = root / "claude" / "projects" / "-Users-x-proj"
    claude.mkdir(parents=True)
    with (claude / "sess-a.jsonl").open("w") as fh:
        # content as a block list (how claude stores assistant messages)
        fh.write(json.dumps({"uuid": "u-1", "sessionId": "s-1", "type": "assistant",
                             "message": {"content": [{"type": "text", "text": "przed " + marker("decyzja claude")}]}}) + "\n")
        # content as a bare string (58 of 141 real user messages look like this)
        fh.write(json.dumps({"uuid": "u-2", "sessionId": "s-1", "type": "user",
                             "message": {"content": "goly string " + marker("decyzja ze stringa", tags=["cache"])}}) + "\n")
        # sidechain and tool_result must not contribute
        fh.write(json.dumps({"uuid": "u-3", "sessionId": "s-1", "type": "assistant", "isSidechain": True,
                             "message": {"content": [{"type": "text", "text": marker("z sidechaina")}]}}) + "\n")
        fh.write(json.dumps({"uuid": "u-4", "sessionId": "s-1", "type": "user",
                             "message": {"content": [{"type": "tool_result", "text": marker("z tool_result")}]}}) + "\n")

    gem = root / "gemini" / "tmp" / "projekt-g" / "chats"
    gem.mkdir(parents=True)
    with (gem / "session-x.jsonl").open("w") as fh:
        fh.write(json.dumps({"sessionId": "g-1", "projectHash": "h", "kind": "main"}) + "\n")
        fh.write(json.dumps({"id": "m-1", "type": "gemini", "timestamp": "t",
                             "content": "gemini pisze stringiem " + marker("decyzja gemini", tags=["wydajnosc"])}) + "\n")
        # the same message repeated inside a $set snapshot: must dedupe, not double
        fh.write(json.dumps({"$set": {"messages": [
            {"id": "m-1", "type": "gemini", "content": "gemini pisze stringiem " + marker("decyzja gemini", tags=["wydajnosc"])},
            {"id": "m-2", "type": "user", "content": [{"text": "user tablica " + marker("decyzja usera g", tags=["testowanie"])}]},
        ]}}) + "\n")
    return claude, gem


def test_sessions(root: Path):
    print("\n[uniwersalny odczyt sesji]")
    write_fixtures(root)
    sessions.PROVIDERS["claude"]["roots"] = lambda: [root / "claude" / "projects"]
    sessions.PROVIDERS["gemini"]["roots"] = lambda: [root / "gemini" / "tmp"]
    sessions.PROVIDERS["codex"]["roots"] = lambda: [root / "codex" / "nie-ma"]

    check("wykrywanie providerow", sessions.detect(), {"claude": 1, "gemini": 1, "codex": 0})

    msgs = list(sessions.iter_messages(["claude"]))
    texts = [m.text for m in msgs]
    check("claude: blok tekstowy", any("decyzja claude" in t for t in texts), True)
    check("claude: goly string", any("decyzja ze stringa" in t for t in texts), True)
    check("claude: sidechain pominiety", any("z sidechaina" in t for t in texts), False)
    check("claude: tool_result pominiety", any("z tool_result" in t for t in texts), False)

    gmsgs = list(sessions.iter_messages(["gemini"]))
    check("gemini: sessionId z naglowka", {m.session_id for m in gmsgs}, {"g-1"})
    check("gemini: projekt ze sciezki", {m.project for m in gmsgs}, {"projekt-g"})
    check("gemini: rola zmapowana", {m.role for m in gmsgs}, {"user", "assistant"})

    check("id sa namespace'owane", all(":" in m.decision_id for m in msgs + gmsgs), True)
    check("brak kolizji miedzy CLI",
          len({m.decision_id for m in msgs + gmsgs}), len({(m.provider, m.message_id) for m in msgs + gmsgs}))


def test_extract(root: Path):
    print("\n[ekstrakcja end-to-end, bez serwera]")
    from db.extract import collect

    records, problems = collect(["claude", "gemini"], "tester", "senior")
    summaries = sorted(r["decision_summary"] for r in records)
    check("zebrane decyzje", summaries,
          ["decyzja claude", "decyzja gemini", "decyzja usera g", "decyzja ze stringa"])
    check("bez duplikatu z $set", len(records), len({r["id"] for r in records}))
    check("provider zapisany", sorted({r["provider"] for r in records}), ["claude", "gemini"])
    check("kazdy rekord ma zalozenia", all(r["assumptions_tech"] or r["assumptions_biz"] for r in records), True)
    check("kazdy rekord ma id", all(r["id"] for r in records), True)
    check("bez problemow", problems, [])

    # a marker with a tag outside the vocabulary must be reported, not stored
    bad = root / "claude" / "projects" / "-Users-x-proj" / "sess-bad.jsonl"
    bad.write_text(json.dumps({"uuid": "u-9", "sessionId": "s-9", "type": "assistant",
                               "message": {"content": [{"type": "text", "text": marker("zly tag", tags=["messaging"])}]}}) + "\n")
    records2, problems2 = collect(["claude"], "tester", "senior")
    check("zly tag odrzucony", any("messaging" in p for p in problems2), True)
    check("zly tag nie trafil do rekordow", any(r["decision_summary"] == "zly tag" for r in records2), False)


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        test_marker_contract()
        test_sessions(root)
        test_extract(root)
    print(f"\nWYNIK: {len(PASS)} przeszlo, {len(FAIL)} bledow")
    if FAIL:
        print("  niepowodzenia: " + ", ".join(FAIL))
    raise SystemExit(1 if FAIL else 0)
