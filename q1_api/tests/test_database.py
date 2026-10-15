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


def test_cases_table_contains_ocr_columns(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_PATH", str(database_path))

    init_database()

    with get_connection() as connection:
        columns = connection.execute(
            "PRAGMA table_info(cases)"
        ).fetchall()

    column_names = {
        column["name"]
        for column in columns
    }

    assert "ocr_id_number" in column_names
    assert "ocr_full_name" in column_names
    assert "ocr_dob" in column_names
    assert "ocr_issue_date" in column_names
    assert "ocr_confidence" in column_names
    assert "ocr_attempts" in column_names


def test_existing_database_is_upgraded(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "old.db"
    monkeypatch.setenv("DATABASE_PATH", str(database_path))

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE batches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_filename TEXT NOT NULL,
                accepted_count INTEGER NOT NULL DEFAULT 0,
                rejected_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE cases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_id INTEGER NOT NULL,
                case_ref TEXT NOT NULL,
                applicant_name TEXT NOT NULL,
                id_number TEXT NOT NULL,
                dob TEXT NOT NULL,
                issue_date TEXT NOT NULL,
                image_ref TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                failure_reason TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (batch_id) REFERENCES batches(id)
                    ON DELETE CASCADE,
                UNIQUE (batch_id, case_ref)
            )
            """
        )

    init_database()

    with get_connection() as connection:
        columns = connection.execute(
            "PRAGMA table_info(cases)"
        ).fetchall()

    column_names = {
        column["name"]
        for column in columns
    }

    assert "ocr_id_number" in column_names
    assert "ocr_full_name" in column_names
    assert "ocr_dob" in column_names
    assert "ocr_issue_date" in column_names
    assert "ocr_confidence" in column_names
    assert "ocr_attempts" in column_names


def test_export_tables_are_created(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_PATH", str(database_path))

    init_database()

    with get_connection() as connection:
        table_rows = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
            """
        ).fetchall()

        export_columns = connection.execute(
            "PRAGMA table_info(exports)"
        ).fetchall()

    table_names = {
        row["name"]
        for row in table_rows
    }

    column_names = {
        row["name"]
        for row in export_columns
    }

    assert "exports" in table_names
    assert "export_cases" in table_names
    assert "idempotency_key" in column_names
    assert "file_content" in column_names
    assert "delivery_status" in column_names
    assert "delivery_receipt" in column_names
    assert "delivery_attempts" in column_names


def test_export_idempotency_key_must_be_unique(
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
            ("export_test.csv",),
        )
        batch_id = cursor.lastrowid

        export_values = (
            batch_id,
            "EXPORT-001.csv",
            b"case_ref\nAPPL-001\n",
            "export-key-001",
            1,
        )

        connection.execute(
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
            export_values,
        )

        try:
            connection.execute(
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
                export_values,
            )
        except sqlite3.IntegrityError:
            duplicate_was_rejected = True
        else:
            duplicate_was_rejected = False

    assert duplicate_was_rejected is True
