"""SQLite database setup and connection helpers."""

import os
import sqlite3
from pathlib import Path


DEFAULT_DATABASE_PATH = Path(__file__).resolve().parent.parent / "app.db"


def get_database_path() -> str:
    """Return the configured SQLite database path."""

    return os.getenv("DATABASE_PATH", str(DEFAULT_DATABASE_PATH))


def get_connection() -> sqlite3.Connection:
    """Create a SQLite connection with useful defaults."""

    connection = sqlite3.connect(get_database_path())
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _ensure_column(
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str,
    definition: str,
) -> None:
    """Add a column when upgrading an existing SQLite database."""

    columns = connection.execute(
        f"PRAGMA table_info({table_name})"
    ).fetchall()

    existing_names = {
        column["name"]
        for column in columns
    }

    if column_name not in existing_names:
        connection.execute(
            f"""
            ALTER TABLE {table_name}
            ADD COLUMN {column_name} {definition}
            """
        )


def init_database() -> None:
    """Create or upgrade the application database."""

    with get_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS batches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_filename TEXT NOT NULL,
                accepted_count INTEGER NOT NULL DEFAULT 0,
                rejected_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS cases (
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
                ocr_id_number TEXT,
                ocr_full_name TEXT,
                ocr_dob TEXT,
                ocr_issue_date TEXT,
                ocr_confidence REAL,
                ocr_attempts INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (batch_id) REFERENCES batches(id)
                    ON DELETE CASCADE,
                UNIQUE (batch_id, case_ref)
            );

            CREATE TABLE IF NOT EXISTS rejected_rows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_id INTEGER NOT NULL,
                row_number INTEGER NOT NULL,
                raw_data TEXT NOT NULL,
                reasons TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (batch_id) REFERENCES batches(id)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS exports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_id INTEGER NOT NULL,
                file_name TEXT NOT NULL,
                file_content BLOB NOT NULL,
                idempotency_key TEXT NOT NULL UNIQUE,
                case_count INTEGER NOT NULL,
                delivery_status TEXT NOT NULL DEFAULT 'pending',
                delivery_id TEXT,
                delivery_receipt TEXT,
                delivery_attempts INTEGER NOT NULL DEFAULT 0,
                failure_reason TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (batch_id) REFERENCES batches(id)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS export_cases (
                export_id INTEGER NOT NULL,
                case_id INTEGER NOT NULL,
                PRIMARY KEY (export_id, case_id),
                FOREIGN KEY (export_id) REFERENCES exports(id)
                    ON DELETE CASCADE,
                FOREIGN KEY (case_id) REFERENCES cases(id)
                    ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_exports_batch_id
            ON exports(batch_id);

            CREATE INDEX IF NOT EXISTS idx_export_cases_case_id
            ON export_cases(case_id);


            CREATE INDEX IF NOT EXISTS idx_cases_batch_id
            ON cases(batch_id);

            CREATE INDEX IF NOT EXISTS idx_cases_status
            ON cases(status);
            """
        )

        _ensure_column(
            connection,
            "cases",
            "ocr_id_number",
            "TEXT",
        )
        _ensure_column(
            connection,
            "cases",
            "ocr_full_name",
            "TEXT",
        )
        _ensure_column(
            connection,
            "cases",
            "ocr_dob",
            "TEXT",
        )
        _ensure_column(
            connection,
            "cases",
            "ocr_issue_date",
            "TEXT",
        )
        _ensure_column(
            connection,
            "cases",
            "ocr_confidence",
            "REAL",
        )
        _ensure_column(
            connection,
            "cases",
            "ocr_attempts",
            "INTEGER NOT NULL DEFAULT 0",
        )
