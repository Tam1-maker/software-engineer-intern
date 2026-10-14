"""HTTP client for the external OCR service."""

import os
import time
from dataclasses import dataclass

import httpx


DEFAULT_OCR_URL = "http://localhost:9100/ocr/parse"
DEFAULT_TIMEOUT_SECONDS = 3.0
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BACKOFF_SECONDS = 0.25


@dataclass(frozen=True)
class OCRResult:
    """Result of processing one identity-card image."""

    success: bool
    fields: dict | None
    failure_reason: str | None
    attempts: int


def get_ocr_url() -> str:
    """Return the configured OCR endpoint."""

    return os.getenv("OCR_URL", DEFAULT_OCR_URL)


def parse_identity_card(
    case_ref: str,
    image_ref: str,
    *,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    backoff_seconds: float = DEFAULT_BACKOFF_SECONDS,
) -> OCRResult:
    """Call OCR with bounded retries and exponential backoff."""

    payload = {
        "case_id": case_ref,
        "image_ref": image_ref,
    }

    last_reason = "OCR processing failed"

    for attempt in range(1, max_attempts + 1):
        try:
            response = httpx.post(
                get_ocr_url(),
                json=payload,
                timeout=timeout_seconds,
            )
        except httpx.TimeoutException:
            last_reason = (
                f"OCR request timed out after "
                f"{timeout_seconds} seconds"
            )
        except httpx.RequestError as exc:
            last_reason = f"OCR connection error: {exc}"
        else:
            if response.status_code == 200:
                return OCRResult(
                    success=True,
                    fields=response.json(),
                    failure_reason=None,
                    attempts=attempt,
                )

            error_message = _extract_error_message(response)

            if response.status_code == 422:
                return OCRResult(
                    success=False,
                    fields=None,
                    failure_reason=error_message,
                    attempts=attempt,
                )

            if response.status_code == 400:
                return OCRResult(
                    success=False,
                    fields=None,
                    failure_reason=error_message,
                    attempts=attempt,
                )

            if response.status_code >= 500:
                last_reason = error_message
            else:
                return OCRResult(
                    success=False,
                    fields=None,
                    failure_reason=error_message,
                    attempts=attempt,
                )

        if attempt < max_attempts:
            delay = backoff_seconds * (2 ** (attempt - 1))
            time.sleep(delay)

    return OCRResult(
        success=False,
        fields=None,
        failure_reason=(
            f"{last_reason}; retries exhausted "
            f"after {max_attempts} attempts"
        ),
        attempts=max_attempts,
    )


def _extract_error_message(response: httpx.Response) -> str:
    """Extract a staff-visible error from an OCR response."""

    try:
        body = response.json()
    except ValueError:
        return (
            f"OCR service returned HTTP "
            f"{response.status_code}"
        )

    if isinstance(body, dict):
        error = body.get("error") or body.get("detail")
        if error:
            return str(error)

    return f"OCR service returned HTTP {response.status_code}"
