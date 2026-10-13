"""Tests for account application CSV row validation."""

from app.validation import validate_application_row


def valid_row() -> dict[str, str]:
    """Return a valid application row for use in tests."""

    return {
        "case_ref": "APPL-TEST-001",
        "applicant_name": "Test Applicant",
        "id_number": "TEST-ID-999001",
        "dob": "1990-01-15",
        "issue_date": "2020-06-20",
        "image_ref": "id_scan_test.jpg",
    }


def test_valid_row_is_accepted():
    row = valid_row()

    normalized, errors = validate_application_row(row, set())

    assert errors == []
    assert normalized is not None
    assert normalized["case_ref"] == "APPL-TEST-001"
    assert normalized["dob"] == "1990-01-15"
    assert normalized["issue_date"] == "2020-06-20"


def test_missing_applicant_name_is_rejected():
    row = valid_row()
    row["applicant_name"] = ""

    normalized, errors = validate_application_row(row, set())

    assert normalized is None
    assert "applicant_name is required" in errors


def test_invalid_date_is_rejected():
    row = valid_row()
    row["dob"] = "1990-13-15"

    normalized, errors = validate_application_row(row, set())

    assert normalized is None
    assert "dob must be a valid date in YYYY-MM-DD format" in errors


def test_duplicate_case_ref_is_rejected():
    row = valid_row()
    seen_case_refs = {"APPL-TEST-001"}

    normalized, errors = validate_application_row(row, seen_case_refs)

    assert normalized is None
    assert "duplicate case_ref: APPL-TEST-001" in errors


def test_issue_date_before_dob_is_rejected():
    row = valid_row()
    row["dob"] = "2000-01-01"
    row["issue_date"] = "1999-12-31"

    normalized, errors = validate_application_row(row, set())

    assert normalized is None
    assert "issue_date cannot be earlier than dob" in errors
