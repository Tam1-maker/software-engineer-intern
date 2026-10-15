"""Tests for the account-opening delivery client."""

import httpx

from app.onboarding_client import deliver_export


def test_successful_delivery_returns_receipt(monkeypatch):
    captured_request = {}

    def fake_post(url, content, headers, timeout):
        captured_request["content"] = content
        captured_request["headers"] = headers

        return httpx.Response(
            200,
            json={
                "delivery_id": "DLV-0001",
                "idempotency_key": "export-key-001",
                "file_name": "EXPORT-001.csv",
                "sha256": "test-hash",
                "ingested_at": 1234567890,
                "attempts": 1,
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    result = deliver_export(
        file_name="EXPORT-001.csv",
        file_bytes=b"case_ref\nAPPL-001\n",
        idempotency_key="export-key-001",
    )

    assert result.success is True
    assert result.attempts == 1
    assert result.failure_reason is None
    assert result.receipt["delivery_id"] == "DLV-0001"

    assert (
        captured_request["headers"]["Idempotency-Key"]
        == "export-key-001"
    )
    assert (
        captured_request["headers"]["X-File-Name"]
        == "EXPORT-001.csv"
    )
    assert (
        captured_request["content"]
        == b"case_ref\nAPPL-001\n"
    )


def test_http_500_is_retried_with_same_key(monkeypatch):
    attempt_count = 0
    observed_keys = []

    def fake_post(url, content, headers, timeout):
        nonlocal attempt_count
        attempt_count += 1
        observed_keys.append(headers["Idempotency-Key"])

        if attempt_count < 3:
            return httpx.Response(
                500,
                json={"error": "temporary failure"},
            )

        return httpx.Response(
            200,
            json={
                "delivery_id": "DLV-0002",
                "idempotency_key": "export-key-002",
                "file_name": "EXPORT-002.csv",
                "sha256": "test-hash",
                "ingested_at": 1234567890,
                "attempts": 1,
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(
        "app.onboarding_client.time.sleep",
        lambda _: None,
    )

    result = deliver_export(
        file_name="EXPORT-002.csv",
        file_bytes=b"test",
        idempotency_key="export-key-002",
    )

    assert result.success is True
    assert result.attempts == 3
    assert attempt_count == 3
    assert observed_keys == [
        "export-key-002",
        "export-key-002",
        "export-key-002",
    ]


def test_timeout_retry_uses_same_key(monkeypatch):
    attempt_count = 0
    observed_keys = []

    def fake_post(url, content, headers, timeout):
        nonlocal attempt_count
        attempt_count += 1
        observed_keys.append(headers["Idempotency-Key"])

        if attempt_count == 1:
            raise httpx.ReadTimeout(
                "response was lost"
            )

        return httpx.Response(
            200,
            json={
                "delivery_id": "DLV-0003",
                "idempotency_key": "export-key-003",
                "file_name": "EXPORT-003.csv",
                "sha256": "test-hash",
                "ingested_at": 1234567890,
                "attempts": 2,
                "deduplicated": True,
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(
        "app.onboarding_client.time.sleep",
        lambda _: None,
    )

    result = deliver_export(
        file_name="EXPORT-003.csv",
        file_bytes=b"test",
        idempotency_key="export-key-003",
    )

    assert result.success is True
    assert result.attempts == 2
    assert result.receipt["deduplicated"] is True
    assert observed_keys == [
        "export-key-003",
        "export-key-003",
    ]


def test_http_400_is_not_retried(monkeypatch):
    attempt_count = 0

    def fake_post(url, content, headers, timeout):
        nonlocal attempt_count
        attempt_count += 1

        return httpx.Response(
            400,
            json={
                "error": "missing Idempotency-Key header"
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    result = deliver_export(
        file_name="EXPORT-004.csv",
        file_bytes=b"test",
        idempotency_key="export-key-004",
    )

    assert result.success is False
    assert result.attempts == 1
    assert attempt_count == 1
    assert (
        result.failure_reason
        == "missing Idempotency-Key header"
    )


def test_delivery_obeys_bounded_retry_limit(monkeypatch):
    attempt_count = 0

    def fake_post(url, content, headers, timeout):
        nonlocal attempt_count
        attempt_count += 1
        raise httpx.ReadTimeout("response timed out")

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(
        "app.onboarding_client.time.sleep",
        lambda _: None,
    )

    result = deliver_export(
        file_name="EXPORT-005.csv",
        file_bytes=b"test",
        idempotency_key="export-key-005",
        max_attempts=3,
    )

    assert result.success is False
    assert result.attempts == 3
    assert attempt_count == 3
    assert "retries exhausted after 3 attempts" in (
        result.failure_reason
    )
