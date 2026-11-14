import pytest

from glaux.db import check_sequence, list_migrations, parse_migration_name


@pytest.mark.parametrize(
    ("name", "version"),
    [("001_init.sql", 1), ("012_add_chunks.sql", 12)],
)
def test_parse_migration_name(name, version):
    assert parse_migration_name(name) == version


@pytest.mark.parametrize("name", ["1_init.sql", "001-init.sql", "001_Init.sql", "001_init.txt"])
def test_parse_migration_name_rejects_bad_names(name):
    with pytest.raises(ValueError):
        parse_migration_name(name)


@pytest.mark.parametrize("versions", [[1, 3], [1, 1], [2]])
def test_check_sequence_rejects_gaps_and_duplicates(versions):
    with pytest.raises(ValueError):
        check_sequence(versions)


def test_shipped_migrations_are_a_clean_sequence():
    migrations = list_migrations()
    assert [m.version for m in migrations] == list(range(1, len(migrations) + 1))
    assert migrations[0].name == "001_init.sql"
    assert "CREATE EXTENSION IF NOT EXISTS vector" in migrations[0].sql
