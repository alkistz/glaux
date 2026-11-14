# Build log

Newest entries first. For each stage: what was verified against live services, what was not,
measurements, and blockers for the next stage.

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
