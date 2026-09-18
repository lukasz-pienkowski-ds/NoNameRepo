.PHONY: help build init ingest query ui down clean

FILE ?= data/raw/sample.jsonl
Q    ?= how does docker compose work
TOPK ?= 5

help:
	@echo "  make build                build the docker image"
	@echo "  make init                 create/apply schema to data/db/context.duckdb"
	@echo "  make ingest [FILE=...]    tag+embed a JSONL file into the store (default: $(FILE))"
	@echo "  make query [Q=...] [TOPK=...]  retrieve top-k similar docs for a query"
	@echo "  make ui                   serve DuckDB web UI at http://localhost:4213 (foreground)"
	@echo "  make down                 stop the ui container"
	@echo "  make clean                remove the generated DuckDB file"

build:
	docker compose build

init: build
	docker compose run --rm context-store python db/init_db.py

ingest: build
	docker compose run --rm context-store python .claude/skills/tag-and-ingest/scripts/ingest.py $(FILE)

query: build
	docker compose run --rm context-store python .claude/skills/query-context/scripts/query.py "$(Q)" --top-k $(TOPK)

ui: build
	docker compose up context-ui

down:
	docker compose down

clean:
	rm -f data/db/context.duckdb data/db/context.duckdb.wal
