"""Operational CLI (FR-006).

``python -m app.cli create-admin --email ... --name ...`` creates the first
administrator — the only account-creation path that does not require an
existing admin. It connects with the admin ``DATABASE_URL`` (migrations'
credential) so RLS on ``users``/``user_roles`` cannot block the bootstrap, sets
the system actor as the acting identity, and writes an argon2id password hash.
"""

import argparse
import getpass
import json
import sys
from pathlib import Path

from sqlalchemy import create_engine, make_url, text

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session_context import set_session_context
from app.main import app

OPENAPI_PATH = Path(__file__).resolve().parents[1] / "openapi.json"


def _admin_engine():
    settings = get_settings()
    url = make_url(settings.DATABASE_URL).set(drivername="postgresql+psycopg")
    return create_engine(url)


def create_admin(email: str, name: str, password: str) -> str:
    if len(password) < 8:
        raise ValueError("password must be at least 8 characters")

    engine = _admin_engine()
    try:
        with engine.connect() as conn, conn.begin():
            system_id = conn.execute(text("SELECT id FROM users WHERE is_system")).scalar_one()
            set_session_context(conn, system_id, ("admin",))

            existing = conn.execute(
                text("SELECT 1 FROM users WHERE email = :email"), {"email": email}
            ).scalar()
            if existing:
                raise ValueError(f"a user with email {email} already exists")

            user_id = conn.execute(
                text(
                    "INSERT INTO users (email, display_name, password_hash, password_set_at) "
                    "VALUES (:email, :name, :password_hash, now()) RETURNING id"
                ),
                {"email": email, "name": name, "password_hash": hash_password(password)},
            ).scalar_one()
            conn.execute(
                text(
                    "INSERT INTO user_roles (user_id, role_id) "
                    "SELECT :user_id, id FROM roles WHERE slug = 'admin'"
                ),
                {"user_id": user_id},
            )
            return str(user_id)
    finally:
        engine.dispose()


def _prompt_password() -> str:
    first = getpass.getpass("Password: ")
    second = getpass.getpass("Confirm password: ")
    if first != second:
        raise ValueError("passwords do not match")
    return first


def render_openapi() -> str:
    """Deterministic OpenAPI rendering (the committed contract, SC-008)."""
    return json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"


def export_openapi(path: str | Path | None = None) -> Path:
    target = Path(path) if path is not None else OPENAPI_PATH
    target.write_text(render_openapi(), encoding="utf-8")
    return target


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create-admin", help="create the first administrator")
    create.add_argument("--email", required=True)
    create.add_argument("--name", required=True)
    create.add_argument(
        "--password",
        help="non-interactive password (omit to be prompted securely)",
    )

    export = sub.add_parser("export-openapi", help="write the committed OpenAPI contract")
    export.add_argument(
        "--output",
        help=f"target path (default: {OPENAPI_PATH})",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "export-openapi":
        target = export_openapi(args.output)
        print(f"Wrote OpenAPI contract to {target}")
        return 0
    if args.command != "create-admin":
        return 2

    try:
        password = args.password or _prompt_password()
        user_id = create_admin(args.email, args.name, password)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"Created administrator {args.email} ({user_id})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
