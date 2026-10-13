"""Tests for SQLite database initialization."""

import sqlite3

from app.database import get_connection, init_database


def test_database_tables_are_created(tmp_path, monkeypatch):
    database_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_PATH", str(database_path))

    init_database()

    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
            """
        ).fetchall()

    table_names = {row["name"] for row in rows}

    assert "batches" in table_names
    assert "cases" in table_names
    assert "rejected_rows" in table_names


def test_new_case_defaults_to_pending(tmp_path, monkeypatch):
    database_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_PATH", str(database_path))

    init_database()

    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO batches (source_filename)
            VALUES (?)
            """,
            ("applications.csv",),
        )
        batch_id = cursor.lastrowid

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
                "APPL-TEST-001",
                "Test Applicant",
                "TEST-ID-999001",
                "1990-01-15",
                "2020-06-20",
                "id_scan_test.jpg",
            ),
        )

        case = connection.execute(
            """
            SELECT *
            FROM cases
            WHERE case_ref = ?
            """,
            ("APPL-TEST-001",),
        ).fetchone()

    assert case is not None
    assert case["status"] == "pending"


def test_duplicate_case_ref_in_same_batch_is_rejected(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_PATH", str(database_path))

    init_database()

    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO batches (source_filename)
            VALUES (?)
            """,
            ("applications.csv",),
        )
        batch_id = cursor.lastrowid

        case_values = (
            batch_id,
            "APPL-TEST-001",
            "Test Applicant",
            "TEST-ID-999001",
            "1990-01-15",
            "2020-06-20",
            "id_scan_test.jpg",
        )

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
            case_values,
        )

        try:
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
                case_values,
            )
        except sqlite3.IntegrityError:
            duplicate_was_rejected = True
        else:
            duplicate_was_rejected = False

    assert duplicate_was_rejected is True
