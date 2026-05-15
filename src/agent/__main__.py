"""`python -m agent` dispatcher."""

from __future__ import annotations

import argparse
import sqlite3
import sys

from anthropic import Anthropic

from agent.config import load_settings
from agent.db.store import init_db, list_pending, update_draft_status
from agent.draft import run_draft
from agent.logging_setup import setup_logging


def _cmd_draft(args: argparse.Namespace) -> int:
    settings = load_settings()
    setup_logging(settings.log_level)
    client = Anthropic(api_key=settings.anthropic_api_key)
    result = run_draft(
        settings,
        anthropic_client=client,
        force=args.force,
        override_post_type=args.post_type,
        dry_run=args.dry_run,
    )
    print(f"status={result.status} post_type={result.post_type} draft_id={result.draft_id}")
    return 0 if result.status in ("drafted", "skipped", "dry_run") else 1


def _cmd_db_list_pending(_: argparse.Namespace) -> int:
    settings = load_settings()
    setup_logging(settings.log_level)
    conn = init_db(settings.db_path)
    try:
        for d in list_pending(conn):
            print(f"{d.id}\t{d.post_type}\t{d.source_ref}\t{d.expires_at}")
    finally:
        conn.close()
    return 0


def _cmd_db_expire(args: argparse.Namespace) -> int:
    settings = load_settings()
    setup_logging(settings.log_level)
    conn = init_db(settings.db_path)
    try:
        update_draft_status(conn, args.draft_id, "expired")
        print(f"marked {args.draft_id} expired")
    finally:
        conn.close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="agent")
    sub = p.add_subparsers(dest="cmd", required=True)

    draft = sub.add_parser("draft", help="Generate today's draft.")
    draft.add_argument("--dry-run", action="store_true")
    draft.add_argument("--force", action="store_true")
    draft.add_argument("--post-type", choices=["project", "concept", "tip"])
    draft.set_defaults(func=_cmd_draft)

    db = sub.add_parser("db", help="Inspect the SQLite state.")
    db_sub = db.add_subparsers(dest="db_cmd", required=True)

    list_p = db_sub.add_parser("list-pending")
    list_p.set_defaults(func=_cmd_db_list_pending)

    expire_p = db_sub.add_parser("expire")
    expire_p.add_argument("draft_id")
    expire_p.set_defaults(func=_cmd_db_expire)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
