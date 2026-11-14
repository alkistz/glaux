import pytest

from glaux import db

pytestmark = pytest.mark.db


def test_migrate_applies_everything_once(empty_db):
    first = db.migrate(empty_db)
    assert [m.version for m in first] == [m.version for m in db.list_migrations()]
    assert db.migrate(empty_db) == []
    assert db.pending_migrations(empty_db) == []


def test_pgvector_is_available_after_migrate(empty_db):
    db.migrate(empty_db)
    query = "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
    row = empty_db.execute(query).fetchone()
    assert row is not None
    assert empty_db.execute("SELECT '[1,2,3]'::vector <=> '[1,2,3]'::vector").fetchone()[0] == 0
