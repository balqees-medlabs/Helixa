"""The gated 8-stage workflow (FR-009/010/010a/011, research D3/D4).

One-step transitions only, server-side gates, and an atomic guarded update so
a stale advance (someone else moved the sample first) is rejected with 409.
The Spec 1 trigger fills the stage event's duration; the write is audited in
the same request transaction.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.services import consent_service, sample_service

# Which role may advance a sample *into* the given stage position (research D3).
# ``admin`` always passes. Registration (position 1) is a separate route guard.
STAGE_ROLES: dict[int, tuple[str, ...]] = {
    2: ("genomics",),  # consent & documentation
    3: ("molecular",),  # molecular processing
    4: ("bioinformatics",),  # data generation
    5: ("trf",),  # TRF preparation
    6: ("trf",),  # TRF confirmation
    7: ("bioinformatics",),  # data conversion & QC
    8: ("bioinformatics",),  # report upload/archive/portal push
}

CONSENT_GATE_POSITION = 3
QC_GATE_POSITION = 8


class StageConflict(Exception):
    """Stale advance, skipped stage, or a sample that cannot advance."""


class StageGateFailed(Exception):
    """A precondition for the target stage is unmet (consent or QC)."""


class StagePermissionDenied(Exception):
    """The acting user's roles may not advance into the target stage."""


@dataclass(frozen=True)
class AdvanceResult:
    sample: dict
    from_stage: int
    to_stage: int


def roles_for(target_position: int) -> tuple[str, ...]:
    return STAGE_ROLES.get(target_position, ())


def can_advance_to(actor_roles: tuple[str, ...], target_position: int) -> bool:
    if "admin" in actor_roles:
        return True
    return bool(set(roles_for(target_position)) & set(actor_roles))


def _gate(conn: Connection, sample_id: uuid.UUID, target_position: int) -> None:
    if target_position == CONSENT_GATE_POSITION and not consent_service.required_complete(
        conn, sample_id
    ):
        raise StageGateFailed("Consent checklist incomplete: every required item must be complete")
    if target_position == QC_GATE_POSITION:
        passed = conn.execute(
            text(
                "SELECT 1 FROM qc_results "
                "WHERE sample_id = :sample_id AND kind = 'qc' AND passed LIMIT 1"
            ),
            {"sample_id": sample_id},
        ).scalar()
        if not passed:
            raise StageGateFailed("Quality control must be passed before report/archive")


def advance(
    conn: Connection,
    sample_id: uuid.UUID,
    *,
    from_stage: int,
    to_stage: int | None,
    actor_id: uuid.UUID,
    actor_roles: tuple[str, ...],
    note: str | None = None,
) -> AdvanceResult:
    current = (
        conn.execute(
            text(
                "SELECT s.id, s.status, s.current_stage_id, st.position "
                "FROM samples s JOIN stages st ON st.id = s.current_stage_id "
                "WHERE s.id = :sample_id"
            ),
            {"sample_id": sample_id},
        )
        .mappings()
        .first()
    )
    if current is None:
        raise sample_service.SampleNotFound(str(sample_id))

    if current["status"] != "active":
        raise StageConflict(f"Sample is {current['status']}; only active samples can advance")

    if current["position"] != from_stage:
        raise StageConflict(
            f"Sample has already advanced to stage {current['position']}; refresh and retry"
        )

    target_position = from_stage + 1
    if to_stage is not None and to_stage != target_position:
        raise StageConflict(
            f"Cannot skip stages: {from_stage} -> {to_stage}; expected {target_position}"
        )
    if target_position > 8:
        raise StageConflict("Sample is already at the final stage")

    target = (
        conn.execute(
            text("SELECT id, position, slug, name FROM stages WHERE position = :position"),
            {"position": target_position},
        )
        .mappings()
        .first()
    )
    if target is None:
        raise StageConflict(f"Stage {target_position} does not exist")

    if not can_advance_to(actor_roles, target_position):
        required = ", ".join(roles_for(target_position)) or "admin"
        raise StagePermissionDenied(f"Advancing to stage {target_position} requires: {required}")

    _gate(conn, sample_id, target_position)

    updated = conn.execute(
        text(
            "UPDATE samples SET current_stage_id = :to_stage_id "
            "WHERE id = :sample_id AND current_stage_id = :from_stage_id "
            "AND status = 'active'"
        ),
        {
            "to_stage_id": target["id"],
            "sample_id": sample_id,
            "from_stage_id": current["current_stage_id"],
        },
    )
    if updated.rowcount == 0:
        raise StageConflict("Sample has already advanced; refresh and retry")

    conn.execute(
        text(
            "INSERT INTO sample_stage_events (sample_id, stage_id, actor_id, note) "
            "VALUES (:sample_id, :stage_id, :actor_id, :note)"
        ),
        {
            "sample_id": sample_id,
            "stage_id": target["id"],
            "actor_id": actor_id,
            "note": note,
        },
    )

    return AdvanceResult(
        sample=sample_service.get_sample(conn, sample_id),
        from_stage=from_stage,
        to_stage=target_position,
    )
