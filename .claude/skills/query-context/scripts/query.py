#!/usr/bin/env python3
"""Retrieve the top-k most similar documents from the DuckDB context store.

TODO(real-model): mock_embed in common/embeddings.py is a placeholder — the
query embedding here must use the same embedding function as ingestion.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from common.embeddings import mock_embed  # noqa: E402
from db.init_db import DEFAULT_DB_PATH, init_db  # noqa: E402


def query(text: str, top_k: int = 5, db_path: Path = DEFAULT_DB_PATH) -> list[dict]:
    con = init_db(db_path)
    embedding = mock_embed(text)

    rows = con.execute(
        """
        SELECT id, text, tags, metadata,
               array_cosine_similarity(embedding, ?::FLOAT[16]) AS score
        FROM documents
        ORDER BY score DESC
        LIMIT ?
        """,
        [embedding, top_k],
    ).fetchall()

    return [
        {"id": r[0], "text": r[1], "tags": r[2], "metadata": r[3], "score": r[4]}
        for r in rows
    ]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query_text", help="Text to find similar context documents for")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    args = parser.parse_args()

    results = query(args.query_text, args.top_k, args.db)
    print(json.dumps(results, indent=2, default=str))
