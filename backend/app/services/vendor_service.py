"""Vendor management (FR-014).

Vendor turnaround is defined by ``tat_days`` plus a ``tat_anchor``
(``receipt`` or ``sequencing``); the SLA/metrics service applies the anchor.
"""

import uuid

from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError


class VendorNotFound(Exception):
    """No vendor with that id."""


class VendorExists(Exception):
    """A vendor with that name already exists."""


_VENDOR_SELECT = (
    "SELECT id, name, tat_days, tat_anchor, is_active, delivery_kind, endpoint_ref, "
    "naming_pattern, md5_required, verification_method FROM vendors "
)


def list_vendors(conn: Connection) -> list[dict]:
    rows = conn.execute(text(f"{_VENDOR_SELECT} ORDER BY name")).mappings().all()
    return [dict(row) for row in rows]


def get_vendor(conn: Connection, vendor_id: uuid.UUID) -> dict:
    row = (
        conn.execute(text(f"{_VENDOR_SELECT} WHERE id = :vendor_id"), {"vendor_id": vendor_id})
        .mappings()
        .first()
    )
    if row is None:
        raise VendorNotFound(str(vendor_id))
    return dict(row)


def create_vendor(
    conn: Connection,
    *,
    name: str,
    tat_days: int,
    tat_anchor: str,
    is_active: bool,
) -> dict:
    if conn.execute(text("SELECT 1 FROM vendors WHERE name = :name"), {"name": name}).scalar():
        raise VendorExists(name)
    try:
        vendor_id = conn.execute(
            text(
                "INSERT INTO vendors (name, tat_days, tat_anchor, is_active) "
                "VALUES (:name, :tat_days, :tat_anchor, :is_active) RETURNING id"
            ),
            {
                "name": name,
                "tat_days": tat_days,
                "tat_anchor": tat_anchor,
                "is_active": is_active,
            },
        ).scalar_one()
    except IntegrityError as exc:
        raise VendorExists(name) from exc
    return get_vendor(conn, vendor_id)


def update_vendor(
    conn: Connection,
    vendor_id: uuid.UUID,
    *,
    name: str | None = None,
    tat_days: int | None = None,
    tat_anchor: str | None = None,
    is_active: bool | None = None,
    delivery_kind: str | None = None,
    endpoint_ref: dict | None = None,
    naming_pattern: str | None = None,
    md5_required: bool | None = None,
    verification_method: str | None = None,
) -> dict:
    get_vendor(conn, vendor_id)

    assignments: list[str] = []
    params: dict = {"vendor_id": vendor_id}
    if name is not None:
        assignments.append("name = :name")
        params["name"] = name
    if tat_days is not None:
        assignments.append("tat_days = :tat_days")
        params["tat_days"] = tat_days
    if tat_anchor is not None:
        assignments.append("tat_anchor = :tat_anchor")
        params["tat_anchor"] = tat_anchor
    if is_active is not None:
        assignments.append("is_active = :is_active")
        params["is_active"] = is_active
    # Non-secret delivery profile (T004): set via the flat PATCH fields.
    if delivery_kind is not None:
        assignments.append("delivery_kind = :delivery_kind")
        params["delivery_kind"] = delivery_kind
    if endpoint_ref is not None:
        assignments.append("endpoint_ref = :endpoint_ref")
        params["endpoint_ref"] = endpoint_ref
    if naming_pattern is not None:
        assignments.append("naming_pattern = :naming_pattern")
        params["naming_pattern"] = naming_pattern
    if md5_required is not None:
        assignments.append("md5_required = :md5_required")
        params["md5_required"] = md5_required
    if verification_method is not None:
        assignments.append("verification_method = :verification_method")
        params["verification_method"] = verification_method

    if assignments:
        try:
            conn.execute(
                text(f"UPDATE vendors SET {', '.join(assignments)} WHERE id = :vendor_id"),
                params,
            )
        except IntegrityError as exc:
            raise VendorExists(name or "") from exc

    return get_vendor(conn, vendor_id)
