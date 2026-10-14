"""API tests for importing account application batches."""

import json

from fastapi.testclient import TestClient

from app.database import get_connection
from app.main import app


VALID_HEADER = (
    "case_ref,applicant_name,id_number,"
    "dob,issue_date,image_ref\n"
)


def test_import_batch_returns_counts_and_rejection_reasons(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_PATH", str(database_path))

    csv_content = VALID_HEADER + (
        "APPL-001,Valid Applicant,TEST-ID-001,"
        "1990-01-01,2020-01-01,id_scan_001.jpg\n"
        "APPL-002,,TEST-ID-002,"
        "1991-02-02,2021-02-02,id_scan_002.jpg\n"
        "APPL-003,Invalid Date,TEST-ID-003,"
        "1992-13-03,2022-03-03,id_scan_003.jpg\n"
        "APPL-001,Duplicate Applicant,TEST-ID-004,"
        "1993-04-04,2023-04-04,id_scan_004.jpg\n"
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/batches",
            files={
                "file": (
                    "applications.csv",
                    csv_content,
                    "text/csv",
                )
            },
        )

    assert response.status_code == 201

    body = response.json()

    assert body["batch_id"] == 1
    assert body["source_filename"] == "applications.csv"
    assert body["accepted_count"] == 1
    assert body["rejected_count"] == 3
    assert len(body["rejected_rows"]) == 3

    all_reasons = [
        reason
        for rejected in body["rejected_rows"]
        for reason in rejected["reasons"]
    ]

    assert "applicant_name is required" in all_reasons
    assert (
        "dob must be a valid date in YYYY-MM-DD format"
        in all_reasons
    )
    assert "duplicate case_ref: APPL-001" in all_reasons

    with get_connection() as connection:
        case_count = connection.execute(
            "SELECT COUNT(*) AS count FROM cases"
        ).fetchone()["count"]

        rejected_count = connection.execute(
            "SELECT COUNT(*) AS count FROM rejected_rows"
        ).fetchone()["count"]

    assert case_count == 1
    assert rejected_count == 3


def test_import_rejects_wrong_csv_header(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_PATH", str(database_path))

    csv_content = (
        "case_ref,applicant_name\n"
        "APPL-001,Test Applicant\n"
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/batches",
            files={
                "file": (
                    "applications.csv",
                    csv_content,
                    "text/csv",
                )
            },
        )

    assert response.status_code == 400
    assert "CSV header must contain exactly" in response.json()["detail"]


def test_import_rejects_empty_file(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_PATH", str(database_path))

    with TestClient(app) as client:
        response = client.post(
            "/api/batches",
            files={
                "file": (
                    "applications.csv",
                    b"",
                    "text/csv",
                )
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "uploaded CSV file is empty"


def test_rejected_rows_are_stored_with_reasons(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_PATH", str(database_path))

    csv_content = VALID_HEADER + (
        "APPL-001,,TEST-ID-001,"
        "1990-01-01,2020-01-01,id_scan_001.jpg\n"
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/batches",
            files={
                "file": (
                    "applications.csv",
                    csv_content,
                    "text/csv",
                )
            },
        )

    assert response.status_code == 201

    with get_connection() as connection:
        rejected = connection.execute(
            """
            SELECT row_number, reasons
            FROM rejected_rows
            """
        ).fetchone()

    assert rejected is not None
    assert rejected["row_number"] == 2
    assert "applicant_name is required" in json.loads(
        rejected["reasons"]
    )


def test_get_batch_details_returns_status_counts(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_PATH", str(database_path))

    csv_content = VALID_HEADER + (
        "APPL-001,Applicant One,TEST-ID-001,"
        "1990-01-01,2020-01-01,id_scan_001.jpg\n"
        "APPL-002,Applicant Two,TEST-ID-002,"
        "1991-02-02,2021-02-02,id_scan_002.jpg\n"
        "APPL-003,,TEST-ID-003,"
        "1992-03-03,2022-03-03,id_scan_003.jpg\n"
    )

    with TestClient(app) as client:
        upload_response = client.post(
            "/api/batches",
            files={
                "file": (
                    "applications.csv",
                    csv_content,
                    "text/csv",
                )
            },
        )

        batch_id = upload_response.json()["batch_id"]
        response = client.get(f"/api/batches/{batch_id}")

    assert response.status_code == 200

    body = response.json()

    assert body["batch_id"] == batch_id
    assert body["accepted_count"] == 2
    assert body["rejected_count"] == 1
    assert body["status_counts"]["pending"] == 2
    assert len(body["rejected_rows"]) == 1
    assert body["rejected_rows"][0]["row_number"] == 4


def test_list_batch_cases_supports_filtering_and_pagination(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_PATH", str(database_path))

    csv_content = VALID_HEADER + (
        "APPL-001,Applicant One,TEST-ID-001,"
        "1990-01-01,2020-01-01,id_scan_001.jpg\n"
        "APPL-002,Applicant Two,TEST-ID-002,"
        "1991-02-02,2021-02-02,id_scan_002.jpg\n"
        "APPL-003,Applicant Three,TEST-ID-003,"
        "1992-03-03,2022-03-03,id_scan_003.jpg\n"
    )

    with TestClient(app) as client:
        upload_response = client.post(
            "/api/batches",
            files={
                "file": (
                    "applications.csv",
                    csv_content,
                    "text/csv",
                )
            },
        )

        batch_id = upload_response.json()["batch_id"]

        first_page = client.get(
            f"/api/batches/{batch_id}/cases",
            params={
                "status": "pending",
                "page": 1,
                "page_size": 2,
            },
        )

        second_page = client.get(
            f"/api/batches/{batch_id}/cases",
            params={
                "status": "pending",
                "page": 2,
                "page_size": 2,
            },
        )

    assert first_page.status_code == 200
    assert first_page.json()["total"] == 3
    assert len(first_page.json()["cases"]) == 2
    assert first_page.json()["page"] == 1

    assert second_page.status_code == 200
    assert second_page.json()["total"] == 3
    assert len(second_page.json()["cases"]) == 1
    assert second_page.json()["page"] == 2

    for case in first_page.json()["cases"]:
        assert case["status"] == "pending"


def test_missing_batch_returns_404(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_PATH", str(database_path))

    with TestClient(app) as client:
        batch_response = client.get("/api/batches/999999")
        cases_response = client.get(
            "/api/batches/999999/cases"
        )

    assert batch_response.status_code == 404
    assert batch_response.json()["detail"] == "batch not found"

    assert cases_response.status_code == 404
    assert cases_response.json()["detail"] == "batch not found"


def test_invalid_case_status_returns_400(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_PATH", str(database_path))

    csv_content = VALID_HEADER + (
        "APPL-001,Applicant One,TEST-ID-001,"
        "1990-01-01,2020-01-01,id_scan_001.jpg\n"
    )

    with TestClient(app) as client:
        upload_response = client.post(
            "/api/batches",
            files={
                "file": (
                    "applications.csv",
                    csv_content,
                    "text/csv",
                )
            },
        )

        batch_id = upload_response.json()["batch_id"]

        response = client.get(
            f"/api/batches/{batch_id}/cases",
            params={"status": "wrong_status"},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "invalid case status"
