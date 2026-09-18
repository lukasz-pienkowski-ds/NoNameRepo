.PHONY: help build up down ingest query context guard ui clean

FILE    ?= data/raw/sample.jsonl
Q       ?= how does docker compose work
TOPK    ?= 5
DOMAIN  ?= hackaton_26
MODEL   ?=
TAGS    ?=
CTXQ    ?=
SESSION ?=
GDOMAIN ?=

CONTEXT_STORE_URL ?= http://localhost:8000

help:
	@echo "  make build                build the docker image"
	@echo "  make up                   start the context-store server in the background at $(CONTEXT_STORE_URL)"
	@echo "  make down                 stop the context-store server (and ui, if running)"
	@echo "  make ingest [FILE=...]    tag+embed a JSONL file by sending it to the running server"
	@echo "  make query [Q=...] [TOPK=...]  ask the running server for top-k similar docs"
	@echo "  make context DOMAIN=... [MODEL=...] [TAGS=...] [CTXQ=...]  project context, grouped by topic"
	@echo "  make guard SESSION=<transcript.jsonl> [GDOMAIN=...]  check a dev session's moves against precedent"
	@echo "  make ui                   serve DuckDB web UI at http://localhost:4213 (foreground, read-only)"
	@echo "  make clean                remove the generated DuckDB file (stop the server first)"
	@echo ""
	@echo "  ingest/query/context/guard are plain network clients (CONTEXT_STORE_URL=$(CONTEXT_STORE_URL))"
	@echo "  and work the same way whether the server is this docker-compose stack or a remote host."

build:
	docker compose build

up: build
	docker compose up -d context-store
	@echo "context-store running at $(CONTEXT_STORE_URL)"

down:
	docker compose down

ingest:
	python3 .claude/skills/tag-and-ingest/scripts/ingest.py $(FILE) --url $(CONTEXT_STORE_URL)

query:
	python3 .claude/skills/query-context/scripts/query.py "$(Q)" --top-k $(TOPK) --url $(CONTEXT_STORE_URL)

context:
	python3 .claude/skills/project-context/scripts/project_context.py $(DOMAIN) \
		$(if $(MODEL),--model $(MODEL)) $(if $(TAGS),--tags $(TAGS)) $(if $(CTXQ),--query "$(CTXQ)") \
		--url $(CONTEXT_STORE_URL)

guard:
	python3 .claude/skills/session-guard/scripts/session_guard.py $(SESSION) \
		$(if $(GDOMAIN),--domain $(GDOMAIN)) --url $(CONTEXT_STORE_URL)

ui: build
	docker compose up context-ui

clean:
	rm -f data/db/context.duckdb data/db/context.duckdb.wal
