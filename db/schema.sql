-- Context store schema.
--
-- `embedding` is a fixed-size FLOAT array so DuckDB's built-in
-- array_cosine_similarity() can be used for retrieval without needing the
-- VSS extension. If the corpus grows large enough to need an ANN index,
-- `INSTALL vss; LOAD vss;` and add an HNSW index on this column.

CREATE TABLE IF NOT EXISTS documents (
    id           VARCHAR PRIMARY KEY,
    source_file  VARCHAR,
    text         VARCHAR NOT NULL,
    tags         VARCHAR[],
    metadata     JSON,
    embedding    FLOAT[16],
    ingested_at  TIMESTAMP DEFAULT current_timestamp
);
