#!/usr/bin/env python3
"""Checks that need a running decision store.

    make test-integration          # or: python test_integration.py

Skips with exit 0 when no store is reachable, so it is safe to run anywhere.
Pass --require to turn that skip into a failure, which is what CI wants.

Everything is written under its own project name and deleted afterwards, so
running this against a store holding real decisions does not disturb them. The
cleanup also runs when an assertion fails.
"""

import argparse
import os
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common.embeddings import EMBEDDING_DIM, mock_embed  # noqa: E402
from db.client import DEFAULT_TOKEN, DEFAULT_URI, DecisionStore  # noqa: E402

PROJECT = "__integration_test__"
PASS, FAIL = [], []


def check(name: str, got, want) -> None:
    (PASS if got == want else FAIL).append(name)
    print(f"  {'OK  ' if got == want else 'FAIL'} {name}" + ("" if got == want else f"  ({got!r} != {want!r})"))


def record(n: int, developer: str = "tester", **over) -> dict:
    base = {
        "id": f"{PROJECT}:{developer}:{n}",
        "developer_id": developer,
        "provider": "claude",
        "seniority_level": "senior",
        "project": PROJECT,
        "session_uuid": f"sess-{developer}",
        "decision_type": "decision",
        "decision_summary": f"decyzja {n} od {developer}",
        "assumptions_tech": ["java 17"],
        "assumptions_biz": ["SLA 99.9"],
        "rationale": "bo tak wyszlo",
        "rejected_options": ["inna opcja — za wolna"],
        "tags": ["testowanie"],
        "status": "unknown",
    }
    base.update(over)
    return base


def count(store: DecisionStore) -> int:
    return store.sql(f"SELECT count(*) FROM decisions WHERE project = '{PROJECT}'")[0][0]


def nulls(store: DecisionStore) -> int:
    return store.sql(
        f"SELECT count(*) FROM decisions WHERE project = '{PROJECT}' AND embedding IS NULL"
    )[0][0]


def cleanup(store: DecisionStore) -> None:
    store.sql(f"DELETE FROM decisions WHERE project = '{PROJECT}'")


