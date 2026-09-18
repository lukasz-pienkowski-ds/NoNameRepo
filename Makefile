.PHONY: help build up down logs wait-store status seed find detect extract test test-integration test-all shell clean

SEED  ?= data/seed/decisions.jsonl
TAGS  ?= skalowanie
LIMIT ?= 3

help:
	@echo "  make up                   start the decision store + embedding worker"
	@echo "  make down                 stop and remove them"
	@echo "  make logs                 follow their logs"
	@echo "  make build                build the image"
	@echo ""
	@echo "  make status               row counts on the store"
	@echo "  make seed                 load demo decisions ($(SEED))"
	@echo "  make find [TAGS=...]      find precedents by tag (limit $(LIMIT))"
	@echo "  make detect               list LLM CLIs with sessions on this machine"
	@echo "  make extract              scan those sessions and upsert decisions"
	@echo ""
	@echo "  make test                 offline checks, no server needed"
	@echo "  make test-integration     checks that need a running store"
	@echo "  make test-all             both of the above"
	@echo ""
	@echo "  make shell                shell inside the running store"
	@echo "  make clean                delete the store's database file"

build:
	docker compose build

up: build
	docker compose up -d
	@$(MAKE) --no-print-directory wait-store
	@echo "decision store on quack://localhost:$${QUACK_PORT:-8888}"

down:
	docker compose down

logs:
	docker compose logs -f

# exec, not run: these talk to the *running* server. `compose run` would start a
# second container where 127.0.0.1:8888 has nothing listening on it.
EXEC := docker compose exec decision-store

# How long to wait for the store to report healthy, in seconds.
WAIT ?= 60

# `docker compose exec` fails against a container that is up but still starting,
# which showed up once as a spurious exit 2 immediately after a --build. Every
# exec target waits for the healthcheck first, so the command runs against a
# store that is actually serving rather than one that merely exists.
wait-store:
	@id=$$(docker compose ps -q decision-store 2>/dev/null); \
	if [ -z "$$id" ]; then \
	  echo "decision-store nie dziala. Uruchom: make up"; exit 1; \
	fi; \
	for i in $$(seq 1 $(WAIT)); do \
	  s=$$(docker inspect --format '{{.State.Health.Status}}' $$id 2>/dev/null); \
	  if [ "$$s" = "healthy" ]; then exit 0; fi; \
	  if [ "$$s" = "unhealthy" ]; then \
	    echo "decision-store jest unhealthy. Zobacz: make logs"; exit 1; \
	  fi; \
	  sleep 1; \
	done; \
	echo "decision-store nie wstal w $(WAIT)s (status: $$s). Zobacz: make logs"; exit 1

status: wait-store
	$(EXEC) python db/cli.py status

seed: wait-store
	$(EXEC) python db/cli.py load $(SEED)

find: wait-store
	$(EXEC) python db/cli.py find --tags $(TAGS) --limit $(LIMIT)

detect: wait-store
	$(EXEC) python db/extract.py --detect

extract: wait-store
	$(EXEC) python db/extract.py --developer "$${USER}"

test: wait-store
	$(EXEC) python test_smoke.py

# Runs inside the store's own container, so it reaches the server on localhost
# and needs no ports or token from the host.
test-integration: wait-store
	$(EXEC) python test_integration.py --require

test-all: test test-integration

shell: wait-store
	$(EXEC) bash

clean:
	rm -f data/db/decisions.duckdb data/db/decisions.duckdb.wal
