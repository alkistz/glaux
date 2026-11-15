# glaux build spec

Status: draft of 2026-11-14. Statements about Diavgeia carry an assumption id (A1, A2, ...). The
first probe (2026-11-14, 19 requests) checked most of them; the table below gives each one's status
and `docs/log.md` has the details. Update this file wherever reality differs, and say so in the log.

Read `docs/context.md` first for why this exists. `CLAUDE.md` holds the working rules. This file says
what to build and how to know each stage is done.

## Phase 1 scope

A more usable Diavgeia for spending decisions:

- harvest decision metadata day by day, resumable and incremental
- download decision PDFs for a chosen set of decision types and extract their text
- extract structured facts (tax IDs, amounts, CPV codes, KIMDIS ids, references to other decisions)
  with tested rules, next to the structured fields the API already gives
- search with hybrid keyword and semantic ranking from a CLI

Not in phase 1: OCR, KIMDIS, TED or registry data, risk indicators, any web interface, anything that
publishes data.

## Built for a public web app

The end product is a public web app (decided 2026-11-14, see `docs/context.md`). Its MVP comes right
after phase 1: search, a page per decision and a page per authority. Phase 1 is the backend it runs
on, so phase 1 follows these rules:

- Commands stay thin. Search, show and statistics live in library functions that return data, and
  the CLI only prints it. A web layer later calls the same functions.
- Every fact keeps its provenance: the ADA, the API field or text span it came from, and the link
  to the official document on Diavgeia. The app links to Diavgeia's PDFs instead of re-hosting them.
- Payees that may be natural persons, sole traders included, are flagged when facts are extracted
  (stage 4), so the app can mask them. Draft the rule from real data: legal-form words in the name
  (Α.Ε., Ε.Π.Ε., Ι.Κ.Ε., Ο.Ε., Ε.Ε.), tax ID patterns, later the business registry.
- Database size and the query-time embedding model have to fit an affordable server. This weighs on
  model choice and vector size in stage 5 (for example `halfvec`, or a smaller model).
- Nothing goes public until the owner has settled the legal questions in `docs/context.md`.

## Principles

- Raw first. Store every API record as received (`jsonb`). Every derived table can be dropped and
  rebuilt from raw data without touching the network.
- Pure logic is separate from I/O. Parsing, normalisation, extraction, chunking and ranking are plain
  functions with unit tests. Only the client, harvest, document fetch, embedding and database modules
  do I/O.
- Every command measures itself. Each run writes a row to `runs` (items, errors, start, end) and prints
  items per second at the end.
- Minimum personal data. Harvest only what phase 1 needs, skip documents flagged as private, keep
  signer and person details out of derived tables.

## Architecture

```
Diavgeia OpenData API
        |
   polite client (one request at a time, backoff, User-Agent with contact)
        |
   harvest ---------> decisions (raw jsonb + indexed columns)
                          |
   fetch-docs <-----------+   (in-scope types, private_data = false)
        |
   documents (text, page stats, OCR flag; PDFs cached on disk)
        |
   +----+--------------------+----------------------+
   |                         |                      |
 extract                   chunk                 subjects
   |                         |                      |
 facts                    chunks ---> embed <-------+
                                        |
                       search: FTS + vector, fused with RRF
```

One Postgres 18 with pgvector in Docker, one Python package `glaux`, one CLI `glaux`.

## Repository layout

```
compose.yaml              Postgres + pgvector, bound to 127.0.0.1
docker/initdb/            creates the glaux_test database on first start
.env.example              settings template; .env is git-ignored
src/glaux/
  cli.py                  argparse entry point
  config.py               settings from the environment and .env
  db.py                   connection and migration runner
  sql/NNN_name.sql        migrations, applied in order, plain SQL
  http.py                 polite HTTP client, for every service    (stage 1)
  probe.py                glaux probe                              (stage 1)
  diavgeia/parse.py       API JSON to row values, pure             (stages 1 and 2)
  harvest.py              day-by-day metadata harvest              (stage 2)
  documents.py            PDF fetch and text extraction            (stage 3)
  extract/                one module per rule, pure                (stage 4)
  text/normalize.py       search normalisation, pure               (stage 5)
  text/chunk.py           chunking, pure                           (stage 5)
  embed.py                BGE-M3 embeddings                        (stage 5)
  search.py               queries and rank fusion                  (stage 5)
tests/unit/               pure logic, no network, no database
tests/integration/        needs the test database, skipped when it is not running
tests/fixtures/           trimmed real API responses, personal data replaced
tests/eval/               judged search queries                    (stage 5)
docs/                     context.md, build-spec.md, log.md
```

