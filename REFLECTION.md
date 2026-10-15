# Reflection

## Database choice

I used SQLite rather than MongoDB. The exercise runs as a single API service and does not require distributed database access, so SQLite keeps local development, automated testing, container deployment, persistence, backup, and restoration straightforward.

The database path is configured using `DATABASE_PATH`. Local development defaults to `q1_api/app.db`, while Docker uses `/data/app.db` on a named persistent volume.

Database initialization supports upgrading an existing Q1 database by checking the `cases` table and adding missing OCR columns. This allowed the Q2 implementation to extend the existing application without replacing the original database.

## Q1 design

CSV import uses multipart file upload. Each row is validated independently, and rejected rows include their original row number and all detected reasons.

The review transition rules are defined centrally in `app/transitions.py`. Valid review transitions are:

- `ocr_done` to `stage1_approved`
- `ocr_done` to `stage1_rejected`
- `stage1_approved` to `stage2_approved`
- `stage1_approved` to `stage2_rejected`

Invalid transitions return HTTP 409 with a staff-visible reason. Keeping these rules in one location makes a future state-machine change easier to implement and test.

## OCR processing approach

`POST /api/batches/{batch_id}/process` uses FastAPI background tasks so the request returns HTTP 202 before all cases finish. The worker selects only `pending` cases. Before processing each case, it checks the current status again.

A successful OCR request stores the parsed identity fields and changes the case to `ocr_done`. A permanent or exhausted failure stores a reason and changes the case to `ocr_failed`.

This implementation uses an in-process background task. It is sufficient for the exercise and local deployment, but a production system with multiple API replicas should use a durable task queue such as Celery, Redis Queue, or a managed message service.

## OCR timeout, retry, and recovery

The OCR client uses:

- 3-second request timeout
- Maximum 3 attempts
- Exponential backoff of 0.25 seconds and 0.5 seconds
- Retry for HTTP 500, timeout, and connection failures
- No retry for HTTP 400 or HTTP 422

HTTP 422 represents an unreadable scan, so retrying the same image cannot resolve the problem. Exhausted retries produce a staff-visible failure reason.

The mock OCR service was tested directly before implementation. A readable test image returned HTTP 200 with deterministic identity fields. An image reference containing `badscan` returned HTTP 422 with a scan-quality reason.

During the Docker smoke test, 43 accepted cases were processed:

- 36 reached `ocr_done`
- 7 reached `ocr_failed`

The measured smoke-test results are observations from that run, not the configured failure probabilities.

If a worker stops before a case is updated, the case remains `pending`. Calling the batch processing endpoint again processes remaining pending cases. Already completed cases are skipped, so rerunning processing does not replace stored OCR results.

## Export and idempotent delivery

An export includes exactly the cases in `stage2_approved`. After successful delivery, those cases move to `exported`, so a later export does not include them again.

The CSV bytes are generated deterministically. The idempotency key contains the batch identity and SHA-256 hash of the export content. The same stored file and key are reused for every delivery attempt of that export. A different export produces different content and therefore a different key.

The mock account-opening service was tested with a five-second diagnostic timeout. The first request timed out after ingestion. Retrying with the same idempotency key returned delivery `DLV-0001`, reported `deduplicated: true`, and showed two attempts. The debug delivery endpoint contained only one ingestion record.

The Docker smoke test also produced one delivered export:

- Export ID: 1
- Delivery ID: DLV-0001
- Exported cases: 36

After delivery, a second export returned no new stage-two-approved cases.

## Deployment and health checks

Docker Compose runs the fixed services:

- `api`
- `mock_ocr`
- `mock_onboarding`
- `nginx`

The API uses Python 3.12 in the container. Nginx exposes host port 8080 and routes `/api/*` to the API and `/ocr/*` to the mock OCR service without removing the OCR path prefix.

`/api/health` is the liveness endpoint. `/api/ready` checks SQLite reachability and returns HTTP 503 when the database cannot be reached.

Compose health checks and `depends_on` with `service_healthy` control startup order. No fixed startup sleep is used.

## Backup and restoration

The backup script uses the SQLite online backup API while the application is running. Backups are copied from the API container into `q3_deploy/backups/`.

The retention test created more than seven timestamped backups. After the script completed, exactly seven backup files remained.

The newest backup passed:

```text
Restoration was tested by stopping the API and Nginx, copying a selected backup to /data/app.db, restarting the services, and checking /api/ready. The restored deployment returned HTTP 200 with the database reported as reachable.

Testing and known limitations

The final pytest suite contains 48 passing tests. It covers:

CSV validation and rejected-row reasons
Database creation and schema upgrades
Batch details, filtering, and pagination
Successful and invalid review transitions
OCR timeout, retry, failure, and recovery behavior
Export selection and prevention of repeated exports
Stable idempotency keys across delivery retries
Delivery receipt persistence

The current test run also reports one Starlette deprecation warning from the installed FastAPI test client dependency. It does not cause a test failure.

Known limitations:

Background processing runs inside the API process rather than a durable external worker.
The deployment uses one API replica because SQLite is the selected database.
Authentication and authorization are outside the core exercise scope.
The optional bonus task was not implemented in order to prioritize the required workflow, failure handling, tests, and operations.

## Testing and known limitations

The final pytest suite contains 48 passing tests. It covers:

- CSV validation and rejected-row reasons
- Database creation and schema upgrades
- Batch details, filtering, and pagination
- Successful and invalid review transitions
- OCR timeout, retry, failure, and recovery behavior
- Export selection and prevention of repeated exports
- Stable idempotency keys across delivery retries
- Delivery receipt persistence

The current test run also reports one Starlette deprecation warning from the installed FastAPI test client dependency. It does not cause a test failure.

Known limitations:

- Background processing runs inside the API process rather than a durable external worker.
- The deployment uses one API replica because SQLite is the selected database.
- Authentication and authorization are outside the core exercise scope.
- The optional bonus task was not implemented because the required workflow, failure handling, tests, and operational reliability were prioritized.
