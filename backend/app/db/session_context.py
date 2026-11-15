"""Session-context helpers: transaction-scoped identity for audit attribution and RLS.

Sets ``app.user_id`` / ``app.role_names`` / ``app.job_id`` for the current
transaction exactly per ``specs/001-database-foundation/contracts/session-context.md``.
Values must be set at the start of every transaction, before any read or write.

We use ``set_config(name, value, is_local => true)`` rather than ``SET LOCAL``:
``set_config`` is an ordinary function, so the value is passed as a bound
parameter (no string interpolation), and ``is_local => true`` scopes it to the
transaction just like ``SET LOCAL`` — so it never leaks across pooled connections.
"""

import uuid
from collections.abc import Iterable, Sequence

from sqlalchemy import text
from sqlalchemy.engine import Connection

ROLE_SLUGS = frozenset({"admin", "genomics", "trf", "molecular", "bioinformatics"})

_SET = text("SELECT set_config(:key, :value, true)")


class SessionContextError(ValueError):
    """Raised when the session context values are missing or invalid."""


def _require_uuid(value: uuid.UUID, key: str) -> str:
    if not isinstance(value, uuid.UUID):
        raise SessionContextError(f"{key} must be a uuid.UUID, got {type(value).__name__}")
    return str(value)


def _role_literal(role_names: Iterable[str]) -> str:
    roles: Sequence[str] = tuple(role_names)
    if not roles:
        raise SessionContextError("app.role_names requires at least one role slug")
    unknown = sorted(set(roles) - ROLE_SLUGS)
    if unknown:
        raise SessionContextError(f"unknown role slugs: {', '.join(unknown)}")
    ordered = list(dict.fromkeys(roles))
    return ",".join(ordered)


def set_session_context(
    conn: Connection,
    user_id: uuid.UUID,
    role_names: Iterable[str],
    job_id: uuid.UUID | None = None,
) -> None:
    """Set the acting identity on the current transaction.

    Must be called inside an open transaction, before any other statement.
    """
    if not conn.in_transaction():
        raise SessionContextError("set_session_context must be called inside an open transaction")

    conn.execute(_SET, {"key": "app.user_id", "value": _require_uuid(user_id, "app.user_id")})
    conn.execute(_SET, {"key": "app.role_names", "value": _role_literal(role_names)})
    if job_id is not None:
        conn.execute(_SET, {"key": "app.job_id", "value": _require_uuid(job_id, "app.job_id")})
