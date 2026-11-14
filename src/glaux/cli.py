"""The glaux command line."""

from __future__ import annotations

import argparse
import sys

import psycopg

from glaux import __version__, db
from glaux.config import ConfigError, Settings, load_settings


def cmd_db_migrate(args: argparse.Namespace, settings: Settings) -> int:
    with db.connect(settings.database_url) as conn:
        applied = db.migrate(conn)
    if applied:
        for m in applied:
            print(f"applied {m.name}")
    else:
        print("database is up to date")
    return 0


def cmd_db_status(args: argparse.Namespace, settings: Settings) -> int:
    with db.connect(settings.database_url) as conn:
        done = db.applied_versions(conn)
    for m in db.list_migrations():
        state = "applied" if m.version in done else "pending"
        print(f"{state:8} {m.name}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="glaux", description="Greek public spending monitor.")
    parser.add_argument("--version", action="version", version=f"glaux {__version__}")
    commands = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    db_parser = commands.add_parser("db", help="database schema")
    db_commands = db_parser.add_subparsers(dest="db_command", required=True, metavar="ACTION")
    db_commands.add_parser("migrate", help="apply pending migrations").set_defaults(
        func=cmd_db_migrate
    )
    db_commands.add_parser("status", help="list applied and pending migrations").set_defaults(
        func=cmd_db_status
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args, load_settings())
    except ConfigError as exc:
        print(f"glaux: {exc}", file=sys.stderr)
        return 2
    except psycopg.OperationalError as exc:
        print(f"glaux: cannot reach the database: {exc}", file=sys.stderr)
        print("glaux: is it running? Try: docker compose up -d", file=sys.stderr)
        return 1
