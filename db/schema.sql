-- Context store schema.
--
-- `embedding` is a fixed-size FLOAT array so DuckDB's built-in
-- array_cosine_similarity() can be used for retrieval without needing the
-- VSS extension. If the corpus grows large enough to need an ANN index,
-- `INSTALL vss; LOAD vss;` and add an HNSW index on this column.
--
-- ASSUMED SCHEMA (TODO real-schema): `domain` and `model_name` are
-- placeholder columns, guessed at ahead of the real ingestion schema that
-- will populate this table (from tagged/embedded Claude Code session
-- JSONL). Once that schema is delivered, this is the one place to adjust
-- column names/types — `project_context.py` and `ingest.py` both reference
-- them by name only, nothing else depends on their shape.

CREATE TABLE IF NOT EXISTS documents (
    id           VARCHAR PRIMARY KEY,
    source_file  VARCHAR,
    text         VARCHAR NOT NULL,
    tags         VARCHAR[],
    domain       VARCHAR,   -- ASSUMED: project/domain this document belongs to
    model_name   VARCHAR,   -- ASSUMED: model that produced the source session, if any
    metadata     JSON,
    embedding    FLOAT[16],
    ingested_at  TIMESTAMP DEFAULT current_timestamp
);
