#!/usr/bin/env python3
"""Client library for the central decision store.

Everything that is not the server itself goes through here: the skill on a
developer machine, the embedding worker, the seeding script. Clients never
open the database file -- the server process holds an exclusive lock on it.

quack_query takes the remote statement as a *string*, so inner values cannot
be bound as parameters and have to be inlined. sql_literal() below does the
quoting; nothing in this module should build SQL any other way.
"""

import os
import sys
from datetime import date, datetime
from pathlib import Path

import duckdb

DEFAULT_URI = os.environ.get("QUACK_URI", "quack://127.0.0.1:8888")
DEFAULT_TOKEN = os.environ.get("QUACK_TOKEN", "")

_COLUMNS = (
    "id",
    "created_at",
    "developer_id",
    "provider",
    "seniority_level",
    "project",
    "session_uuid",
    "decision_type",
    "decision_summary",
    "assumptions_tech",
    "assumptions_biz",
    "rationale",
    "rejected_options",
    "tags",
    "status",
)


def sql_literal(value) -> str:
    """Render a Python value as a DuckDB SQL literal.

    Strings are single-quoted with embedded quotes doubled, which is DuckDB's
    escaping rule. Lists become array literals, so a list of tags round-trips
    into VARCHAR[] unchanged.
    """
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(sql_literal(v) for v in value) + "]"
    if isinstance(value, (date, datetime)):
        return "'" + value.isoformat() + "'"
    return "'" + str(value).replace("'", "''") + "'"


