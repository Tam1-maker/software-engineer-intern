"""Tests for the OCR integration client."""

import httpx

from app.ocr_client import parse_identity_card


def test_successful_ocr_response(monkeypatch):
    def fake_post(url, json, timeout):
        return httpx.Response(
            200,
            json={
                "id_number": "TEST-ID-001",
                "full_name": "Test Applicant",
                "dob": "1990-01-01",
                "issue_date": "2020-01-01",
                "confidence": 0.94,
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    result = parse_identity_card(
        "APPL-001",
        "id_scan_001.jpg",
    )

    assert result.success is True
    assert result.attempts == 1
    assert result.failure_reason is None
    assert result.fields["id_number"] == "TEST-ID-001"


def test_unreadable_scan_is_not_retried(monkeypatch):
    attempt_count = 0

    def fake_post(url, json, timeout):
        nonlocal attempt_count
        attempt_count += 1

        return httpx.Response(
            422,
            json={
                "error": "cannot read identity-card fields"
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    result = parse_identity_card(
        "APPL-002",
        "id_badscan_002.jpg",
    )

    assert result.success is False
    assert result.attempts == 1
    assert attempt_count == 1
    assert (
        result.failure_reason
        == "cannot read identity-card fields"
    )


def test_http_500_is_retried_then_succeeds(monkeypatch):
    attempt_count = 0

    def fake_post(url, json, timeout):
        nonlocal attempt_count
        attempt_count += 1

        if attempt_count < 3:
            return httpx.Response(
                500,
                json={"error": "temporary OCR failure"},
            )

        return httpx.Response(
            200,
            json={
                "id_number": "TEST-ID-003",
                "full_name": "Retry Applicant",
                "dob": "1992-03-03",
                "issue_date": "2022-03-03",
                "confidence": 0.91,
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr("app.ocr_client.time.sleep", lambda _: None)

    result = parse_identity_card(
        "APPL-003",
        "id_scan_003.jpg",
    )

    assert result.success is True
    assert result.attempts == 3
    assert attempt_count == 3


def test_timeout_exhausts_bounded_retries(monkeypatch):
    attempt_count = 0

    def fake_post(url, json, timeout):
        nonlocal attempt_count
        attempt_count += 1
        raise httpx.ReadTimeout("OCR timed out")

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr("app.ocr_client.time.sleep", lambda _: None)

    result = parse_identity_card(
        "APPL-004",
        "id_scan_004.jpg",
        timeout_seconds=1.0,
        max_attempts=3,
    )

    assert result.success is False
    assert result.attempts == 3
    assert attempt_count == 3
    assert "retries exhausted after 3 attempts" in (
        result.failure_reason
    )


def test_http_400_is_not_retried(monkeypatch):
    attempt_count = 0

    def fake_post(url, json, timeout):
        nonlocal attempt_count
        attempt_count += 1

        return httpx.Response(
            400,
            json={"error": "missing image_ref"},
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    result = parse_identity_card(
        "APPL-005",
        "",
    )

    assert result.success is False
    assert result.attempts == 1
    assert attempt_count == 1
    assert result.failure_reason == "missing image_ref"
