# glaux

γλαύξ, the owl on Athenian coins. A Greek public spending monitor.

Phase 1 is a more usable [Diavgeia](https://diavgeia.gov.gr): hybrid keyword and semantic search over
public decisions, plus structured facts (tax IDs, amounts, CPV codes, KIMDIS ids) extracted from the
decision PDFs. It produces risk signals for a human to check, never findings about named people or
companies.

- Why and background: [docs/context.md](docs/context.md)
- What to build and in what order: [docs/build-spec.md](docs/build-spec.md)
- What has been verified so far: [docs/log.md](docs/log.md)

## For operators of public services

glaux reads public data through official APIs, one request at a time with a pause between
requests. It identifies itself with a User-Agent that links to this repository. If it puts load on
your service or you want it to stop, please open an issue here and we will slow down or stop.

Αν το glaux επιβαρύνει την υπηρεσία σας, ανοίξτε ένα issue σε αυτό το αποθετήριο και θα μειώσουμε
ή θα σταματήσουμε τα αιτήματα.

## Setup

Needs [uv](https://docs.astral.sh/uv/) and Docker.

```sh
cp .env.example .env          # then set GLAUX_CONTACT
uv sync
docker compose up -d --wait   # Postgres 18 + pgvector on 127.0.0.1:5432
uv run glaux db migrate
uv run pytest
```

Integration tests use the `glaux_test` database and are skipped when it is not running.