## Dependencies

Add a dependency in the stage that first needs it, not before.

| Stage | Package | Why |
|---|---|---|
| 0 | psycopg[binary] 3 | Postgres driver |
| 0 | pytest, ruff (dev) | tests, lint and format |
| 1 | httpx | HTTP client with timeouts |
| 2 | pgvector | adapter for the vector type (can wait until stage 5) |
| 3 | pypdf | PDF text extraction, BSD licence |
| 5 | sentence-transformers (optional group `embed`) | local embeddings; pulls in torch, so keep it optional |
| 5 | none extra | the `http` embedding backend uses httpx, already a dependency |

CLI is `argparse`. Migrations are numbered SQL files run by `glaux db migrate`. No ORM, no web
framework, no task queue.

PDF extraction: start with pypdf. If Greek text quality is poor in stage 3, compare pdfminer.six on the
same 50 PDFs before switching. PyMuPDF (and PyMuPDF4LLM, used by the arXiv corpus paper) is faster
but AGPL licensed; ask before adopting it.

## Configuration

Environment variables, optionally from `.env` in the working directory. Real environment variables win.

| Variable | Default | Meaning |
|---|---|---|
| `GLAUX_CONTACT` | none | Email or URL sent in the User-Agent. Network commands refuse to run without it. |
| `GLAUX_DATABASE_URL` | `postgresql://glaux:glaux@127.0.0.1:5432/glaux` | main database |
| `GLAUX_TEST_DATABASE_URL` | same server, database `glaux_test` | wiped by integration tests |
| `GLAUX_DATA_DIR` | `./data` | PDFs, probe output, caches; git-ignored |
| `GLAUX_REQUEST_DELAY` | `1.0` | seconds between requests to one service |

User-Agent: `glaux/<version> (research prototype; contact: <GLAUX_CONTACT>)`.

## Polite client rules

These apply to every network call, in every stage.

- One request at a time. Wait `GLAUX_REQUEST_DELAY` seconds between requests.
- Timeout 30 seconds per request.
- Retry on 429, 5xx, timeouts and connection errors, with exponential backoff and jitter, at most
  5 attempts. Honour `Retry-After`.
- On 401 or 403, or after 10 consecutive failures, stop the whole run and report. A block is a signal
  to talk to the operator, not something to route around.
- Never disable TLS verification.
- Log every request (method, URL, status, bytes, duration) at debug level, and count them per run.

## Diavgeia API: working assumptions

Status after the first probe (2026-11-14). Samples: one day of issue dates (2026-10-14, first 500
of 1,341) and one deep page of 1 to 14 October (500 of 237,596). Raw responses are in
`data/probe/` (not committed).

