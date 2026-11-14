"""Database connection and a minimal SQL migration runner.

Migrations are plain SQL files in glaux/sql named NNN_description.sql. Each one runs once, in
version order, inside its own transaction, and is recorded in schema_migrations.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from importlib import resources

import psycopg

_MIGRATION_NAME = re.compile(r"^(\d{3})_[a-z0-9_]+\.sql$")


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    sql: str


def parse_migration_name(name: str) -> int:
    """Return the version number of a migration file name, or raise ValueError."""
    match = _MIGRATION_NAME.match(name)
    if not match:
        raise ValueError(f"bad migration file name: {name!r} (expected NNN_description.sql)")
    return int(match.group(1))


def check_sequence(versions: list[int]) -> None:
    """Versions must run 1, 2, 3 ... with no gaps or duplicates."""
    expected = list(range(1, len(versions) + 1))
    if sorted(versions) != expected:
        raise ValueError(f"migration versions must be 1..{len(versions)}, got {sorted(versions)}")


def list_migrations() -> list[Migration]:
    folder = resources.files("glaux").joinpath("sql")
    migrations = [
        Migration(parse_migration_name(entry.name), entry.name, entry.read_text(encoding="utf-8"))
        for entry in folder.iterdir()
        if entry.name.endswith(".sql")
    ]
    migrations.sort(key=lambda m: m.version)
    check_sequence([m.version for m in migrations])
    return migrations


def connect(database_url: str) -> psycopg.Connection:
    return psycopg.connect(database_url, connect_timeout=5)


_CREATE_MIGRATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version    integer PRIMARY KEY,
    name       text NOT NULL,
    applied_at timestamptz NOT NULL DEFAULT now()
)
"""


def applied_versions(conn: psycopg.Connection) -> set[int]:
    with conn.transaction():
        conn.execute(_CREATE_MIGRATIONS_TABLE)
        rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
    return {row[0] for row in rows}


def pending_migrations(conn: psycopg.Connection) -> list[Migration]:
    done = applied_versions(conn)
    return [m for m in list_migrations() if m.version not in done]


def migrate(conn: psycopg.Connection) -> list[Migration]:
    """Apply every pending migration. Returns the ones applied."""
    applied = []
    for migration in pending_migrations(conn):
        with conn.transaction():
            conn.execute(migration.sql)
            conn.execute(
                "INSERT INTO schema_migrations (version, name) VALUES (%s, %s)",
                (migration.version, migration.name),
            )
        applied.append(migration)
    return applied
