# Deployment Runbook

## Configuration and startup

Requirements: Docker Desktop with Docker Compose v2 and host port 8080 available.

From `q3_deploy/` run:

    cp .env.example .env
    docker compose up --build -d
    docker compose ps

The required services are `api`, `mock_ocr`, `mock_onboarding`, and `nginx`. All four should be healthy.

Verify:

    curl -i http://localhost:8080/api/health
    curl -i http://localhost:8080/api/ready
    bash scripts/smoke_test.sh

## Log access

    docker compose logs --tail=100
    docker compose logs -f
    docker compose logs --tail=100 api
    docker compose logs --tail=100 mock_ocr
    docker compose logs --tail=100 mock_onboarding
    docker compose logs --tail=100 nginx

## OCR failure diagnosis

Check batch status and failed cases:

    curl -sS http://localhost:8080/api/batches/BATCH_ID
    curl -sS "http://localhost:8080/api/batches/BATCH_ID/cases?status=ocr_failed&page=1&page_size=100"

Inspect OCR outcomes:

    docker compose exec mock_ocr python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:9100/debug/requests').read().decode())"

`unreadable` is permanent. `error_500` and `hang` are transient and receive bounded retries. Reprocess pending cases with:

    curl -X POST http://localhost:8080/api/batches/BATCH_ID/process

## Backup

Create an online SQLite backup:

    bash scripts/backup.sh

Backups are stored in `q3_deploy/backups/`; only the seven newest `app-*.db` files are retained.

Verify the latest backup:

    LATEST_BACKUP="$(find backups -type f -name 'app-*.db' | sort -r | head -n 1)"
    sqlite3 "${LATEST_BACKUP}" "PRAGMA integrity_check;"

Expected result: `ok`.

## Restore

    docker compose stop nginx api
    BACKUP_FILE="$(find backups -type f -name 'app-*.db' | sort -r | head -n 1)"
    sqlite3 "${BACKUP_FILE}" "PRAGMA integrity_check;"
    docker compose up -d --no-deps api
    docker compose cp "${BACKUP_FILE}" api:/data/app.db
    docker compose restart api
    docker compose up -d nginx
    curl -i http://localhost:8080/api/ready

## Shutdown

Keep persistent data:

    docker compose down

Remove the persistent volume only when data is no longer required:

    docker compose down -v
