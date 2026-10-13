"""Validation helpers for imported account application rows."""

from datetime import datetime
from typing import Optional


REQUIRED_FIELDS = (
    "case_ref",
    "applicant_name",
    "id_number",
    "dob",
    "issue_date",
    "image_ref",
)


def parse_date(value: str, field_name: str) -> tuple[Optional[str], Optional[str]]:
    """Validate a YYYY-MM-DD date and return a normalized value or an error."""

    value = value.strip()

    if not value:
        return None, f"{field_name} is required"

    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return None, f"{field_name} must be a valid date in YYYY-MM-DD format"

    return parsed.date().isoformat(), None


def validate_application_row(
    row: dict[str, str],
    seen_case_refs: set[str],
) -> tuple[Optional[dict[str, str]], list[str]]:
    """Validate and normalize one imported application row."""

    errors: list[str] = []
    normalized: dict[str, str] = {}

    for field in REQUIRED_FIELDS:
        value = (row.get(field) or "").strip()
        normalized[field] = value

        if not value:
            errors.append(f"{field} is required")

    case_ref = normalized["case_ref"]

    if case_ref:
        if case_ref in seen_case_refs:
            errors.append(f"duplicate case_ref: {case_ref}")
        else:
            seen_case_refs.add(case_ref)

    dob, dob_error = parse_date(normalized["dob"], "dob")
    issue_date, issue_date_error = parse_date(
        normalized["issue_date"],
        "issue_date",
    )

    if dob_error:
        errors.append(dob_error)
    else:
        normalized["dob"] = dob

    if issue_date_error:
        errors.append(issue_date_error)
    else:
        normalized["issue_date"] = issue_date

    if dob and issue_date and issue_date < dob:
        errors.append("issue_date cannot be earlier than dob")

    if errors:
        return None, errors

    return normalized, []
