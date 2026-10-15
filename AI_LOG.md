# AI Usage Log

## Scope of assistance

Microsoft Copilot assisted throughout the exercise as an interactive development aid.

## Q1 assistance

AI assistance included:

- Explaining the required repository layout and local setup
- Drafting CSV validation, SQLite initialization, and related tests
- Suggesting a centralized review-transition table
- Drafting batch import, query, pagination, and review tests
- Diagnosing Python path and test configuration issues

I verified the behavior by running the entire pytest suite and manually testing the FastAPI endpoints through Swagger.

## Q2 assistance

AI assistance included:

- Interpreting the OCR and account-opening service contracts
- Drafting HTTP clients with explicit timeout, bounded retries, and exponential backoff
- Drafting background OCR processing and recovery tests
- Designing deterministic CSV exports and content-derived idempotency keys
- Drafting delivery-retry tests that verify the same key is reused
- Diagnosing missing FastAPI route registration

I directly tested both mock services with curl. I observed an account-opening timeout after ingestion and confirmed that retrying with the same key returned the original receipt without creating another ingestion.

## Q3 assistance

AI assistance included:

- Drafting the API Dockerfile, Docker Compose configuration, and nginx routing
- Drafting liveness and database-readiness checks
- Diagnosing the unhealthy API container caused by a missing get_connection import
- Diagnosing and correcting the nginx health check
- Drafting the online SQLite backup and seven-file retention script
- Drafting the end-to-end smoke test and operational runbook

I ran Docker Compose locally, verified all four services as healthy, tested nginx routing, ran the smoke test, created and validated backups, and restored a backup successfully.

## Verification and understanding

I reviewed and executed all submitted commands and code. I corrected errors found during execution rather than treating AI output as automatically correct.

Examples of corrections and verification included:

- Fixing the pytest import path
- Repairing malformed copied test code
- Correcting the database-upgrade test to represent the real Q1 schema
- Registering the missing export route
- Importing get_connection for the readiness endpoint
- Updating the nginx health-check command
- Verifying backup integrity with SQLite PRAGMA integrity_check
- Verifying delivery idempotency through the mock debug endpoint

I understand that I may be asked to explain or modify the submitted code during the interview.
