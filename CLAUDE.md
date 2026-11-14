# CLAUDE.md

Project: glaux (γλαύξ, the owl on Athenian coins). A Greek public spending monitor. Phase 1 is a more
usable Diavgeia: hybrid keyword and semantic search plus structured facts extracted from decision PDFs.

You are building the code. Stage 1 (probe) is in progress. Start each session by reading "Where we
stopped" at the top of `docs/log.md`: it lists what is waiting on me and the next steps.

The end product is a public web app (see `docs/context.md`). Phase 1 builds its backend.

## Commands

- `uv sync` installs; `uv run glaux --help` lists CLI commands.
- `docker compose up -d --wait` starts Postgres 18 with pgvector on 127.0.0.1:5432.
- `uv run glaux db migrate` applies migrations from `src/glaux/sql/`.
- `uv run pytest` runs everything; integration tests skip when the `glaux_test` database is down.
- `uv run ruff check . && uv run ruff format .` before committing.

## Read first

1. `docs/context.md` for why this exists, the research behind it, constraints and roadmap.
2. `docs/build-spec.md` for what to build: architecture, data model, extraction rules, CLI, tests, acceptance criteria.

## How to work

- Start by running one real request against the Diavgeia OpenData API and look at the actual response
  before designing parsers. The spec lists assumptions that were never verified. Treat the live API as the
  source of truth and update `docs/build-spec.md` where reality differs.
- Build in the stage order given in the spec. Finish and test each stage on a small slice (one week of
  decisions) before moving on. Time each stage and report throughput.
- Keep pure logic (normalisation, extraction, chunking, ranking, parsing) free of network and database
  access, with unit tests. Add a test with every extraction rule. Save real API responses as trimmed fixtures
  in `tests/fixtures/` after checking them for personal data.
- Keep raw API JSON in the database so extraction can be re-run without re-harvesting.
- Prefer boring choices: Python 3.11+, Postgres with pgvector in Docker, plain SQL, a small CLI. No
  frameworks beyond what the spec needs.
- Commit per stage with a clear message. Do not commit data, PDFs, dumps, model caches or `.env`.
- Ask me before making decisions that are expensive to reverse (schema changes after data is loaded, switching
  the search store, anything that publishes or shares data).

## Rules that always apply

- Be a polite client of public services: low concurrency, an honest User-Agent with a contact address,
  retries with backoff, resumable and incremental harvesting.
- Skip documents for records flagged as containing private data. Collect and store the minimum personal data
  the task needs.
- Anything about named people or companies is a lead to verify, never a finding. Score and aggregate at the
  level of authorities and procedures. Do not build features that publish named suspicion.
- Never disable TLS verification or work around network blocks. Report them.
- Write plain prose in docs and commit messages. No em dashes.

## Definition of done for a stage

Code, tests passing, a short note in `docs/build-spec.md` or `docs/log.md` on what was verified against the
live service and what was not, and the next stage's blockers listed.