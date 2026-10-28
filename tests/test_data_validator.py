"""
test_data_validator.py
======================
Tests for src/data_validator.py
"""

import pandas as pd
import pytest

from src.data_validator import ValidationStatus, validate_dataframe


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def valid_df():
    return pd.DataFrame({
        "record_id":    ["EMP001", "EMP002"],
        "name":         ["Alice Smith", "Bob Jones"],
        "email":        ["alice@example.com", "bob@example.com"],
        "phone":        ["5551234567", "5559876543"],
        "department":   ["Human Resources", "Finance"],
        "joining_date": ["2020-01-15", "2019-03-15"],
        "salary":       [50000.0, 75000.0],
        "city":         ["New York", "Chicago"],
    })


# ---------------------------------------------------------------------------
# 4. Email validation
# ---------------------------------------------------------------------------

class TestEmailValidation:
    def test_valid_email_passes(self, valid_df):
        report = validate_dataframe(valid_df, required_columns=["email"])
        # All should pass (no errors on email for valid rows)
        email_errors = [e for e in report.errors if e.field == "email"]
        assert len(email_errors) == 0

    def test_invalid_email_flagged(self):
        df = pd.DataFrame({
            "record_id": ["EMP001"],
            "name":      ["Alice"],
            "email":     ["not_an_email"],
            "salary":    [50000.0],
        })
        report = validate_dataframe(df)
        email_errors = [e for e in report.errors if e.rule == "invalid_email_format"]
        assert len(email_errors) >= 1

    def test_missing_email_flagged_as_critical_when_required(self):
        df = pd.DataFrame({
            "record_id": ["EMP001"],
            "name":      ["Alice"],
            "email":     [""],
            "salary":    [50000.0],
        })
        report = validate_dataframe(df, required_columns=["email"])
        critical_errors = [e for e in report.errors if e.severity == "critical" and e.field == "email"]
        assert len(critical_errors) >= 1


# ---------------------------------------------------------------------------
# 5. Numeric / salary validation
# ---------------------------------------------------------------------------

class TestSalaryValidation:
    def test_valid_salary_passes(self, valid_df):
        report = validate_dataframe(valid_df)
        salary_errors = [e for e in report.errors if e.field == "salary"]
        assert len(salary_errors) == 0

    def test_negative_salary_flagged(self):
        df = pd.DataFrame({
            "record_id": ["EMP001"],
            "name":      ["Alice"],
            "email":     ["alice@test.com"],
            "salary":    [-5000.0],
        })
        report = validate_dataframe(df)
        neg_errors = [e for e in report.errors if e.rule == "negative_salary"]
        assert len(neg_errors) >= 1

    def test_non_numeric_salary_flagged(self):
        df = pd.DataFrame({
            "record_id": ["EMP001"],
            "name":      ["Alice"],
            "email":     ["alice@test.com"],
            "salary":    ["eighty thousand"],
        })
        report = validate_dataframe(df)
        type_errors = [e for e in report.errors if e.rule == "non_numeric_salary"]
        assert len(type_errors) >= 1


# ---------------------------------------------------------------------------
# Required fields
# ---------------------------------------------------------------------------

class TestRequiredFields:
    def test_missing_required_field_is_invalid(self):
        df = pd.DataFrame({
            "record_id": ["EMP001"],
            "name":      [""],
            "email":     ["alice@test.com"],
            "salary":    [50000.0],
        })
        report = validate_dataframe(df, required_columns=["name"])
        assert report.invalid_count >= 1

    def test_all_present_is_valid(self, valid_df):
        report = validate_dataframe(
            valid_df,
            required_columns=["record_id", "name", "email", "salary"],
        )
        assert report.valid_count == len(valid_df)
        assert report.invalid_count == 0


# ---------------------------------------------------------------------------
# Duplicate record IDs
# ---------------------------------------------------------------------------

class TestDuplicateIds:
    def test_duplicate_id_flagged(self):
        df = pd.DataFrame({
            "record_id": ["EMP001", "EMP001"],
            "name":      ["Alice", "Alice B"],
            "salary":    [50000, 60000],
        })
        report = validate_dataframe(df)
        dup_errors = [e for e in report.errors if e.rule == "duplicate_id"]
        assert len(dup_errors) >= 2   # both rows flagged


# ---------------------------------------------------------------------------
# Records not silently discarded
# ---------------------------------------------------------------------------

class TestNoSilentDiscard:
    def test_review_records_present_in_report(self):
        df = pd.DataFrame({
            "record_id": ["EMP001"],
            "name":      ["Alice"],
            "email":     ["bad-email"],
            "salary":    [50000.0],
        })
        report = validate_dataframe(df)
        total = report.valid_count + report.review_count + report.invalid_count
        assert total == len(df), "Records were silently discarded"

    def test_invalid_records_present_in_report(self):
        df = pd.DataFrame({
            "record_id": ["EMP001"],
            "name":      [""],
            "email":     ["alice@test.com"],
            "salary":    [50000.0],
        })
        report = validate_dataframe(df, required_columns=["name"])
        total = report.valid_count + report.review_count + report.invalid_count
        assert total == len(df)
