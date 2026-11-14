from pathlib import Path

import pytest

from glaux.config import (
    DEFAULT_DATABASE_URL,
    ConfigError,
    load_settings,
    parse_env_file,
    user_agent,
)


def test_parse_env_file_handles_comments_quotes_and_export():
    text = """
    # a comment
    GLAUX_CONTACT="someone@example.org"
    export GLAUX_DATA_DIR='/tmp/glaux'
    GLAUX_REQUEST_DELAY = 2.5
    not a setting
    =no key
    EMPTY=
    """
    assert parse_env_file(text) == {
        "GLAUX_CONTACT": "someone@example.org",
        "GLAUX_DATA_DIR": "/tmp/glaux",
        "GLAUX_REQUEST_DELAY": "2.5",
        "EMPTY": "",
    }


def test_parse_env_file_keeps_equals_signs_in_values():
    assert parse_env_file("URL=postgresql://u:p@h/db?a=b") == {"URL": "postgresql://u:p@h/db?a=b"}


def test_defaults_when_nothing_is_set():
    s = load_settings(environ={}, env_file=None)
    assert s.database_url == DEFAULT_DATABASE_URL
    assert s.contact is None
    assert s.data_dir == Path("./data")
    assert s.request_delay == 1.0


def test_environment_wins_over_env_file(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("GLAUX_CONTACT=from-file\nGLAUX_REQUEST_DELAY=3\n", encoding="utf-8")
    s = load_settings(environ={"GLAUX_CONTACT": "from-env"}, env_file=env_file)
    assert s.contact == "from-env"
    assert s.request_delay == 3.0


def test_blank_contact_counts_as_missing():
    s = load_settings(environ={"GLAUX_CONTACT": "   "}, env_file=None)
    assert s.contact is None
    with pytest.raises(ConfigError, match="GLAUX_CONTACT"):
        s.require_contact()


@pytest.mark.parametrize("value", ["fast", "-1"])
def test_bad_request_delay_is_rejected(value):
    with pytest.raises(ConfigError, match="GLAUX_REQUEST_DELAY"):
        load_settings(environ={"GLAUX_REQUEST_DELAY": value}, env_file=None)


def test_user_agent_names_tool_and_contact():
    ua = user_agent("someone@example.org")
    assert ua.startswith("glaux/")
    assert "contact: someone@example.org" in ua
