#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKUP_DIR="${DEPLOY_DIR}/backups"

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_NAME="app-${TIMESTAMP}.db"
CONTAINER_BACKUP="/tmp/${BACKUP_NAME}"

mkdir -p "${BACKUP_DIR}"

cd "${DEPLOY_DIR}"

if ! docker compose ps --status running api | grep -q "api"; then
    echo "Error: API container is not running." >&2
    exit 1
fi

docker compose exec -T api \
    python - "${CONTAINER_BACKUP}" <<'PY'
import sqlite3
import sys

source_path = "/data/app.db"
destination_path = sys.argv[1]

source = sqlite3.connect(source_path)
destination = sqlite3.connect(destination_path)

try:
    source.backup(destination)
finally:
    destination.close()
    source.close()
PY

docker compose cp \
    "api:${CONTAINER_BACKUP}" \
    "${BACKUP_DIR}/${BACKUP_NAME}" >/dev/null

docker compose exec -T api rm -f "${CONTAINER_BACKUP}"

backup_count=0

while IFS= read -r backup_file; do
    backup_count=$((backup_count + 1))

    if [ "${backup_count}" -gt 7 ]; then
        rm -f "${backup_file}"
    fi
done < <(
    find "${BACKUP_DIR}" \
        -type f \
        -name 'app-*.db' \
        -print \
        | sort -r
)

echo "Backup created:"
echo "${BACKUP_DIR}/${BACKUP_NAME}"

echo "Retained backups:"
find "${BACKUP_DIR}" \
    -type f \
    -name 'app-*.db' \
    -print \
    | sort -r
