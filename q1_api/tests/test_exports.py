"""Tests for CSV export and account-opening delivery."""

from fastapi.testclient import TestClient

from app.database import get_connection
from app.main import app
from app.onboarding_client import DeliveryResult


def insert_export_batch() -> tuple[int, list[int]]:
    """Insert approved and non-approved test cases."""

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
            ("export_test.csv", 3, 0),
        )
        batch_id = cursor.lastrowid

        case_ids = []

        for index, status in enumerate(
            (
                "stage2_approved",
                "stage2_approved",
                "stage1_approved",
            ),
            start=1,
        ):
            cursor = connection.execute(
                """
                INSERT INTO cases (
                    batch_id,
                    case_ref,
                    applicant_name,
                    id_number,
                    dob,
                    issue_date,
                    image_ref,
                    status,
                    ocr_id_number,
                    ocr_full_name,
                    ocr_dob,
                    ocr_issue_date,
                    ocr_confidence
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    batch_id,
                    f"APPL-EXPORT-{index:03d}",
                    f"Export Applicant {index}",
                    f"TEST-ID-ORIGINAL-{index}",
                    "1990-01-01",
                    "2020-01-01",
                    f"id_scan_{index:03d}.jpg",
                    status,
                    f"TEST-ID-OCR-{index}",
                    f"OCR Applicant {index}",
                    "1991-02-02",
                    "2021-02-02",
                    0.95,
                ),
            )
            case_ids.append(cursor.lastrowid)

    return batch_id, case_ids


def test_export_delivers_only_stage2_approved_cases(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_PATH", str(database_path))

    captured_delivery = {}

    def fake_delivery(
        file_name,
        file_bytes,
        idempotency_key,
    ):
        captured_delivery["file_name"] = file_name
        captured_delivery["file_bytes"] = file_bytes
        captured_delivery["key"] = idempotency_key

        return DeliveryResult(
            success=True,
            receipt={
                "delivery_id": "DLV-TEST-001",
                "idempotency_key": idempotency_key,
                "file_name": file_name,
                "sha256": "test-hash",
                "ingested_at": 1234567890,
                "attempts": 1,
            },
            failure_reason=None,
            attempts=1,
        )

    monkeypatch.setattr(
        "app.export_service.deliver_export",
        fake_delivery,
    )

    with TestClient(app) as client:
        batch_id, case_ids = insert_export_batch()

        response = client.post(
            f"/api/batches/{batch_id}/export"
        )

    assert response.status_code == 200

    body = response.json()

    assert body["case_count"] == 2
    assert body["delivery_status"] == "delivered"
    assert body["receipt"]["delivery_id"] == "DLV-TEST-001"

    csv_text = captured_delivery["file_bytes"].decode(
        "utf-8"
    )

    assert "APPL-EXPORT-001" in csv_text
    assert "APPL-EXPORT-002" in csv_text
    assert "TEST-ID-OCR-1" in csv_text
    assert "TEST-ID-OCR-2" in csv_text
    assert "APPL-EXPORT-003" not in csv_text

    with get_connection() as connection:
        first_case = connection.execute(
            "SELECT status FROM cases WHERE id = ?",
            (case_ids[0],),
        ).fetchone()

        second_case = connection.execute(
            "SELECT status FROM cases WHERE id = ?",
            (case_ids[1],),
        ).fetchone()

        third_case = connection.execute(
            "SELECT status FROM cases WHERE id = ?",
            (case_ids[2],),
        ).fetchone()

        export_count = connection.execute(
            "SELECT COUNT(*) AS count FROM exports"
        ).fetchone()["count"]

    assert first_case["status"] == "exported"
    assert second_case["status"] == "exported"
    assert third_case["status"] == "stage1_approved"
    assert export_count == 1


def test_later_export_excludes_previously_exported_cases(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_PATH", str(database_path))

    def fake_delivery(
        file_name,
        file_bytes,
        idempotency_key,
    ):
        return DeliveryResult(
            success=True,
            receipt={
                "delivery_id": "DLV-TEST-002",
                "idempotency_key": idempotency_key,
                "file_name": file_name,
                "sha256": "test-hash",
                "ingested_at": 1234567890,
                "attempts": 1,
            },
            failure_reason=None,
            attempts=1,
        )

    monkeypatch.setattr(
        "app.export_service.deliver_export",
        fake_delivery,
    )

    with TestClient(app) as client:
        batch_id, _ = insert_export_batch()

        first_response = client.post(
            f"/api/batches/{batch_id}/export"
        )

        second_response = client.post(
            f"/api/batches/{batch_id}/export"
        )

    assert first_response.status_code == 200
    assert first_response.json()["case_count"] == 2

    assert second_response.status_code == 200
    assert second_response.json()["export_created"] is False
    assert second_response.json()["case_count"] == 0
    assert (
        second_response.json()["message"]
        == "no new stage2-approved cases to export"
    )

    with get_connection() as connection:
        export_count = connection.execute(
            "SELECT COUNT(*) AS count FROM exports"
        ).fetchone()["count"]

    assert export_count == 1


def test_failed_delivery_retries_same_stored_export(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_PATH", str(database_path))

    observed_keys = []
    delivery_call_count = 0

    def fake_delivery(
        file_name,
        file_bytes,
        idempotency_key,
    ):
        nonlocal delivery_call_count
        delivery_call_count += 1
        observed_keys.append(idempotency_key)

        if delivery_call_count == 1:
            return DeliveryResult(
                success=False,
                receipt=None,
                failure_reason="temporary delivery failure",
                attempts=3,
            )

        return DeliveryResult(
            success=True,
            receipt={
                "delivery_id": "DLV-RECOVERED",
                "idempotency_key": idempotency_key,
                "file_name": file_name,
                "sha256": "test-hash",
                "ingested_at": 1234567890,
                "attempts": 2,
                "deduplicated": True,
            },
            failure_reason=None,
            attempts=2,
        )

    monkeypatch.setattr(
        "app.export_service.deliver_export",
        fake_delivery,
    )

    with TestClient(app) as client:
        batch_id, _ = insert_export_batch()

        first_response = client.post(
            f"/api/batches/{batch_id}/export"
        )

        second_response = client.post(
            f"/api/batches/{batch_id}/export"
        )

    assert first_response.status_code == 502
    assert second_response.status_code == 200

    assert len(observed_keys) == 2
    assert observed_keys[0] == observed_keys[1]

    with get_connection() as connection:
        exports = connection.execute(
            """
            SELECT *
            FROM exports
            ORDER BY id
            """
        ).fetchall()

        exported_count = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM cases
            WHERE status = 'exported'
            """
        ).fetchone()["count"]

    assert len(exports) == 1
    assert exports[0]["delivery_status"] == "delivered"
    assert exports[0]["delivery_id"] == "DLV-RECOVERED"
    assert exported_count == 2


def test_missing_batch_export_returns_404(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_PATH", str(database_path))

    with TestClient(app) as client:
        response = client.post(
            "/api/batches/999999/export"
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "batch not found"
