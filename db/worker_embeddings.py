#!/usr/bin/env python3
"""Fill in missing embeddings on the central store, asynchronously.

Developer machines never compute vectors -- they have no model and should not
need one. An INSERT lands with embedding NULL and is immediately usable for
tag search. This worker picks those rows up afterwards.

Why not compute at write time: the insert would take as long as inference, and
a model that is down or slow would block writes, which means losing decisions.
Here the model can be unavailable for an hour and nothing breaks -- rows queue
up with NULL and tag search keeps working throughout.

`embedding IS NULL` is the queue. There is no task table, because a row
already states whether it has been processed.

TODO(real-model): mock_embed comes from common/embeddings.py, the project's
designated swap point. Replacing it with a real model also means changing
EMBEDDING_DIM there and the FLOAT[n] column in schema.sql, then re-computing
every existing vector -- fixed-size arrays cannot change width in place.
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db.client import DEFAULT_TOKEN, DEFAULT_URI, DecisionStore  # noqa: E402
from common.embeddings import EMBEDDING_DIM, mock_embed  # noqa: E402


def process_batch(store: DecisionStore, batch_size: int) -> int:
    pending = store.pending_embeddings(batch_size)
    for decision_id, summary in pending:
        store.set_embedding(decision_id, mock_embed(summary or ""), EMBEDDING_DIM)
    return len(pending)


def run(uri: str, token: str, batch_size: int, interval: float, once: bool) -> None:
    store = DecisionStore(uri, token)
    while True:
        done = process_batch(store, batch_size)
        if done:
            print(f"embedded {done} decision(s)", flush=True)
        if once:
            return
        time.sleep(interval if not done else 0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uri", default=DEFAULT_URI, help="Central server (env: QUACK_URI)")
    parser.add_argument("--token", default=DEFAULT_TOKEN, help="Auth token (env: QUACK_TOKEN)")
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--interval", type=float, default=5.0, help="Seconds between idle polls")
    parser.add_argument("--once", action="store_true", help="Process one batch and exit")
    args = parser.parse_args()

    run(args.uri, args.token, args.batch_size, args.interval, args.once)
