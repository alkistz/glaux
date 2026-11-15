"""The glaux command line."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import sys

import psycopg

from glaux import __version__, db
from glaux.config import ConfigError, Settings, load_settings, user_agent
from glaux.http import PoliteClient, Refused, TooManyFailures


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


def cmd_probe(args: argparse.Namespace, settings: Settings) -> int:
    from glaux import probe

    agent = user_agent(settings.require_contact())
    stamp = dt.datetime.now().strftime("%Y%m%dT%H%M%S")
    out_dir = settings.data_dir / "probe" / f"{stamp}-{args.set}"
    with PoliteClient(probe.BASE_URL, agent, settings.request_delay) as client:
        if args.set == "filters":
            index = probe.run_filter_probe(client, out_dir, args.day, args.modified_day)
        else:
            index = probe.run_probe(client, out_dir, args.day)
        stats = client.stats
    for e in index:
        status = e.get("status") or "-"
        print(f"{status!s:>4} {e.get('bytes', 0):>9} B {e.get('seconds', 0):>6}s  {e['name']}")
        if e.get("info"):
            print(f"{'':24}info {json.dumps(e['info'], ensure_ascii=False)}")
        if e.get("error"):
            print(f"{'':24}error {e['error']}")
    print(f"\n{stats.requests} requests, {stats.retries} retries, {stats.bytes} bytes")
    print(f"saved to {out_dir}")
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

    probe_parser = commands.add_parser(
        "probe", help="check API assumptions with a few saved requests"
    )
    probe_parser.add_argument(
        "--day",
        type=dt.date.fromisoformat,
        default=dt.date(2026, 10, 14),
        help="issue date to sample (default: 2026-10-14)",
    )
    probe_parser.add_argument(
        "--set",
        choices=("basic", "filters"),
        default="basic",
        help="basic: endpoints and record shapes; filters: date filters, ranges, revocations",
    )
    probe_parser.add_argument(
        "--modified-day",
        type=dt.date.fromisoformat,
        default=dt.date(2026, 11, 13),
        help="last-modified date to sample with --set filters (default: 2026-11-13)",
    )
    probe_parser.set_defaults(func=cmd_probe)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    parser.add_argument("-v", "--verbose", action="store_true", help="log every request")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    try:
        return args.func(args, load_settings())
    except ConfigError as exc:
        print(f"glaux: {exc}", file=sys.stderr)
        return 2
    except (Refused, TooManyFailures) as exc:
        print(f"glaux: stopped: {exc}", file=sys.stderr)
        return 3
    except psycopg.OperationalError as exc:
        print(f"glaux: cannot reach the database: {exc}", file=sys.stderr)
        print("glaux: is it running? Try: docker compose up -d", file=sys.stderr)
        return 1