| Id | Assumption | Status |
|---|---|---|
| A1 | Base URL `https://diavgeia.gov.gr/opendata/`, JSON via `.json` suffix, no key. | Confirmed. nginx, no rate-limit headers. |
| A2 | `GET /search` filters on `from_issue_date`, `to_issue_date`, `type`, pages with `page` (from 0) and `size`; response `{info, decisions}`. | Confirmed, with a catch: the API silently adds `status:"Αναρτημένη"` (published only) and `submissionTimestamp:[from_issue_date TO now]`. `info.query` shows the real query. `status=all` removes the status filter. `org` not tried yet. |
| A3 | `size` is capped. Deep pagination may be capped. | `size` is silently capped at 500. Page 40 at size 500 (offset 20,000) works; no cap found up to there. |
| A4 | Search results carry the full record, so no per-decision request is needed. | Confirmed: identical to `GET /decisions/{ada}` for three decisions, including `extraFieldValues`. |
| A5 | Decision fields as listed in the arXiv paper. | Confirmed, plus `adam` (always null at top level in 1,000 sampled), `url` (a `luminapi` link), `documentChecksum` (null), `warnings`, `correctedVersionId`. `status` is `PUBLISHED` in records. |
| A6 | `documentUrl` serves the PDF at `https://diavgeia.gov.gr/doc/{ada}`. | Confirmed for one decision (144 KB, about 7 pages). |
| A7 | `extraFieldValues` holds amounts and tax IDs per type, described by `GET /types/{uid}/details`. | Confirmed, richer than expected. Β.2.1 has a nested schema: `org {afm, afmType, name}`, `sponsor[] {sponsorAFMName {afm, afmType, afmCountry, name}, expenseAmount {amount, currency}, cpv, kae}`, `relatedAnalipsiYpoxreosis[]` (the commitment's ADA), `relatedDecisions[]`, `adam`. Β.1.3 has `amountWithVAT`, `amountWithKae`, `financialYear`, `budgettype`. Amounts are JSON numbers: parse with `Decimal`. |
| A8 | Spending type ids Β.1.3, Β.2.1, Β.2.2, Δ.1, Δ.2.1, Δ.2.2. | Confirmed. The ids are these codes, in Greek capitals. `/types` lists 43 types, including parent groups. |
| A9 | `/organizations` and `/types` list everything. | Confirmed. One response each: 43 types; 5,435 organisations (2.5 MB, 19 s). Organisations include `vatNumber`, `supervisorId`, and an official's email (`odeManagerEmail`), which we do not copy into derived tables. |
| A10 | Corrections keep the ADA with a new `versionId`; revocations change `status`. | Partly confirmed. `/decisions/{ada}/versionlog.json` lists versions with status. On 2026-10-14, `status=all` returns 1,413 against 1,341 published. A revoked record has not been seen yet. |
| A11 | Decisions are published days or weeks after their issue date. | Confirmed, strongly. Decisions issued on 2026-10-14 were still arriving on 2026-11-13. Lag in a month sample: median 3 days. |
| A12 | No server-side filter on amount. | Not checked. Diavgeia AI offers amount and payee tax ID filters, which hints that the API (or its advanced search) supports them. Check with the next probe requests. |
| A13 | Rate limits unknown. | 19 requests at 1 per second, no 429s, no limit headers. Still unknown. |
| A14 | `issueDate` is Athens midnight. | Wrong. About 70% are midnight UTC (03:00 Athens in summer), 30% Athens midnight. A one-day range matches a single instant, so it only returns the second group. The Athens-local date of the timestamp is correct for both. Query windows must cover the whole day. |
| A15 | ADAM is two year digits, a type, nine digits. | Confirmed in `extraFieldValues.adam` (467 of 1,000 sampled): `PAY`, `REQ`, `AWRD`, `PROC` seen. Main join key to KIMDIS. |
| A16 | ADAs are 10 characters, hyphen, 3. | Wrong. Before the hyphen: 5, 7, 8 or 10 characters; then 3. Digits and Greek capitals only. |
| A17 | `from_date` and `to_date` filter on submission time. | New, not checked. Needed for the stage 2 design below. |

Privacy flag: `privateData` was true for 29 of 1,000 sampled decisions.

Volume: decisions issued 1 to 14 October 2026 and published by 14 November: 237,596, about 17,000
a day across all types. Bulk exports were not looked for yet.

## Data model

Plain SQL migrations. Stage 0 ships `001_init.sql` (the `vector` extension and the `runs` table). Each
stage below adds its tables in a new migration. No data is loaded until stage 2, so tables can change
freely until then. After that, schema changes need a migration and a check with the owner (see
`CLAUDE.md`).

Draft shapes, to be fixed against the probe results:

**runs** (stage 0): `id`, `command`, `args jsonb`, `started_at`, `finished_at`, `items`, `errors`,
`notes`.

**organizations**, **decision_types** (stage 2): `uid` primary key, `label`, `category` or
`parent_uid`, `raw jsonb`, `fetched_at`.

**decisions** (stage 2):

| Column | Notes |
|---|---|
| `ada` text, primary key | |
| `version_id` text | update the row when it changes |
| `status` text | published, revoked, and so on |
| `subject` text | as received |
| `subject_norm` text | normalised for search (stage 5) |
| `subject_tsv` tsvector | generated from `subject_norm` with config `simple` |
| `issue_date` date | Athens-local date of the timestamp (A14) |
| `adam` text | from `extraFieldValues.adam`, KIMDIS join key (A15) |
| `submitted_at`, `published_at` timestamptz | |
| `org_uid`, `type_uid` text | no foreign keys, since reference lists may lag; a check query reports orphans |
| `private_data` boolean | |
| `document_url` text | |
| `raw` jsonb not null | the full record |
| `first_seen_at`, `updated_at` timestamptz | |

Indexes: `issue_date`, `(type_uid, issue_date)`, `(org_uid, issue_date)`, `adam`, GIN on
`subject_tsv`.

**harvest_days** (stage 2): `day` primary key (a submission day if the proposal in stage 2 is
accepted), `scope` (the type set harvested), `status` (pending, running, done, failed),
`api_total`, `stored`, `pages`, `requests`, `started_at`, `finished_at`, `error`.

**documents** (stage 3): `ada` primary key, `sha256`, `bytes`, `pages`, `text`, `text_chars`,
`chars_per_page`, `needs_ocr`, `extractor` (name and version), `fetched_at`, `error`. Cached PDFs live at
`$GLAUX_DATA_DIR/pdfs/YYYY/MM/{ada}.pdf`. Whether to keep them is decided after stage 3 measures size.

**facts** (stage 4): `id`, `ada`, `field` (afm, amount, cpv, adam, ada_ref), `value` text, `value_num`
numeric, `qualifier` (for example VAT included or excluded), `valid` boolean, `source` (api or text),
`rule`, `rule_version`, `span_start`, `span_end`, `extracted_at`. Rows from the API and from text sit
side by side and are never merged. Re-running a rule replaces only that rule's rows.

**chunks** (stage 5): `id`, `ada`, `seq`, `text`, `text_norm`, `tsv`, `embedding vector(1024)`,
`model`, unique on `(ada, seq)`.

**subject_embeddings** (stage 5): `ada` primary key, `embedding vector(1024)`, `model`, `backend`,
`embedded_at`. `chunks` also gets `backend`. The vector size follows the chosen model (1024 for
BGE-M3, 384 for multilingual-e5-small).

Vector indexes: HNSW with `vector_cosine_ops`, built after the bulk load.

## The test slice

Unless a stage says otherwise, work on one ordinary week: Monday 2026-10-12 to Sunday 2026-10-18. It has
no public holiday, and it is old enough that most late publications (A11) should have arrived. Run
anything slow on one day (2026-10-14) first and extrapolate before running the week.

## Stages

Each stage ends with the definition of done in `CLAUDE.md`: code, passing tests, a note in
`docs/log.md` on what was verified against the live service and what was not, and the next stage's
blockers. Commit once per stage.

### Stage 0: scaffold (done 2026-11-14)

Delivers the package layout, `glaux` entry point, `compose.yaml`, `.gitignore`, `.env.example`, the
migration runner with `glaux db migrate` and `glaux db status`, unit tests and one integration test.

Accept: `uv sync`, `docker compose up -d --wait`, `uv run glaux db migrate`, `uv run pytest` all succeed
on a fresh clone.

### Stage 1: probe

`glaux probe [--day 2026-10-14]` makes a small, fixed set of requests (no more than 20) and saves each
response unchanged under `$GLAUX_DATA_DIR/probe/<timestamp>/`, then prints a summary of keys and value
types.

1. `GET /types` and one `GET /types/{uid}/details` for each spending type found
2. `GET /organizations`, first page
3. `GET /search` for the day: `size=10`, then `size=500`, then `size=1000` to find the cap (A3)
4. `GET /search` for the day filtered to one spending type (A2)
5. `GET /search` with a deep `page` to find a pagination cap, if the day is large enough
6. `GET /decisions/{ada}` for three decisions of different spending types, to compare with the
   search record (A4)
7. one PDF from `documentUrl` (A6)

Then by hand: trim the responses into `tests/fixtures/`, replace natural persons' names and tax IDs
with synthetic values (valid checksum, obviously fake names), and list each fixture's source URL and
fetch date in `tests/fixtures/README.md`. Write `diavgeia/parse.py` against the fixtures.

Accept: every assumption A1 to A16 has a status in the log (confirmed, wrong with what is true, or
still unknown); fixtures exist for a search page, a decision of each spending type, the types list and
one type's details; parser tests run against them; this spec is updated.

Progress (2026-11-14): `glaux probe` built and run once, 18 requests plus 1 by hand, no errors. All
assumptions have a status above. Still to do: fixtures, `diavgeia/parse.py` and its tests.

### Stage 2: metadata harvest

`glaux harvest --from DATE --to DATE [--types spending|all] [--refresh]`

Proposal from the probe results, to confirm with the owner before building: key the harvest on
**submission day**, not issue day. Late publication (A11) is large, so an issue day is never
finished: 2026-10-14 was still gaining decisions a month later. Every decision is submitted exactly
once, so a submission-day harvest catches late decisions without re-harvesting old days. Analysis
still filters on `issue_date`. This depends on A17; if `from_date` and `to_date` do not filter on
submission time, fall back to issue days with a window covering the whole day (A14) and a
`--refresh` of recent weeks.

- Default scope is the spending types (A8). Decisions outside scope are not stored. For scoping
  numbers, record each day's `api_total` across all types too, which costs one request per day.
- Always pass `status=all` so revoked decisions are seen (A2, A10).
- For each day in range: mark it running, page through the results at size 500, upsert each
  decision by ADA (update when `version_id` or `status` changes), then mark it done with
  `api_total`, `stored`, `pages` and `requests`. A failure marks the day failed and the run moves on.
- Rerunning picks up pending, failed and interrupted days. `--refresh` re-harvests days already done.
- Revocations do not change the submission time, so a separate sweep re-checks the status of recent
  decisions. Design it once a revoked record has been seen.
- At about 17,000 decisions a day, a day is about 35 pages and a year about 13,000 requests, which
  is under 4 hours at one request per second.
- Parse JSON with `Decimal` for numbers.
- Also loads `organizations` and `decision_types`.

Accept: harvest the test week. Kill it mid-day, rerun, and the end state is the same: no duplicates,
and `stored` equals the in-scope total for every day. `glaux stats` shows counts per day and per type.
The log records requests made, wall time, decisions per second and database size.

### Stage 3: documents

`glaux fetch-docs --from DATE --to DATE [--limit N]`

- For in-scope decisions with `private_data = false` and no `documents` row: download the PDF, hash it,
  extract text page by page, compute characters per page, and set `needs_ocr` when that falls below a
  threshold (start at 200 and tune on real data).
- Run on 2026-10-14 first. Extrapolate time and disk use to the week and ask before running the week
  if it would take more than a few hours.

Accept, reported per decision type: share with usable text, share needing OCR, share failed, median
PDF size, median text length, documents per hour, and chunks per document. Also measure how much
of the text comes before the operative part (from "Αποφασίζουμε" or "Αποφασίζει" onwards). The
opening list of laws is near-identical across decisions, so chunking only the operative part may
cut embedding cost a lot. Twenty random documents are checked by eye for Greek
text quality (broken encoding, lost accents, words split by hyphens or columns) and the findings are
noted.

### Stage 4: extraction

`glaux extract [--rule NAME] [--from DATE --to DATE]` runs text rules over `documents.text` and API
mappers over `decisions.raw`, and writes `facts`.

Every rule is a pure function returning matches with field, value, numeric value, qualifier, validity,
span, rule name and rule version. Every rule has tests for positive cases, negative cases, edge cases
and at least one snippet from a real fixture.

| Rule | Pattern and checks |
|---|---|
| `afm` | 9 digits within a short window after a keyword (ΑΦΜ, Α.Φ.Μ., A.F.M. and spacing variants). Bare 9-digit numbers without a keyword are ignored. Checksum: digits d1 to d9, sum of d_i times 2^(9-i) for i from 1 to 8, then mod 11, then mod 10, must equal d9; all zeros is invalid. Store failures with `valid = false`: checksum failures are a data-quality signal (see context). |
| `amount` | Greek format `1.234.567,89` or plain `1234,89`, next to a currency marker (€, EUR, ευρώ in any case or accent form). Parsed to `Decimal`, never float. `qualifier` from nearby words: VAT included (συμπεριλαμβανομένου ΦΠΑ, με ΦΠΑ), excluded (πλέον ΦΠΑ, χωρίς ΦΠΑ), or unknown. |
| `cpv` | `\d{8}-\d`, valid only when the code is in the CPV 2008 list. Commit the list as a data file with its source noted. |
| `adam` | The A15 pattern, confirmed or corrected against real text in stage 1. Also match after the label ΑΔΑΜ. |
| `ada_ref` | Fold Latin look-alike capitals to Greek, then match `[0-9Α-Ω]{5,10}-[0-9Α-Ω]{3}` (A16). Skip the decision's own ADA. Whether a reference resolves to a known decision is a query-time join, not a stored flag. |
| API mappers | Map `extraFieldValues` to facts with `source = api`: `sponsor[].sponsorAFMName.afm`, `sponsor[].expenseAmount.amount`, `sponsor[].cpv`, `sponsor[].kae`, `amountWithVAT`, `adam`, and the related-ADA fields (A7). For these types the API is the primary source and text extraction is the cross-check. |

Accept: all rule tests pass. The log has per-field counts for the test week, a hand check of 20 random
matches per field with precision noted, and an agreement report: for decisions with both an API and a
text value for amount or tax ID, the share that agree. The full 100-decision precision evaluation is
roadmap step 3 and comes after phase 1.

### Stage 5: search

1. **Normalisation** (`text/normalize.py`): Unicode NFD, drop combining marks, casefold, fold final
   sigma to sigma, collapse whitespace. The same function runs on stored text and on queries. Tests
   cover accented, unaccented and mixed-case Greek, and Latin text.
2. **Keyword search**: Postgres FTS with config `simple` over normalised text. Queries use
   `websearch_to_tsquery('simple', normalize(q))`. Also try a prefix mode (`:*` on each term) as a
   cheap way to match inflected endings, and compare both on the eval set.
3. **Chunking** (`text/chunk.py`): pack paragraphs into chunks of about 1,200 characters with about 200
   characters of overlap, never splitting inside a word. Only for in-scope documents with usable text.
4. **Embeddings**: `glaux embed subjects|chunks [--batch-size N]`. BGE-M3 dense vectors (1024
   dimensions, normalised) via sentence-transformers, in bf16. Embed the original text, not the
   normalised form. Store the model name and revision. Resumable: only rows without an embedding.
   A first CPU benchmark on synthetic text (`scripts/bench_embeddings.py`, results in `docs/log.md`)
   could not separate BGE-M3, multilingual-e5-small and paraphrase-multilingual-mpnet on quality,
   while e5-small was 10 times faster. Compare BGE-M3 and e5-small on the real eval set below before
   embedding chunks at scale. Qwen3-Embedding-0.6B is out: its tokenizer turns Greek into about 3
   times as many tokens, and it was slower and worse.

   **Switchable backend.** Where vectors are computed is configuration, not code:

   - `local`: sentence-transformers on this machine. The default, and the only backend used for
     search queries unless the owner decides otherwise.
   - `http`: any endpoint that speaks the OpenAI-style `POST /v1/embeddings` protocol, which most
     hosts of open models offer. Use it for a large backfill when local is too slow. Plain httpx
     with the retry logic from `glaux.http`; no provider SDKs.
   - Both sit behind one small interface, `embed(texts) -> vectors`, with a fake backend for tests.
   - Every stored vector records `model` and `backend`. Search only compares vectors from the same
     model, and refuses to mix models.
   - Before vectors from two backends are mixed for one model (for example a hosted backfill plus
     local queries), embed the same 200 texts with both and require cosine similarity of at least
     0.99 for each pair. Record the result in the log.
   - The `http` backend sends decision text, which can contain personal data, to a third party.
     It runs only with `--allow-remote` on the command line, prints the host it is sending to, and
     its first use needs the owner's OK (`CLAUDE.md`).
   - Settings: `GLAUX_EMBED_BACKEND` (`local` or `http`), `GLAUX_EMBED_MODEL`, and for `http`
     `GLAUX_EMBED_URL` and `GLAUX_EMBED_API_KEY`. The key lives in `.env` only.

   Which backend to use for the chunk backfill depends on chunk counts from stage 3 and quality from
   the eval below. `docs/log.md` (2026-11-14) has a first cost and time estimate.
5. **Ranking** (`search.py`): four lists of the top 100 each (FTS on subjects, FTS on chunks, vector on
   subjects, vector on chunks). Chunk lists are collapsed to the best chunk per decision. Fuse with
   reciprocal rank fusion, score = sum over lists of 1 / (60 + rank). Filters for date range,
   organisation and type go inside each list's SQL. `rrf()` is a pure function with tests.
6. **CLI**: `glaux search "query" [--from --to --org --type --limit 20] [--mode hybrid|fts|vector]`
   prints ADA, date, organisation, type, subject, score, which lists matched, and a snippet.
   `glaux show ADA` prints the metadata, facts and document stats for one decision.

Accept: a judged query set of 20 to 30 Greek queries in `tests/eval/queries.yaml`, written by the
owner, each with the relevant ADAs from the test week. It includes inflected forms, queries typed
without accents, and concept queries that share no words with the subject. `glaux eval-search`
reports recall@10 and MRR for fts, vector and hybrid. Hybrid beats FTS alone on recall@10. Search
takes under 1 second at p95 on the test week.

## Commands at the end of phase 1

| Command | Stage |
|---|---|
| `glaux db migrate`, `glaux db status` | 0 |
| `glaux probe` | 1 |
| `glaux harvest`, `glaux stats` | 2 |
| `glaux fetch-docs` | 3 |
| `glaux extract` | 4 |
| `glaux embed`, `glaux search`, `glaux show`, `glaux eval-search` | 5 |

## Testing

- `tests/unit`: pure logic. No network, no database. Fast.
- `tests/integration`: needs the `glaux_test` database and is skipped when it is not reachable. The
  fixture wipes the schema before each test and refuses to run against a database whose name does not
  end in `_test`.
- No test calls the live API. `glaux probe` is the live check, run by hand.
- Fixtures are trimmed real responses with personal data replaced. Each one is listed with its source
  URL and fetch date in `tests/fixtures/README.md`.

## Open decisions

| Decision | When |
|---|---|
| Value for `GLAUX_CONTACT` | done: the repo URL |
| Key the harvest on submission day instead of issue day | before stage 2 |
| Harvest all decision types, or only spending types | after stage 2 shows volumes |
| Embedding backend for the chunk backfill: local, a hosted endpoint for the same open model, or a proprietary API | after stage 3 (chunk counts) and stage 5 (quality) |
| Which years define the first real corpus | after stage 2 |
| Keep PDFs or only their text; how much OCR is needed | after stage 3 |
| Where this runs long term, given embedding cost | after stage 5 measures throughput |
| Check the name `glaux` on PyPI | before publishing anything |

## Notes on the arXiv corpus (2512.05647)

Checked 2026-11-14 from the paper only, not the data. About 1 million decisions from 2021, text
extracted with PyMuPDF4LLM to Markdown, code and data at `https://github.com/y3nk0/diavgeia`. No
licence is stated for the data, and the authors say they did not remove personal data. That rules it
out as a source we store or redistribute. It may still help as a cross-check on extraction quality for
2021 decisions. Look at the repository before stage 3.
