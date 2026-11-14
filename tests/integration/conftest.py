import os

import psycopg
import pytest

TEST_DATABASE_URL = os.environ.get(
    "GLAUX_TEST_DATABASE_URL", "postgresql://glaux:glaux@127.0.0.1:5432/glaux_test"
)


@pytest.fixture
def empty_db():
    """A connection to an emptied test database. Skips when the database is not running."""
    try:
        conn = psycopg.connect(TEST_DATABASE_URL, connect_timeout=3, autocommit=True)
    except psycopg.OperationalError as exc:
        reason = exc.__class__.__name__
        pytest.skip(f"test database not reachable ({reason}); run docker compose up -d")
    name = conn.execute("SELECT current_database()").fetchone()[0]
    assert name.endswith("_test"), f"refusing to wipe non-test database {name!r}"
    conn.execute("DROP SCHEMA public CASCADE")
    conn.execute("CREATE SCHEMA public")
    conn.autocommit = False
    try:
        yield conn
    finally:
        conn.close()
