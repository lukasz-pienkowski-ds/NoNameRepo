"""
Mock embedding + tagging helpers.

TODO(real-model): replace `mock_embed` with a call to a real embedding model
(e.g. an Anthropic/OpenAI embeddings endpoint or a local sentence-transformers
model) and `mock_tag` with an LLM-based tagger. The interfaces (text in,
fixed-length float vector / list[str] out) are designed to stay the same so
callers in db.py, ingest.py and query.py don't need to change.
"""

import hashlib
import math
import re

EMBEDDING_DIM = 16

_KEYWORD_TAGS = {
    "duckdb": "database",
    "sql": "database",
    "docker": "infra",
    "compose": "infra",
    "container": "infra",
    "claude": "ai",
    "skill": "ai",
    "embedding": "ml",
    "vector": "ml",
    "retrieval": "ml",
    "generation": "ml",
    "model": "ml",
}


def mock_embed(text: str, dim: int = EMBEDDING_DIM) -> list[float]:
    """Deterministic pseudo-embedding derived from token hashes.

    Not semantically meaningful — it exists so the ingestion/query pipeline
    and DuckDB vector-similarity SQL can be wired up and tested end to end
    before a real embedding model is plugged in.
    """
    vec = [0.0] * dim
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    if not tokens:
        tokens = [""]
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        for i in range(dim):
            vec[i] += digest[i % len(digest)] / 255.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def mock_tag(text: str) -> list[str]:
    """Naive keyword-based tagger, standing in for an LLM/classifier tagger."""
    lower = text.lower()
    tags = {tag for keyword, tag in _KEYWORD_TAGS.items() if keyword in lower}
    return sorted(tags) or ["untagged"]