def run(store: DecisionStore) -> None:
    cleanup(store)  # a previous crashed run must not poison this one

    print("\n[zapis i idempotencja]")
    store.insert_decisions([record(i) for i in range(3)])
    check("3 rekordy zapisane", count(store), 3)
    for _ in range(3):
        store.insert_decisions([record(i) for i in range(3)])
    check("idempotencja przy 4 przebiegach", count(store), 3)

    try:
        store.insert_decisions([{"decision_summary": "brak id"}])
        check("rekord bez id odrzucony", "przeszlo", "ValueError")
    except ValueError:
        check("rekord bez id odrzucony", True, True)

    # Two rows with one id in a single INSERT: DuckDB keeps the first and drops
    # the rest without an error, so the client must collapse them itself.
    store.insert_decisions([
        record(9, decision_summary="pierwsza wersja"),
        record(9, decision_summary="druga wersja"),
    ])
    got = store.sql(
        f"SELECT decision_summary FROM decisions WHERE id = '{PROJECT}:tester:9'")[0][0]
    check("duplikat id w jednym INSERT: wygrywa ostatni", got, "druga wersja")
    store.sql(f"DELETE FROM decisions WHERE id = '{PROJECT}:tester:9'")

    print("\n[embeddingi asynchroniczne]")
    check("nowe rekordy czekaja na wektor", nulls(store), 3)
    check("szukanie dziala przed wektorami",
          len(store.find_precedent(query_text="cokolwiek", tags=["testowanie"])) > 0, True)

    for decision_id, summary in store.pending_embeddings(50):
        store.set_embedding(decision_id, mock_embed(summary or ""), EMBEDDING_DIM)
    check("wektory policzone", nulls(store), 0)

    store.insert_decisions([record(i) for i in range(3)])
    check("reingest nie kasuje wektorow", nulls(store), 0)

    store.insert_decisions([record(0, decision_summary="TRESC ZMIENIONA")])
    check("zmiana tresci wraca do kolejki", nulls(store), 1)

    print("\n[wyszukiwanie]")
    hits = store.find_precedent(tags=["testowanie"], limit=10)
    check("filtr po tagu", len([h for h in hits if h["project"] == PROJECT]), 3)
    # Asking for more overlap than the query has tags cannot match anything, so
    # this stays empty whatever else the store holds. An earlier version picked
    # a tag it assumed nobody used, and broke the moment real data arrived.
    check("brak trafien to pusta lista",
          store.find_precedent(tags=["testowanie"], min_tag_overlap=2), [])
    check("prog similarity odcina",
          store.find_precedent(query_text="x", tags=["testowanie"], min_similarity=0.999), [])

    store.insert_decisions([record(7, developer="ktos-inny")])
    hits = store.find_precedent(tags=["testowanie"], exclude_developer="ktos-inny", limit=10)
    check("wykluczenie autora", any(h["developer_id"] == "ktos-inny" for h in hits), False)

    print("\n[wyszukiwanie pelnotekstowe BM25]")
    store.insert_decisions([
        record(20, decision_summary="Klucz idempotencji na zapisach przychodzacych",
               rationale="dostawca ponawia webhooki, wiec bez klucza dostawalismy duplikaty"),
        record(21, decision_summary="Partycjonowanie tabeli po miesiacu",
               rationale="kasowanie starych wierszy blokowalo zapisy na kilkanascie sekund"),
    ])
    store.rebuild_fts_index()

    hits = store.find_precedent(query_text="dostawca ponawia webhooki duplikaty",
                                tags=["testowanie"], limit=1)
    check("BM25 znajduje wlasciwy rekord",
          hits[0]["decision_summary"] if hits else None,
          "Klucz idempotencji na zapisach przychodzacych")
    check("BM25 dal niezerowy wynik", bool(hits and hits[0]["relevance"] > 0), True)

    hits = store.find_precedent(query_text="kasowanie starych wierszy blokowalo zapisy",
                                tags=["testowanie"], limit=1)
    check("BM25 rozroznia dwa podobne rekordy",
          hits[0]["decision_summary"] if hits else None,
          "Partycjonowanie tabeli po miesiacu")

    check("prog BM25 odcina bezsens",
          store.find_precedent(query_text="konfiguracja drukarki iglowej w kadrach",
                               tags=["testowanie"], min_relevance=0.5), [])

    # A record added after the last rebuild must be invisible to BM25: that is
    # what makes the worker's rebuild necessary rather than optional.
    store.insert_decisions([record(22, decision_summary="Zupelnie nowy wpis",
                                   rationale="telemetria satelitarna w kwantowym kompilatorze")])
    before = store.find_precedent(query_text="telemetria satelitarna kwantowym",
                                  tags=["testowanie"], min_relevance=0.1)
    store.rebuild_fts_index()
    after = store.find_precedent(query_text="telemetria satelitarna kwantowym",
                                 tags=["testowanie"], min_relevance=0.1)
    check("nowy rekord niewidoczny przed przebudowa", before, [])
    check("widoczny po przebudowie", len(after), 1)

    print("\n[petla zwrotna]")
    store.set_status(f"{PROJECT}:tester:1", "confirmed")
    got = store.sql(f"SELECT status FROM decisions WHERE id = '{PROJECT}:tester:1'")[0][0]
    check("status zmieniony po review", got, "confirmed")

    print("\n[rownoleglosc: 3 klientow x 10 zapisow]")
    # Each thread opens its own connection, the way three laptops would. The
    # point is the server: one process owns the file, so writes serialise.
    errors: list[Exception] = []

    def writer(developer: str) -> None:
        try:
            DecisionStore(store.uri, store.token).insert_decisions(
                [record(i, developer=developer) for i in range(10)])
        except Exception as exc:  # noqa: BLE001 - reported, not swallowed
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(f"dev{n}",)) for n in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    check("brak bledow zapisu", errors, [])
    written = store.sql(
        f"SELECT count(*) FROM decisions WHERE project = '{PROJECT}' "
        "AND developer_id LIKE 'dev%'")[0][0]
    check("30 zapisow doszlo", written, 30)
    per_dev = store.sql(
        f"SELECT count(DISTINCT developer_id) FROM decisions WHERE project = '{PROJECT}' "
        "AND developer_id LIKE 'dev%'")[0][0]
    check("po 10 na kazdego z 3", per_dev, 3)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--uri", default=DEFAULT_URI)
    parser.add_argument("--token", default=DEFAULT_TOKEN)
    parser.add_argument("--require", action="store_true",
                        help="fail instead of skipping when no store is reachable")
    args = parser.parse_args()

    try:
        store = DecisionStore(args.uri, args.token)
        store.count()
    except Exception as exc:  # noqa: BLE001
        first = str(exc).splitlines()[0]
        # A rejected token is a misconfiguration, not an absent store. Skipping
        # it quietly would hide a typo in QUACK_TOKEN behind a green run, so it
        # fails whether or not --require was passed.
        if "auth" in first.lower():
            print(f"BLAD: centrala na {args.uri} odrzucila token")
            print(f"  {first}")
            print("  sprawdz QUACK_TOKEN w .env")
            return 1
        print(f"POMINIETE: brak polaczenia z centrala na {args.uri}")
        print(f"  {first}")
        print("  uruchom `make store-up`, albo podaj --uri/--token")
        return 1 if args.require else 0

    print(f"centrala: {args.uri}")
    try:
        run(store)
    finally:
        cleanup(store)
        print(f"\nposprzatane: projekt {PROJECT} usuniety")

    print(f"WYNIK: {len(PASS)} przeszlo, {len(FAIL)} bledow")
    if FAIL:
        print("  niepowodzenia: " + ", ".join(FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
