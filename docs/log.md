# Build log

Newest entries first. For each stage: what was verified against live services, what was not,
measurements, and blockers for the next stage.

## Where we stopped (2026-11-14, end of day)

Branches: `main` on GitHub has stage 0. `stage-1-probe` is local only, not pushed, three commits
ahead of `main`: the polite client, `glaux probe`, the probe results below, the embedding
benchmark, the switchable embedding backend plan and the public web app decision.

Waiting on the owner:

1. Key the stage 2 harvest on submission day instead of issue day (stage 2 in the spec). Check A17
   with one request first.
2. Push `stage-1-probe` once stage 1 is done.
3. Who the public web app is for first (open questions in `docs/context.md`).

Next steps to finish stage 1:

1. Cut fixtures from `data/probe/20261114T013502/`: a search page, one decision of each spending
   type, the types list and the Β.2.1 type details. Replace natural persons' names and tax IDs
   with synthetic values (valid checksum) and list sources in `tests/fixtures/README.md`.
2. Write `diavgeia/parse.py` and its tests: JSON numbers as `Decimal`, issue date as the
   Athens-local date (A14), ADA and ADAM patterns as found (A15, A16).
3. Check A17 (`from_date`, `to_date` on submission time) with one request.
4. Close stage 1 in this log, then delete the raw probe responses that are no longer needed. They
   contain personal data.

Local state outside git:

- `.env` holds `GLAUX_CONTACT=https://github.com/alkistz/glaux`.
- The Postgres container `glaux-db-1` is running (`docker compose stop` stops it; data stays in
  the `glaux-pg` volume).
- `data/probe/` holds 4.5 MB of raw responses, including personal data. Git-ignored.
- `~/.cache/huggingface/hub` gained about 6 GB of model weights for the benchmark:
  multilingual-e5-small, BGE-M3 and Qwen3-Embedding-0.6B. Qwen3 (about 1.2 GB) is no longer needed.
- Repo-local git `user.email` is the GitHub noreply address.

## 2026-11-14: stage 1 in progress, first probe

Contact for the User-Agent: `https://github.com/alkistz/glaux` (public, issues on; the README has a
note for service operators in English and Greek).

Built `glaux.http.PoliteClient` (one request at a time, 1 s apart, backoff on 429 and 5xx, honours
`Retry-After`, stops on 401, 403, long waits, TLS failures and 10 failures in a row) and
`glaux probe`. 44 tests pass.

Live requests: 1 by hand, then `glaux probe --day 2026-10-14` with 18 requests in 37 s, no errors,
no retries, 4.5 MB. Responses saved in `data/probe/20261114T013502/` (not committed).

Verified against the live API: A1, A2 (with hidden default filters), A3, A4, A5, A6, A7, A8, A9,
A11, A15. Partly: A10. Wrong: A14 (issue dates are midnight in either Athens time or UTC) and A16
(ADA prefixes vary in length). Not checked: A12, A13, and the new A17. Details are in the table in
`docs/build-spec.md`.

What changes because of it:

- The one-day query used so far misses about 70% of a day's decisions (A14). Any harvest window
  has to cover the whole day.
- Late publication is large (A11). Proposed: key the harvest on submission day, not issue day.
  Needs the owner's OK and a check of A17.
- Default search hides non-published decisions. Use `status=all`.
- For spending types the API already gives structured tax IDs, amounts, CPV and budget codes, and
  ADAM for about half of decisions. Text extraction becomes a cross-check for these fields.
- Volume: about 17,000 decisions a day across all types (1 to 14 October 2026, published by
  14 November). A year of metadata is about 13,000 requests.

Not done yet for stage 1: trimmed fixtures with personal data replaced, `diavgeia/parse.py` and its
tests.

### Embedding benchmark (input for stage 5)

`scripts/bench_embeddings.py`, CPU only (Ryzen AI 9 HX 370, 12 cores, AVX-512 BF16). Quality on
25 hand-written Greek queries against 44 synthetic subjects, so it is a sanity check, not a model
choice: one query is 4 points. Speed on 1,000 subjects (about 20 tokens) and 192 chunks of 1,200
characters (about 330 tokens for XLM-R tokenizers).

