"""Server-side context-store operations: ingest, similarity query, project lookup.

Plain functions over a DuckDB connection, used by db/server.py. Kept separate
from the HTTP layer so the actual logic has no network/framework code in it.
"""

import json
from collections import defaultdict

from common.embeddings import mock_embed, mock_tag


def ingest_lines(con, lines, default_source: str = "api") -> int:
    count = 0
    for lineno, line in enumerate(lines, start=1):
        line = line.strip()
        if not line:
            continue
        record = json.loads(line)
        text = record["text"]
        doc_id = record.get("id", f"{default_source}-{lineno}")
        source = record.get("source", default_source)
        domain = record.get("domain")
        model_name = record.get("model")
        metadata = {
            k: v
            for k, v in record.items()
            if k not in {"id", "text", "source", "domain", "model"}
        }

        tags = mock_tag(text)
        embedding = mock_embed(text)

        con.execute(
            """
            INSERT INTO documents
                (id, source_file, text, tags, domain, model_name, metadata, embedding)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (id) DO UPDATE SET
                source_file = excluded.source_file,
                text = excluded.text,
                tags = excluded.tags,
                domain = excluded.domain,
                model_name = excluded.model_name,
                metadata = excluded.metadata,
                embedding = excluded.embedding,
                ingested_at = now()
            """,
            [doc_id, source, text, tags, domain, model_name, json.dumps(metadata), embedding],
        )
        count += 1
    return count


def query_similar(con, text: str, top_k: int = 5) -> list[dict]:
    embedding = mock_embed(text)
    rows = con.execute(
        """
        SELECT id, text, tags, domain, model_name, metadata,
               array_cosine_similarity(embedding, ?::FLOAT[16]) AS score
        FROM documents
        ORDER BY score DESC
        LIMIT ?
        """,
        [embedding, top_k],
    ).fetchall()
    cols = [d[0] for d in con.description]
    return [dict(zip(cols, r)) for r in rows]


def _context_rows(con, domain, model_name, tags, query_text):
    sql = "SELECT id, text, tags, model_name, metadata FROM documents WHERE domain = ?"
    params = [domain]
    if model_name:
        sql += " AND model_name = ?"
        params.append(model_name)
    if tags:
        sql += " AND list_has_any(tags, ?)"
        params.append(tags)
    if query_text:
        sql += " ORDER BY array_cosine_similarity(embedding, ?::FLOAT[16]) DESC"
        params.append(mock_embed(query_text))
    else:
        sql += " ORDER BY ingested_at DESC"
    rows = con.execute(sql, params).fetchall()
    cols = [d[0] for d in con.description]
    return [dict(zip(cols, r)) for r in rows]


def get_project_context(
    con, domain: str, model_name: str | None = None, tags: list[str] | None = None, query_text: str | None = None
) -> dict:
    docs = _context_rows(con, domain, model_name, tags, query_text)
    used_model_fallback = False
    if model_name and not docs:
        docs = _context_rows(con, domain, None, tags, query_text)
        used_model_fallback = True

    topics = defaultdict(list)
    for d in docs:
        for tag in d.get("tags") or ["untagged"]:
            topics[tag].append(d["id"])

    return {
        "domain": domain,
        "requested_model": model_name,
        "used_model_fallback": used_model_fallback,
        "count": len(docs),
        "topics": dict(topics),
        "documents": docs,
    }
