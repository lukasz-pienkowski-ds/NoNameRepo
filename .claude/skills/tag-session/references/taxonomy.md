# Labeling vocabulary

A controlled vocabulary only works if two people describing the same thing land on the same label. Every message gets exactly one `domain` and one to four `tags` drawn from these lists — or `null` and `[]` when the message carries no engineering content at all.

## Domains (choose exactly one)

- `data-modeling` — schemas, normalization, migrations, multi-tenancy layout
- `data-access` — ORMs, query patterns, connection handling, transactions
- `api-design` — contracts, versioning, pagination, error shapes
- `concurrency` — async/sync, threads, queues, locking, backpressure
- `architecture` — service boundaries, coupling, layering, build-vs-buy
- `state-and-caching` — caching layers, invalidation, session and idempotency state
- `messaging` — events, brokers, delivery guarantees, ordering
- `frontend` — component structure, state management, rendering strategy
- `ml-systems` — feature pipelines, training/serving split, model versioning, eval
- `infra-and-deploy` — packaging, environments, CI/CD, runtime topology
- `observability` — logging, metrics, tracing, alert design
- `security-and-auth` — authn/authz, secrets, tenancy isolation, crypto choices
- `testing` — test strategy, fixtures, contract and load testing
- `performance` — profiling-driven optimization, resource budgets
- `process` — tooling and workflow choices with engineering consequences

## Tags (choose 1–4)

Pattern and tradeoff axes, deliberately technology-agnostic:

`async-vs-sync`, `batch-vs-stream`, `sql-vs-nosql`, `monolith-vs-services`, `build-vs-buy`,
`push-vs-pull`, `polling-vs-webhooks`, `orm-vs-raw-sql`, `optimistic-vs-pessimistic-locking`,
`eventual-consistency`, `idempotency`, `retry-and-backoff`, `rate-limiting`, `connection-pooling`,
`cache-invalidation`, `pagination`, `schema-migration`, `multi-tenancy`, `soft-delete-vs-archive`,
`denormalization`, `queue-backpressure`, `circuit-breaker`, `feature-flagging`,
`server-vs-client-rendering`, `state-management`, `component-composition`, `dashboard-design`,
`file-upload-handling`, `background-jobs`, `cron-vs-event-driven`, `secrets-management`,
`token-vs-session-auth`, `rbac-vs-abac`, `pii-handling`, `audit-logging`,
`error-taxonomy`, `logging-strategy`, `metric-cardinality`, `test-pyramid`, `fixture-strategy`,
`contract-testing`, `dependency-injection`, `plugin-architecture`, `config-management`,
`versioning-strategy`, `data-validation-boundary`, `timezone-handling`, `numeric-precision`,
`bulk-import`, `third-party-api-limits`, `vendor-lock-in`, `cost-vs-latency`, `legacy-interop`

## Choosing well

Tag the **tradeoff axis, not the technology**. `redis` tells a future reader nothing transferable; `cache-invalidation` plus `push-vs-pull` finds the message again from a different stack. The technology stays in the message text, which is stored verbatim.

## Proposing a new tag

If nothing fits, use the closest existing tag **and** add one more of the form `new:my-proposed-tag`. The writer accepts the `new:` prefix and it marks the label for later curation. Do not silently invent bare tags — a vocabulary that grows by one label per session stops being a vocabulary.
