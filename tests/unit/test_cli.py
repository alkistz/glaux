import pytest

from glaux.cli import build_parser, main


def test_help_exits_cleanly(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    assert "db" in capsys.readouterr().out


def test_command_is_required():
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args([])
    assert exc.value.code == 2


def test_db_needs_an_action():
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(["db"])
    assert exc.value.code == 2


def test_unreachable_database_is_reported_not_raised(monkeypatch, capsys):
    monkeypatch.setenv("GLAUX_DATABASE_URL", "postgresql://nobody@127.0.0.1:1/none")
    assert main(["db", "status"]) == 1
    assert "cannot reach the database" in capsys.readouterr().err
