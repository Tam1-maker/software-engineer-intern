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


def init_database() -> None:
    """Create the application tables if they do not already exist."""

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

            CREATE INDEX IF NOT EXISTS idx_cases_batch_id
            ON cases(batch_id);

            CREATE INDEX IF NOT EXISTS idx_cases_status
            ON cases(status);
            """
        )

