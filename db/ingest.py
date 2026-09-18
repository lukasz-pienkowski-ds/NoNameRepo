#!/usr/bin/env python3
"""Tag and embed a JSONL file of documents, then upsert them into DuckDB.

Each input line must be a JSON object with at least a "text" field. "id" and
"source" are optional (an id is derived from the file name + line number if
missing).

TODO(real-model): mock_tag/mock_embed in common/embeddings.py are placeholders.
Swap them for a real tagging/embedding model without changing this script.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from common.embeddings import mock_embed, mock_tag  # noqa: E402
from db.init_db import DEFAULT_DB_PATH, init_db  # noqa: E402


def ingest_file(jsonl_path: Path, db_path: Path = DEFAULT_DB_PATH) -> int:
    con = init_db(db_path)
    count = 0
    with jsonl_path.open() as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            text = record["text"]
            doc_id = record.get("id", f"{jsonl_path.stem}-{lineno}")
            source = record.get("source", jsonl_path.name)
            metadata = {k: v for k, v in record.items() if k not in {"id", "text", "source"}}

            tags = mock_tag(text)
            embedding = mock_embed(text)

            con.execute(
                """
                INSERT INTO documents (id, source_file, text, tags, metadata, embedding)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT (id) DO UPDATE SET
                    source_file = excluded.source_file,
                    text = excluded.text,
                    tags = excluded.tags,
                    metadata = excluded.metadata,
                    embedding = excluded.embedding,
                    ingested_at = now()
                """,
                [doc_id, source, text, tags, json.dumps(metadata), embedding],
            )
            count += 1
    return count


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("jsonl_path", type=Path, help="Path to the input JSONL file")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="Path to the DuckDB file")
    args = parser.parse_args()

    n = ingest_file(args.jsonl_path, args.db)
    print(f"Tagged and ingested {n} document(s) from {args.jsonl_path} into {args.db}")
