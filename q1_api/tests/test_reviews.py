"""API tests for the two-stage case review workflow."""

from fastapi.testclient import TestClient

from app.database import get_connection
from app.main import app


def insert_case(status: str) -> int:
    """Insert one case and return its database ID."""

    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO batches (source_filename)
            VALUES (?)
            """,
            ("review_test.csv",),
        )
        batch_id = cursor.lastrowid

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
                status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                batch_id,
                "APPL-REVIEW-001",
                "Review Applicant",
                "TEST-ID-REVIEW-001",
                "1990-01-01",
                "2020-01-01",
                "id_scan_review.jpg",
                status,
            ),
        )

        return cursor.lastrowid


def test_successful_case_review_lifecycle(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_PATH", str(database_path))

    with TestClient(app) as client:
        case_id = insert_case("ocr_done")

        stage1_response = client.post(
            f"/api/cases/{case_id}/review",
            json={
                "stage": 1,
                "decision": "approve",
            },
        )

        stage2_response = client.post(
            f"/api/cases/{case_id}/review",
            json={
                "stage": 2,
                "decision": "approve",
            },
        )

    assert stage1_response.status_code == 200
    assert stage1_response.json()["previous_status"] == "ocr_done"
    assert stage1_response.json()["status"] == "stage1_approved"

    assert stage2_response.status_code == 200
    assert (
        stage2_response.json()["previous_status"]
        == "stage1_approved"
    )
    assert stage2_response.json()["status"] == "stage2_approved"

    with get_connection() as connection:
        case = connection.execute(
            """
            SELECT status
            FROM cases
            WHERE id = ?
            """,
            (case_id,),
        ).fetchone()

    assert case["status"] == "stage2_approved"


def test_pending_case_review_returns_409(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_PATH", str(database_path))

    with TestClient(app) as client:
        case_id = insert_case("pending")

        response = client.post(
            f"/api/cases/{case_id}/review",
            json={
                "stage": 1,
                "decision": "approve",
            },
        )

    assert response.status_code == 409
    assert (
        response.json()["detail"]
        == "case must complete OCR before review"
    )


def test_stage2_before_stage1_returns_409(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_PATH", str(database_path))

    with TestClient(app) as client:
        case_id = insert_case("ocr_done")

        response = client.post(
            f"/api/cases/{case_id}/review",
            json={
                "stage": 2,
                "decision": "approve",
            },
        )

    assert response.status_code == 409
    assert (
        response.json()["detail"]
        == "stage 2 review requires stage 1 approval"
    )


def test_ocr_failed_case_review_returns_409(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_PATH", str(database_path))

    with TestClient(app) as client:
        case_id = insert_case("ocr_failed")

        response = client.post(
            f"/api/cases/{case_id}/review",
            json={
                "stage": 1,
                "decision": "approve",
            },
        )

    assert response.status_code == 409
    assert (
        response.json()["detail"]
        == "an OCR-failed case cannot be reviewed"
    )


def test_repeated_stage1_review_returns_409(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_PATH", str(database_path))

    with TestClient(app) as client:
        case_id = insert_case("ocr_done")

        first_response = client.post(
            f"/api/cases/{case_id}/review",
            json={
                "stage": 1,
                "decision": "approve",
            },
        )

        repeated_response = client.post(
            f"/api/cases/{case_id}/review",
            json={
                "stage": 1,
                "decision": "approve",
            },
        )

    assert first_response.status_code == 200
    assert repeated_response.status_code == 409
    assert (
        repeated_response.json()["detail"]
        == "this review stage has already been completed"
    )


def test_rejected_case_cannot_be_reviewed_again(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_PATH", str(database_path))

    with TestClient(app) as client:
        case_id = insert_case("ocr_done")

        rejection_response = client.post(
            f"/api/cases/{case_id}/review",
            json={
                "stage": 1,
                "decision": "reject",
            },
        )

        repeated_response = client.post(
            f"/api/cases/{case_id}/review",
            json={
                "stage": 2,
                "decision": "approve",
            },
        )

    assert rejection_response.status_code == 200
    assert (
        rejection_response.json()["status"]
        == "stage1_rejected"
    )

    assert repeated_response.status_code == 409
    assert (
        repeated_response.json()["detail"]
        == "a rejected case cannot be reviewed again"
    )


def test_missing_case_returns_404(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_PATH", str(database_path))

    with TestClient(app) as client:
        response = client.post(
            "/api/cases/999999/review",
            json={
                "stage": 1,
                "decision": "approve",
            },
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "case not found"


def test_invalid_review_request_returns_422(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_PATH", str(database_path))

    with TestClient(app) as client:
        case_id = insert_case("ocr_done")

        invalid_stage = client.post(
            f"/api/cases/{case_id}/review",
            json={
                "stage": 3,
                "decision": "approve",
            },
        )

        invalid_decision = client.post(
            f"/api/cases/{case_id}/review",
            json={
                "stage": 1,
                "decision": "maybe",
            },
        )

    assert invalid_stage.status_code == 422
    assert (
        invalid_stage.json()["detail"]
        == "stage must be 1 or 2"
    )

    assert invalid_decision.status_code == 422
    assert (
        invalid_decision.json()["detail"]
        == "decision must be approve or reject"
    )
