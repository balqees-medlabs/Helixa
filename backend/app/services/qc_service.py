"""Data-generation and quality-control outcomes (FR-013).

A passing ``kind='qc'`` row is the report/archive gate; ``data_generation``
rows capture the upstream outcome without opening that gate.
"""

import json
import uuid

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.services.sample_service import get_sample


def record(
    conn: Connection,
    sample_id: uuid.UUID,
    *,
    kind: str,
    passed: bool,
    detail: dict,
    actor_id: uuid.UUID,
) -> dict:
    get_sample(conn, sample_id)  # 404 when hidden/absent

    row = (
        conn.execute(
            text(
                "INSERT INTO qc_results (sample_id, kind, passed, detail, recorded_by) "
                "VALUES (:sample_id, :kind, :passed, CAST(:detail AS jsonb), :recorded_by) "
                "RETURNING id, sample_id, kind, passed, detail, recorded_by, recorded_at"
            ),
            {
                "sample_id": sample_id,
                "kind": kind,
                "passed": passed,
                "detail": json.dumps(detail),
                "recorded_by": actor_id,
            },
        )
        .mappings()
        .one()
    )
    return dict(row)
