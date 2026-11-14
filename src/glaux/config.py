"""Settings from environment variables, with an optional .env file in the working directory.

Real environment variables win over values in .env.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from glaux import __version__

DEFAULT_DATABASE_URL = "postgresql://glaux:glaux@127.0.0.1:5432/glaux"
DEFAULT_DATA_DIR = "./data"
DEFAULT_REQUEST_DELAY = 1.0


class ConfigError(Exception):
    """A setting is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    database_url: str
    contact: str | None
    data_dir: Path
    request_delay: float

    def require_contact(self) -> str:
        """Return the contact for the User-Agent, or fail if it is not set."""
        if not self.contact:
            raise ConfigError(
                "GLAUX_CONTACT is not set. Network commands send it in the User-Agent so the "
                "operators of public services can reach us. Set it in .env (see .env.example)."
            )
        return self.contact


def parse_env_file(text: str) -> dict[str, str]:
    """Parse KEY=VALUE lines. Skips blank lines and comments, strips one pair of quotes."""
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").lstrip()
        key, sep, value = line.partition("=")
        key = key.strip()
        if not sep or not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        values[key] = value
    return values


def load_settings(
    environ: Mapping[str, str] | None = None,
    env_file: Path | None = Path(".env"),
) -> Settings:
    env: dict[str, str] = {}
    if env_file is not None and env_file.is_file():
        env.update(parse_env_file(env_file.read_text(encoding="utf-8")))
    env.update(os.environ if environ is None else environ)

    delay_text = env.get("GLAUX_REQUEST_DELAY") or str(DEFAULT_REQUEST_DELAY)
    try:
        delay = float(delay_text)
    except ValueError as exc:
        raise ConfigError(f"GLAUX_REQUEST_DELAY must be a number, got {delay_text!r}") from exc
    if delay < 0:
        raise ConfigError("GLAUX_REQUEST_DELAY must not be negative")

    return Settings(
        database_url=env.get("GLAUX_DATABASE_URL") or DEFAULT_DATABASE_URL,
        contact=(env.get("GLAUX_CONTACT") or "").strip() or None,
        data_dir=Path(env.get("GLAUX_DATA_DIR") or DEFAULT_DATA_DIR),
        request_delay=delay,
    )


def user_agent(contact: str) -> str:
    """The User-Agent header for every request glaux makes to a public service."""
    return f"glaux/{__version__} (research prototype; contact: {contact})"
