"""Business logic for importing account application batches."""

import csv
import io
import json

from app.database import get_connection
from app.validation import REQUIRED_FIELDS, validate_application_row


class CSVImportError(ValueError):
    """Raised when an uploaded CSV cannot be imported."""


def import_batch(filename: str, content: bytes) -> dict:
    """Validate and store one uploaded CSV batch."""

    if not filename.lower().endswith(".csv"):
        raise CSVImportError("uploaded file must be a CSV file")

    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CSVImportError("CSV file must use UTF-8 encoding") from exc

    reader = csv.DictReader(io.StringIO(text))

    if reader.fieldnames is None:
        raise CSVImportError("CSV file must include a header row")

    actual_fields = [field.strip() for field in reader.fieldnames]
    expected_fields = list(REQUIRED_FIELDS)

    if actual_fields != expected_fields:
        raise CSVImportError(
            "CSV header must contain exactly: "
            + ", ".join(expected_fields)
        )

    seen_case_refs: set[str] = set()
    accepted_rows: list[dict[str, str]] = []
    rejected_rows: list[dict] = []

    for row_number, row in enumerate(reader, start=2):
        normalized, errors = validate_application_row(
            row,
            seen_case_refs,
        )

        if errors:
            rejected_rows.append(
                {
                    "row_number": row_number,
                    "raw_data": row,
                    "reasons": errors,
                }
            )
        else:
            accepted_rows.append(normalized)

    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO batches (
                source_filename,
                accepted_count,
                rejected_count
            )
            VALUES (?, ?, ?)
            """,
            (
                filename,
                len(accepted_rows),
                len(rejected_rows),
            ),
        )
        batch_id = cursor.lastrowid

        for row in accepted_rows:
            connection.execute(
                """
                INSERT INTO cases (
                    batch_id,
                    case_ref,
                    applicant_name,
                    id_number,
                    dob,
                    issue_date,
                    image_ref
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    batch_id,
                    row["case_ref"],
                    row["applicant_name"],
                    row["id_number"],
                    row["dob"],
                    row["issue_date"],
                    row["image_ref"],
                ),
            )

        for rejected in rejected_rows:
            connection.execute(
                """
                INSERT INTO rejected_rows (
                    batch_id,
                    row_number,
                    raw_data,
                    reasons
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    batch_id,
                    rejected["row_number"],
                    json.dumps(
                        rejected["raw_data"],
                        ensure_ascii=False,
                    ),
                    json.dumps(
                        rejected["reasons"],
                        ensure_ascii=False,
                    ),
                ),
            )

    return {
        "batch_id": batch_id,
        "source_filename": filename,
        "accepted_count": len(accepted_rows),
        "rejected_count": len(rejected_rows),
        "rejected_rows": [
            {
                "row_number": rejected["row_number"],
                "reasons": rejected["reasons"],
            }
            for rejected in rejected_rows
        ],
    }


def get_batch_details(batch_id: int) -> dict | None:
    """Return batch metadata and case counts grouped by status."""

    with get_connection() as connection:
        batch = connection.execute(
            """
            SELECT
                id,
                source_filename,
                accepted_count,
                rejected_count,
                created_at
            FROM batches
            WHERE id = ?
            """,
            (batch_id,),
        ).fetchone()

        if batch is None:
            return None

        status_rows = connection.execute(
            """
            SELECT status, COUNT(*) AS count
            FROM cases
            WHERE batch_id = ?
            GROUP BY status
            ORDER BY status
            """,
            (batch_id,),
        ).fetchall()

        rejected_rows = connection.execute(
            """
            SELECT row_number, reasons
            FROM rejected_rows
            WHERE batch_id = ?
            ORDER BY row_number
            """,
            (batch_id,),
        ).fetchall()

    status_counts = {
        row["status"]: row["count"]
        for row in status_rows
    }

    return {
        "batch_id": batch["id"],
        "source_filename": batch["source_filename"],
        "accepted_count": batch["accepted_count"],
        "rejected_count": batch["rejected_count"],
        "created_at": batch["created_at"],
        "status_counts": status_counts,
        "rejected_rows": [
            {
                "row_number": row["row_number"],
                "reasons": json.loads(row["reasons"]),
            }
            for row in rejected_rows
        ],
    }


def list_batch_cases(
    batch_id: int,
    status: str | None,
    page: int,
    page_size: int,
) -> dict | None:
    """Return one paginated page of cases from a batch."""

    with get_connection() as connection:
        batch_exists = connection.execute(
            """
            SELECT 1
            FROM batches
            WHERE id = ?
            """,
            (batch_id,),
        ).fetchone()

        if batch_exists is None:
            return None

        where_clause = "WHERE batch_id = ?"
        parameters: list = [batch_id]

        if status is not None:
            where_clause += " AND status = ?"
            parameters.append(status)

        total = connection.execute(
            f"""
            SELECT COUNT(*) AS count
            FROM cases
            {where_clause}
            """,
            parameters,
        ).fetchone()["count"]

        offset = (page - 1) * page_size
        query_parameters = parameters + [page_size, offset]

        rows = connection.execute(
            f"""
            SELECT
                id,
                case_ref,
                applicant_name,
                id_number,
                dob,
                issue_date,
                image_ref,
                status,
                failure_reason,
                created_at
            FROM cases
            {where_clause}
            ORDER BY id
            LIMIT ? OFFSET ?
            """,
            query_parameters,
        ).fetchall()

    return {
        "batch_id": batch_id,
        "status": status,
        "page": page,
        "page_size": page_size,
        "total": total,
        "cases": [
            dict(row)
            for row in rows
        ],
    }
