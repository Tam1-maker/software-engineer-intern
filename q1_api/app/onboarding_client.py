"""HTTP client for the account-opening ingestion service."""

import os
import time
from dataclasses import dataclass

import httpx


DEFAULT_ONBOARDING_URL = "http://localhost:9200/ingest"
DEFAULT_TIMEOUT_SECONDS = 3.0
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BACKOFF_SECONDS = 0.25


@dataclass(frozen=True)
class DeliveryResult:
    """Result of delivering one export."""

    success: bool
    receipt: dict | None
    failure_reason: str | None
    attempts: int


def get_onboarding_url() -> str:
    """Return the configured account-opening endpoint."""

    return os.getenv(
        "ONBOARDING_URL",
        DEFAULT_ONBOARDING_URL,
    )


def deliver_export(
    file_name: str,
    file_bytes: bytes,
    idempotency_key: str,
    *,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    backoff_seconds: float = DEFAULT_BACKOFF_SECONDS,
) -> DeliveryResult:
    """Deliver an export using bounded retries."""

    headers = {
        "Idempotency-Key": idempotency_key,
        "X-File-Name": file_name,
        "Content-Type": "text/csv",
    }

    last_reason = "account-opening delivery failed"

    for attempt in range(1, max_attempts + 1):
        try:
            response = httpx.post(
                get_onboarding_url(),
                content=file_bytes,
                headers=headers,
                timeout=timeout_seconds,
            )
        except httpx.TimeoutException:
            last_reason = (
                "account-opening response timed out after "
                f"{timeout_seconds} seconds"
            )
        except httpx.RequestError as exc:
            last_reason = (
                f"account-opening connection error: {exc}"
            )
        else:
            if response.status_code == 200:
                return DeliveryResult(
                    success=True,
                    receipt=response.json(),
                    failure_reason=None,
                    attempts=attempt,
                )

            error_message = _extract_error_message(response)

            if response.status_code == 400:
                return DeliveryResult(
                    success=False,
                    receipt=None,
                    failure_reason=error_message,
                    attempts=attempt,
                )

            if response.status_code >= 500:
                last_reason = error_message
            else:
                return DeliveryResult(
                    success=False,
                    receipt=None,
                    failure_reason=error_message,
                    attempts=attempt,
                )

        if attempt < max_attempts:
            delay = backoff_seconds * (2 ** (attempt - 1))
            time.sleep(delay)

    return DeliveryResult(
        success=False,
        receipt=None,
        failure_reason=(
            f"{last_reason}; retries exhausted "
            f"after {max_attempts} attempts"
        ),
        attempts=max_attempts,
    )


def _extract_error_message(response: httpx.Response) -> str:
    """Extract a staff-visible error from a response."""

    try:
        body = response.json()
    except ValueError:
        return (
            "account-opening service returned HTTP "
            f"{response.status_code}"
        )

    if isinstance(body, dict):
        error = body.get("error") or body.get("detail")
        if error:
            return str(error)

    return (
        "account-opening service returned HTTP "
        f"{response.status_code}"
    )