| Model | hit@1 | hit@3 | MRR | subjects/s bf16 | chunks/s bf16 | hours per 1M chunks |
|---|---|---|---|---|---|---|
| Postgres `simple` FTS, exact | 0.04 | 0.04 | 0.04 | | | |
| Same, 5-character prefix | 0.16 | 0.16 | 0.16 | | | |
| paraphrase-multilingual-mpnet-base-v2 (278M) | 0.64 | 0.84 | 0.75 | 294 | 18.7 | 15 |
| multilingual-e5-small (118M) | 0.64 | 0.88 | 0.77 | 848 | 55.5 | 5 |
| BGE-M3 (568M) | 0.68 | 0.80 | 0.76 | 81 | 5.4 | 51 |
| Qwen3-Embedding-0.6B (596M) | 0.52 | 0.68 | 0.64 | 19 | 1.5 | over 185 |

- bf16 is about twice as fast as fp32 for the XLM-R models, with cosine similarity of at least
  0.998 to the fp32 vectors. Qwen3 gained nothing from bf16.
- Qwen3's tokenizer produces about 3 times as many tokens for Greek (1,067 against 333 per chunk).
  Its chunk speed was measured with truncation to 512 tokens, so the real figure is worse.
- The keyword scores are low because the query set was written to be hard for keywords
  (synonyms, colloquial words). Real queries will be kinder to full-text search.
- At about 17,000 decisions a day, BGE-M3 embeds a day's subjects in under 4 minutes. Chunks
  depend on document length, measured in stage 3.

First estimate for one year of chunks, assuming about 5 million in-scope decisions a year and about
330 tokens per chunk. API prices are from memory, not checked; proprietary tokenizers may count
Greek as more tokens.

| | 3 chunks per decision | 10 chunks per decision |
|---|---|---|
| BGE-M3 on this laptop | about 32 days | about 107 days |
| multilingual-e5-small on this laptop | about 3 days | about 10 days |
| New decisions each day, BGE-M3 local | about 2 hours | about 7 hours |
| Hosted BGE-M3, about $0.01 per million tokens | about $50 | about $165 |
| Proprietary API, $0.02 to $0.15 per million tokens | $100 to $750 | $330 to $2,500 |

Subjects for a year take about 20 hours with BGE-M3 locally, so no API is needed for subjects or
queries. The one PDF fetched so far has about 7 pages, which suggests the higher column, but one
document proves nothing. The spec now plans a switchable embedding backend (stage 5).

## 2026-11-14: stage 0, scaffold

Done:

- Moved project docs into place: `CLAUDE.md` (was `CLAUDE.MD`, so Claude Code did not load it) and
  `docs/context.md`. The CLI is named `glaux` (the context draft called it `dvg`).
- Wrote `docs/build-spec.md` from scratch. The original spec from the design conversation was not
  carried over.
- Package layout under `src/glaux`, `glaux` entry point, argparse CLI with `db migrate` and
  `db status`, settings from the environment and `.env`, a plain SQL migration runner.
- `compose.yaml` with `pgvector/pgvector:0.8.7-pg18-trixie`, bound to 127.0.0.1, plus a
  `glaux_test` database created on first start.
- Migration `001_init.sql`: the `vector` extension and the `runs` table.

Verified locally:

- Postgres 18.7 and pgvector 0.8.7 run. `glaux db migrate` applies `001_init.sql` and is a no-op on
  rerun.
- `uv run pytest`: 24 passed (22 unit, 2 integration against `glaux_test`).
- `ruff check` and `ruff format` are clean.
- Cold start of the database container, image already pulled: about 26 seconds to healthy.

Machine: 24 cores, 62 GB RAM, no NVIDIA GPU detected. BGE-M3 will run on CPU. Measure in stage 5.

Not verified: nothing about Diavgeia yet. No request has been made to any public service.

Side check, arXiv corpus 2512.05647: summary in `docs/build-spec.md`. Not usable as a stored source
(2021 only, no data licence, personal data not removed). Its field list matches assumption A5.

Blockers for stage 1:

- `GLAUX_CONTACT` needs a value before any request goes out.
