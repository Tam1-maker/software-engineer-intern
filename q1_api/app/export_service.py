"""CSV export creation and account-opening delivery logic."""

import csv
import hashlib
import io
import json

from app.database import get_connection
from app.onboarding_client import deliver_export


class BatchNotFoundError(LookupError):
    """Raised when the requested batch does not exist."""


def export_batch(batch_id: int) -> dict:
    """Create or retry an export for stage-two-approved cases."""

    existing_export = _find_retryable_export(batch_id)

    if existing_export is not None:
        return _deliver_stored_export(existing_export)

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
            raise BatchNotFoundError("batch not found")

        cases = connection.execute(
            """
            SELECT
                id,
                case_ref,
                applicant_name,
                COALESCE(ocr_id_number, id_number) AS export_id_number,
                COALESCE(ocr_dob, dob) AS export_dob,
                COALESCE(
                    ocr_issue_date,
                    issue_date
                ) AS export_issue_date
            FROM cases
            WHERE batch_id = ?
              AND status = 'stage2_approved'
            ORDER BY id
            """,
            (batch_id,),
        ).fetchall()

    if not cases:
        return {
            "batch_id": batch_id,
            "export_created": False,
            "case_count": 0,
            "message": "no new stage2-approved cases to export",
        }

    file_bytes = _build_export_csv(cases)
    content_hash = hashlib.sha256(file_bytes).hexdigest()

    idempotency_key = (
        f"batch-{batch_id}-export-{content_hash}"
    )
    file_name = (
        f"EXPORT-BATCH-{batch_id}-"
        f"{content_hash[:12]}.csv"
    )

    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO exports (
                batch_id,
                file_name,
                file_content,
                idempotency_key,
                case_count
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                batch_id,
                file_name,
                file_bytes,
                idempotency_key,
                len(cases),
            ),
        )
        export_id = cursor.lastrowid

        for case in cases:
            connection.execute(
                """
                INSERT INTO export_cases (
                    export_id,
                    case_id
                )
                VALUES (?, ?)
                """,
                (
                    export_id,
                    case["id"],
                ),
            )

    stored_export = {
        "id": export_id,
        "batch_id": batch_id,
        "file_name": file_name,
        "file_content": file_bytes,
        "idempotency_key": idempotency_key,
        "case_count": len(cases),
    }

    return _deliver_stored_export(stored_export)


def _build_export_csv(cases) -> bytes:
    """Build deterministic CSV bytes for approved cases."""

    output = io.StringIO(newline="")

    writer = csv.writer(
        output,
        lineterminator="\n",
    )

    writer.writerow(
        [
            "case_ref",
            "applicant_name",
            "id_number",
            "dob",
            "issue_date",
        ]
    )

    for case in cases:
        writer.writerow(
            [
                case["case_ref"],
                case["applicant_name"],
                case["export_id_number"],
                case["export_dob"],
                case["export_issue_date"],
            ]
        )

    return output.getvalue().encode("utf-8")


def _find_retryable_export(batch_id: int) -> dict | None:
    """Find an undelivered export that must retain its key."""

    with get_connection() as connection:
        export = connection.execute(
            """
            SELECT
                id,
                batch_id,
                file_name,
                file_content,
                idempotency_key,
                case_count
            FROM exports
            WHERE batch_id = ?
              AND delivery_status IN ('pending', 'failed')
            ORDER BY id
            LIMIT 1
            """,
            (batch_id,),
        ).fetchone()

    if export is None:
        return None

    return dict(export)


def _deliver_stored_export(export: dict) -> dict:
    """Deliver a stored export and persist the result."""

    result = deliver_export(
        file_name=export["file_name"],
        file_bytes=export["file_content"],
        idempotency_key=export["idempotency_key"],
    )

    if result.success:
        receipt = result.receipt or {}

        with get_connection() as connection:
            connection.execute(
                """
                UPDATE exports
                SET
                    delivery_status = 'delivered',
                    delivery_id = ?,
                    delivery_receipt = ?,
                    delivery_attempts = ?,
                    failure_reason = NULL
                WHERE id = ?
                """,
                (
                    receipt.get("delivery_id"),
                    json.dumps(
                        receipt,
                        ensure_ascii=False,
                    ),
                    result.attempts,
                    export["id"],
                ),
            )

            connection.execute(
                """
                UPDATE cases
                SET status = 'exported'
                WHERE id IN (
                    SELECT case_id
                    FROM export_cases
                    WHERE export_id = ?
                )
                  AND status = 'stage2_approved'
                """,
                (export["id"],),
            )

        return {
            "batch_id": export["batch_id"],
            "export_id": export["id"],
            "export_created": True,
            "file_name": export["file_name"],
            "case_count": export["case_count"],
            "idempotency_key": export["idempotency_key"],
            "delivery_status": "delivered",
            "delivery_attempts": result.attempts,
            "receipt": receipt,
        }

    with get_connection() as connection:
        connection.execute(
            """
            UPDATE exports
            SET
                delivery_status = 'failed',
                delivery_attempts = ?,
                failure_reason = ?
            WHERE id = ?
            """,
            (
                result.attempts,
                result.failure_reason,
                export["id"],
            ),
        )

    return {
        "batch_id": export["batch_id"],
        "export_id": export["id"],
        "export_created": True,
        "file_name": export["file_name"],
        "case_count": export["case_count"],
        "idempotency_key": export["idempotency_key"],
        "delivery_status": "failed",
        "delivery_attempts": result.attempts,
        "failure_reason": result.failure_reason,
    }
