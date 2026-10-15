"""Batch processing logic for OCR integration."""

from app.database import get_connection
from app.ocr_client import parse_identity_card


def process_batch(batch_id: int) -> None:
    """Process every pending case in one batch."""

    with get_connection() as connection:
        cases = connection.execute(
            """
            SELECT id, case_ref, image_ref
            FROM cases
            WHERE batch_id = ?
              AND status = 'pending'
            ORDER BY id
            """,
            (batch_id,),
        ).fetchall()

    for case in cases:
        _process_case(
            case_id=case["id"],
            case_ref=case["case_ref"],
            image_ref=case["image_ref"],
        )


def _process_case(
    case_id: int,
    case_ref: str,
    image_ref: str,
) -> None:
    """Process one pending case and persist its final result."""

    with get_connection() as connection:
        current_case = connection.execute(
            """
            SELECT status
            FROM cases
            WHERE id = ?
            """,
            (case_id,),
        ).fetchone()

    if current_case is None:
        return

    if current_case["status"] != "pending":
        return

    result = parse_identity_card(
        case_ref=case_ref,
        image_ref=image_ref,
    )

    with get_connection() as connection:
        if result.success:
            fields = result.fields or {}

            connection.execute(
                """
                UPDATE cases
                SET
                    status = 'ocr_done',
                    failure_reason = NULL,
                    ocr_id_number = ?,
                    ocr_full_name = ?,
                    ocr_dob = ?,
                    ocr_issue_date = ?,
                    ocr_confidence = ?,
                    ocr_attempts = ?
                WHERE id = ?
                  AND status = 'pending'
                """,
                (
                    fields.get("id_number"),
                    fields.get("full_name"),
                    fields.get("dob"),
                    fields.get("issue_date"),
                    fields.get("confidence"),
                    result.attempts,
                    case_id,
                ),
            )
        else:
            connection.execute(
                """
                UPDATE cases
                SET
                    status = 'ocr_failed',
                    failure_reason = ?,
                    ocr_attempts = ?
                WHERE id = ?
                  AND status = 'pending'
                """,
                (
                    result.failure_reason,
                    result.attempts,
                    case_id,
                ),
            )


def get_pending_case_count(batch_id: int) -> int | None:
    """Return pending case count, or None when batch is missing."""

    with get_connection() as connection:
        batch = connection.execute(
            """
            SELECT id
            FROM batches
            WHERE id = ?
            """,
            (batch_id,),
        ).fetchone()

        if batch is None:
            return None

        row = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM cases
            WHERE batch_id = ?
              AND status = 'pending'
            """,
            (batch_id,),
        ).fetchone()

    return row["count"]
