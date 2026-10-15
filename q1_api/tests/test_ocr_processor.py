"""Tests for background OCR batch processing."""

from fastapi.testclient import TestClient

from app.database import get_connection
from app.main import app
from app.ocr_client import OCRResult


def insert_batch_with_cases() -> tuple[int, list[int]]:
    """Insert one batch with a readable and unreadable case."""

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
            ("ocr_test.csv", 2, 0),
        )
        batch_id = cursor.lastrowid

        case_ids = []

        for case_ref, image_ref in (
            ("APPL-OCR-001", "id_scan_001.jpg"),
            ("APPL-OCR-002", "id_badscan_002.jpg"),
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
                    image_ref
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    batch_id,
                    case_ref,
                    "OCR Applicant",
                    "TEST-ID-ORIGINAL",
                    "1990-01-01",
                    "2020-01-01",
                    image_ref,
                ),
            )
            case_ids.append(cursor.lastrowid)

    return batch_id, case_ids


def test_process_batch_stores_success_and_failure(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_PATH", str(database_path))

    def fake_parse(case_ref, image_ref):
        if "badscan" in image_ref:
            return OCRResult(
                success=False,
                fields=None,
                failure_reason="scan is unreadable",
                attempts=1,
            )

        return OCRResult(
            success=True,
            fields={
                "id_number": "TEST-ID-OCR-001",
                "full_name": "OCR Result Applicant",
                "dob": "1990-01-01",
                "issue_date": "2020-01-01",
                "confidence": 0.96,
            },
            failure_reason=None,
            attempts=2,
        )

    monkeypatch.setattr(
        "app.ocr_processor.parse_identity_card",
        fake_parse,
    )

    with TestClient(app) as client:
        batch_id, case_ids = insert_batch_with_cases()

        response = client.post(
            f"/api/batches/{batch_id}/process"
        )

    assert response.status_code == 202
    assert response.json()["batch_id"] == batch_id
    assert response.json()["pending_count"] == 2
    assert response.json()["processing_started"] is True

    with get_connection() as connection:
        successful_case = connection.execute(
            """
            SELECT *
            FROM cases
            WHERE id = ?
            """,
            (case_ids[0],),
        ).fetchone()

        failed_case = connection.execute(
            """
            SELECT *
            FROM cases
            WHERE id = ?
            """,
            (case_ids[1],),
        ).fetchone()

    assert successful_case["status"] == "ocr_done"
    assert (
        successful_case["ocr_id_number"]
        == "TEST-ID-OCR-001"
    )
    assert (
        successful_case["ocr_full_name"]
        == "OCR Result Applicant"
    )
    assert successful_case["ocr_confidence"] == 0.96
    assert successful_case["ocr_attempts"] == 2
    assert successful_case["failure_reason"] is None

    assert failed_case["status"] == "ocr_failed"
    assert failed_case["failure_reason"] == "scan is unreadable"
    assert failed_case["ocr_attempts"] == 1


def test_process_missing_batch_returns_404(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_PATH", str(database_path))

    with TestClient(app) as client:
        response = client.post(
            "/api/batches/999999/process"
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "batch not found"


def test_reprocessing_batch_skips_finished_cases(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_PATH", str(database_path))

    call_count = 0

    def fake_parse(case_ref, image_ref):
        nonlocal call_count
        call_count += 1

        return OCRResult(
            success=True,
            fields={
                "id_number": "TEST-ID-OCR-001",
                "full_name": "OCR Result Applicant",
                "dob": "1990-01-01",
                "issue_date": "2020-01-01",
                "confidence": 0.96,
            },
            failure_reason=None,
            attempts=1,
        )

    monkeypatch.setattr(
        "app.ocr_processor.parse_identity_card",
        fake_parse,
    )

    with TestClient(app) as client:
        batch_id, _ = insert_batch_with_cases()

        first_response = client.post(
            f"/api/batches/{batch_id}/process"
        )

        second_response = client.post(
            f"/api/batches/{batch_id}/process"
        )

    assert first_response.status_code == 202
    assert call_count == 2

    assert second_response.status_code == 202
    assert second_response.json()["pending_count"] == 0
    assert second_response.json()["processing_started"] is False


def test_interrupted_pending_case_can_be_processed_again(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_PATH", str(database_path))

    def fake_parse(case_ref, image_ref):
        return OCRResult(
            success=True,
            fields={
                "id_number": "TEST-ID-RECOVERED",
                "full_name": "Recovered Applicant",
                "dob": "1990-01-01",
                "issue_date": "2020-01-01",
                "confidence": 0.93,
            },
            failure_reason=None,
            attempts=1,
        )

    monkeypatch.setattr(
        "app.ocr_processor.parse_identity_card",
        fake_parse,
    )

    with TestClient(app) as client:
        batch_id, case_ids = insert_batch_with_cases()

        with get_connection() as connection:
            connection.execute(
                """
                UPDATE cases
                SET status = 'ocr_done'
                WHERE id = ?
                """,
                (case_ids[0],),
            )

        response = client.post(
            f"/api/batches/{batch_id}/process"
        )

    assert response.status_code == 202
    assert response.json()["pending_count"] == 1

    with get_connection() as connection:
        recovered_case = connection.execute(
            """
            SELECT status, ocr_id_number
            FROM cases
            WHERE id = ?
            """,
            (case_ids[1],),
        ).fetchone()

    assert recovered_case["status"] == "ocr_done"
    assert (
        recovered_case["ocr_id_number"]
        == "TEST-ID-RECOVERED"
    )


def test_case_list_returns_stored_ocr_fields(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_PATH", str(database_path))

    def fake_parse(case_ref, image_ref):
        return OCRResult(
            success=True,
            fields={
                "id_number": "TEST-ID-LIST-001",
                "full_name": "Listed OCR Applicant",
                "dob": "1990-01-01",
                "issue_date": "2020-01-01",
                "confidence": 0.95,
            },
            failure_reason=None,
            attempts=2,
        )

    monkeypatch.setattr(
        "app.ocr_processor.parse_identity_card",
        fake_parse,
    )

    with TestClient(app) as client:
        batch_id, _ = insert_batch_with_cases()

        process_response = client.post(
            f"/api/batches/{batch_id}/process"
        )

        list_response = client.get(
            f"/api/batches/{batch_id}/cases",
            params={
                "status": "ocr_done",
                "page": 1,
                "page_size": 10,
            },
        )

    assert process_response.status_code == 202
    assert list_response.status_code == 200

    cases = list_response.json()["cases"]

    assert len(cases) == 2
    assert cases[0]["status"] == "ocr_done"
    assert cases[0]["ocr_id_number"] == "TEST-ID-LIST-001"
    assert cases[0]["ocr_full_name"] == "Listed OCR Applicant"
    assert cases[0]["ocr_dob"] == "1990-01-01"
    assert cases[0]["ocr_issue_date"] == "2020-01-01"
    assert cases[0]["ocr_confidence"] == 0.95
    assert cases[0]["ocr_attempts"] == 2