def _embed(text: str) -> list[float]:
    """Embed a query with the same function used at ingestion.

    Imported lazily so this module stays usable as pure transport. Note the
    consequence for later: query and stored vectors must come from the same
    model, so once mock_embed is replaced by a real one, whatever calls this
    needs access to that model too. With a model that only runs on the central
    host, semantic search from a laptop needs a different answer -- tag-only
    retrieval, or a query endpoint on the server.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from common.embeddings import mock_embed

    return mock_embed(text)


class DecisionStore:
    """A connection to the central store over quack."""

    def __init__(self, uri: str = DEFAULT_URI, token: str = DEFAULT_TOKEN):
        self.uri = uri
        self.token = token
        self._con = duckdb.connect()
        self._con.execute("INSTALL quack")
        self._con.execute("LOAD quack")

    def sql(self, statement: str) -> list[tuple]:
        """Run a statement on the central server and return its rows."""
        return self._con.execute(
            "SELECT * FROM quack_query(?, ?, token := ?, disable_ssl := true)",
            [self.uri, statement, self.token],
        ).fetchall()

    # -- writing ---------------------------------------------------------

    def insert_decisions(self, records: list[dict]) -> int:
        """Upsert decision records. Returns how many were sent.

        `id` must be the uuid of the source message, so re-running the
        extractor over the same session file is a no-op rather than a source
        of duplicates. Missing ids are rejected here rather than silently
        filled in, because a generated id would defeat exactly that.
        """
        if not records:
            return 0

        # Deduplicate by id, last wins. DuckDB does not reject the same key
        # twice in one INSERT ... ON CONFLICT -- it silently keeps the first
        # and drops the rest, so a later, more complete version of a record
        # would vanish without a word. Gemini hits this routinely: its "$set"
        # snapshots repeat messages that also appear as their own records.
        deduped = {record.get("id"): record for record in records}
        records = list(deduped.values())

        rows = []
        for record in records:
            if not record.get("id"):
                raise ValueError(
                    "record has no id; use the uuid of the source message, "
                    "not a generated one (see schema.sql)"
                )
            rows.append(
                "("
                + ", ".join(
                    sql_literal(record.get(column))
                    for column in _COLUMNS
                    if column != "created_at"
                )
                + ")"
            )

        columns = ", ".join(c for c in _COLUMNS if c != "created_at")
        updates = [f"{c} = excluded.{c}" for c in _COLUMNS if c not in {"id", "created_at"}]
        # An unchanged row keeps its vector, so re-running the extractor does not
        # make the worker redo everything. A changed summary drops it back to
        # NULL, which re-queues the row rather than leaving a vector that
        # describes text no longer in the record.
        updates.append(
            "embedding = CASE"
            " WHEN decisions.decision_summary IS DISTINCT FROM excluded.decision_summary"
            " THEN NULL ELSE decisions.embedding END"
        )
        updates = ", ".join(updates)
        self.sql(
            f"INSERT INTO decisions ({columns}) VALUES {', '.join(rows)} "
            f"ON CONFLICT (id) DO UPDATE SET {updates}"
        )
        return len(rows)

    def set_status(self, decision_id: str, status: str) -> None:
        """Close the loop after code review."""
        self.sql(
            f"UPDATE decisions SET status = {sql_literal(status)} "
            f"WHERE id = {sql_literal(decision_id)}"
        )

    # -- reading ---------------------------------------------------------

    def find_precedent(
        self,
        query_text: str | None = None,
        tags: list[str] | None = None,
        limit: int = 3,
        exclude_developer: str | None = None,
        min_tag_overlap: int = 1,
        min_similarity: float = 0.0,
    ) -> list[dict]:
        """Find decisions taken in a comparable situation.

        Tags filter, similarity ranks. Hard constraints are not something to
        score: an imposed stack or a tag that does not apply rules a precedent
        out, it does not merely make it less likely. What is left is then
        ordered by how close the situation actually is.

        Ranking uses array_cosine_similarity(), a core DuckDB function -- no
        extension, no index. At this corpus size a full scan beats maintaining
        an HNSW index, and rows still waiting for the embedding worker simply
        score 0 rather than disappearing.

        `min_similarity` defaults to 0 on purpose: with the placeholder
        embeddings it cannot separate anything, so the tag filter is what does
        the cutting. It becomes useful when a real model replaces mock_embed.

        Returning nothing is a valid answer, and the common one early on.
        Mid-work a wrong precedent does more damage than a missing one, because
        the agent presents it in the register of "the team already solved this".
        """
        overlap = f"len(list_intersect(tags, {sql_literal(list(tags))}))" if tags else "0"

        if query_text:
            vector = _embed(query_text)
            similarity = (
                f"coalesce(array_cosine_similarity("
                f"embedding, {sql_literal(vector)}::FLOAT[{len(vector)}]), 0.0)"
            )
        else:
            similarity = "0.0"

        where = []
        if tags:
            # The threshold goes in WHERE, not QUALIFY: QUALIFY needs a window
            # function, and this is a plain scalar expression.
            where.append(f"{overlap} >= {int(min_tag_overlap)}")
        if exclude_developer:
            where.append(f"developer_id IS DISTINCT FROM {sql_literal(exclude_developer)}")
        if query_text and min_similarity > 0:
            where.append(f"{similarity} >= {float(min_similarity)}")
        clause = f"WHERE {' AND '.join(where)}" if where else ""

        rows = self.sql(
            f"""
            SELECT {', '.join(_COLUMNS)},
                   {overlap} AS tag_overlap,
                   {similarity} AS similarity
            FROM decisions
            {clause}
            ORDER BY
                -- Tags lead, similarity breaks ties. Deliberately this way
                -- round: with mock_embed every vector points roughly the same
                -- direction, so cosine lands in a ~0.95-0.98 band for any pair
                -- of texts -- measured, and in that band an unrelated sentence
                -- can outscore a related one. Tag overlap is the signal that
                -- actually carries information today. Flip these two lines
                -- once a real embedding model is in.
                tag_overlap DESC,
                similarity DESC,
                CASE seniority_level WHEN 'senior' THEN 0 WHEN 'mid' THEN 1 ELSE 2 END,
                CASE status WHEN 'confirmed' THEN 0 WHEN 'unknown' THEN 1 ELSE 2 END,
                created_at DESC
            LIMIT {int(limit)}
            """
        )
        return [dict(zip((*_COLUMNS, "tag_overlap", "similarity"), row)) for row in rows]

    def count(self) -> int:
        return self.sql("SELECT count(*) FROM decisions")[0][0]

    def pending_embeddings(self, limit: int = 50) -> list[tuple[str, str]]:
        """Rows still waiting for a vector. NULL embedding *is* the queue."""
        return self.sql(
            "SELECT id, decision_summary FROM decisions "
            f"WHERE embedding IS NULL ORDER BY created_at LIMIT {int(limit)}"
        )

    def set_embedding(self, decision_id: str, vector: list[float], dim: int) -> None:
        self.sql(
            f"UPDATE decisions SET embedding = {sql_literal(vector)}::FLOAT[{int(dim)}] "
            f"WHERE id = {sql_literal(decision_id)}"
        )
