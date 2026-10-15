#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPOSITORY_ROOT="$(cd "${DEPLOY_DIR}/.." && pwd)"

BASE_URL="${BASE_URL:-http://localhost:8080}"
CSV_FILE="${REPOSITORY_ROOT}/data/account_applications.csv"

export BASE_URL
export CSV_FILE

python3 <<'PY'
import json
import os
import time
import urllib.error
import urllib.request
import uuid


base_url = os.environ["BASE_URL"]
csv_file = os.environ["CSV_FILE"]


def request_json(
    method,
    path,
    body=None,
    headers=None,
    expected=(200,),
):
    request_headers = dict(headers or {})

    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        request_headers["Content-Type"] = "application/json"

    request = urllib.request.Request(
        base_url + path,
        data=data,
        headers=request_headers,
        method=method,
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=30,
        ) as response:
            status = response.status
            content = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        status = exc.code
        content = exc.read().decode("utf-8")

    if status not in expected:
        raise RuntimeError(
            f"{method} {path} returned {status}: {content}"
        )

    return json.loads(content)


def upload_csv():
    boundary = "----SmokeTest" + uuid.uuid4().hex

    with open(csv_file, "rb") as source:
        file_bytes = source.read()

    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; '
        'name="file"; '
        'filename="account_applications.csv"\r\n'
        "Content-Type: text/csv\r\n"
        "\r\n"
    ).encode("utf-8")

    body += file_bytes
    body += f"\r\n--{boundary}--\r\n".encode("utf-8")

    request = urllib.request.Request(
        base_url + "/api/batches",
        data=body,
        headers={
            "Content-Type": (
                f"multipart/form-data; boundary={boundary}"
            ),
        },
        method="POST",
    )

    with urllib.request.urlopen(
        request,
        timeout=30,
    ) as response:
        return json.loads(
            response.read().decode("utf-8")
        )


print("1. Checking API health...")
health = request_json("GET", "/api/health")
ready = request_json("GET", "/api/ready")

assert health["status"] == "ok"
assert ready["status"] == "ready"

print("2. Uploading application batch...")
upload = upload_csv()
batch_id = upload["batch_id"]

print(
    f"   Batch {batch_id}: "
    f"{upload['accepted_count']} accepted, "
    f"{upload['rejected_count']} rejected"
)

print("3. Starting background OCR processing...")
process_result = request_json(
    "POST",
    f"/api/batches/{batch_id}/process",
    expected=(202,),
)

print(
    f"   Pending cases submitted: "
    f"{process_result['pending_count']}"
)

print("4. Waiting for OCR cases to reach final states...")

deadline = time.monotonic() + 180

while True:
    batch = request_json(
        "GET",
        f"/api/batches/{batch_id}",
    )

    pending_count = batch["status_counts"].get(
        "pending",
        0,
    )

    if pending_count == 0:
        break

    if time.monotonic() >= deadline:
        raise RuntimeError(
            "OCR processing did not finish within 180 seconds"
        )

    print(f"   Remaining pending cases: {pending_count}")
    time.sleep(2)

batch = request_json(
    "GET",
    f"/api/batches/{batch_id}",
)

ocr_done_count = batch["status_counts"].get(
    "ocr_done",
    0,
)
ocr_failed_count = batch["status_counts"].get(
    "ocr_failed",
    0,
)

print(
    f"   OCR completed: {ocr_done_count}, "
    f"failed: {ocr_failed_count}"
)

if ocr_done_count == 0:
    raise RuntimeError(
        "Smoke test requires at least one OCR-successful case"
    )

print("5. Retrieving OCR-successful cases...")
cases_result = request_json(
    "GET",
    (
        f"/api/batches/{batch_id}/cases"
        "?status=ocr_done&page=1&page_size=100"
    ),
)

cases = cases_result["cases"]

if not cases:
    raise RuntimeError(
        "No OCR-successful cases were returned"
    )

print("6. Completing stage 1 reviews...")

for case in cases:
    request_json(
        "POST",
        f"/api/cases/{case['id']}/review",
        body={
            "stage": 1,
            "decision": "approve",
        },
    )

print("7. Completing stage 2 reviews...")

for case in cases:
    request_json(
        "POST",
        f"/api/cases/{case['id']}/review",
        body={
            "stage": 2,
            "decision": "approve",
        },
    )

print("8. Exporting and delivering approved cases...")

export_result = request_json(
    "POST",
    f"/api/batches/{batch_id}/export",
)

if export_result.get("delivery_status") != "delivered":
    raise RuntimeError(
        "Export was not delivered successfully: "
        + json.dumps(export_result)
    )

if export_result["case_count"] != len(cases):
    raise RuntimeError(
        "Exported case count does not match reviewed cases"
    )

print("9. Checking that a later export is empty...")

second_export = request_json(
    "POST",
    f"/api/batches/{batch_id}/export",
)

if second_export.get("export_created") is not False:
    raise RuntimeError(
        "A later export incorrectly included old cases"
    )

print()
print("Smoke test passed.")
print(f"Batch ID: {batch_id}")
print(f"OCR successful: {ocr_done_count}")
print(f"OCR failed: {ocr_failed_count}")
print(f"Export ID: {export_result['export_id']}")
print(
    "Delivery ID: "
    f"{export_result['receipt']['delivery_id']}"
)
print(
    "Idempotency key: "
    f"{export_result['idempotency_key']}"
)
PY
