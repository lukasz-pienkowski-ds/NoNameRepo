"""Closed tag vocabulary, shared by the skill and the central store.

This list is a team contract, frozen before the hackathon starts. It exists
because free-form tags drift -- one person writes "kolejki", another
"messaging", a third "queue" -- and then the hard `tags && [...]` filter
returns nothing. The skill picks from this list; the store validates against
it and refuses anything else, so drift is caught at write time rather than
discovered when a query comes back empty.

Adding a tag is a team decision, not a local one.
"""

TAGS: tuple[str, ...] = (
    "persystencja",
    "kolejki-i-zdarzenia",
    "skalowanie",
    "wydajnosc",
    "autoryzacja",
    "integracja-zewnetrzna",
    "migracja-danych",
    "cache",
    "obserwowalnosc",
    "testowanie",
    "ci-cd",
    "architektura-uslug",
    "format-danych",
    "wybor-biblioteki",
    "bezpieczenstwo",
)

SENIORITY_LEVELS: tuple[str, ...] = ("junior", "mid", "senior")
DECISION_TYPES: tuple[str, ...] = ("decision", "assumption", "solution")
STATUSES: tuple[str, ...] = ("unknown", "confirmed", "rejected")


def unknown_tags(tags: list[str]) -> list[str]:
    """Return the tags that are not in the frozen vocabulary."""
    return sorted(set(tags) - set(TAGS))
