# Build log

Newest entries first. For each stage: what was verified against live services, what was not,
measurements, and blockers for the next stage.

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
