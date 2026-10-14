"""Business logic for reviewing account application cases."""

from app.database import get_connection
from app.transitions import (
    determine_next_status,
    explain_invalid_transition,
)


class CaseNotFoundError(LookupError):
    """Raised when the requested case does not exist."""


class InvalidTransitionError(ValueError):
    """Raised when a requested review transition is not allowed."""


def review_case(
    case_id: int,
    stage: int,
    decision: str,
) -> dict:
    """Apply one valid review decision to a case."""

    with get_connection() as connection:
        case = connection.execute(
            """
            SELECT id, batch_id, case_ref, status
            FROM cases
            WHERE id = ?
            """,
            (case_id,),
        ).fetchone()

        if case is None:
            raise CaseNotFoundError("case not found")

        current_status = case["status"]

        next_status = determine_next_status(
            current_status=current_status,
            stage=stage,
            decision=decision,
        )

        if next_status is None:
            reason = explain_invalid_transition(
                current_status=current_status,
                stage=stage,
            )
            raise InvalidTransitionError(reason)

        connection.execute(
            """
            UPDATE cases
            SET status = ?
            WHERE id = ?
            """,
            (
                next_status,
                case_id,
            ),
        )

    return {
        "case_id": case["id"],
        "batch_id": case["batch_id"],
        "case_ref": case["case_ref"],
        "previous_status": current_status,
        "status": next_status,
        "stage": stage,
        "decision": decision,
    }
