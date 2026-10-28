"""
test_data_cleaner.py
====================
Tests for src/data_cleaner.py
"""

import pandas as pd
import pytest

from src.data_cleaner import (
    clean_dataframe,
    detect_duplicates,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def basic_df():
    return pd.DataFrame({
        "record_id":    ["EMP001", "EMP002", "EMP003"],
        "name":         ["  alice smith  ", "BOB JONES", "Carol White"],
        "email":        ["ALICE@EXAMPLE.COM", "bob@example.com", "carol@example.com"],
        "phone":        ["+1 (555) 123-4567", "555.987.6543", "(800) 999-0000"],
        "department":   ["hr", "I.T.", "Finance"],
        "joining_date": ["2020-01-15", "15/03/2019", "March 22, 2021"],
        "salary":       ["50,000", "75000", "90000.50"],
        "city":         ["New York", "Chicago", "Boston"],
    })


@pytest.fixture
def categorical_mappings():
    return {
        "department": {
            "hr":  "Human Resources",
            "i.t.": "Information Technology",
        }
    }


# ---------------------------------------------------------------------------
# 1. Whitespace cleaning
# ---------------------------------------------------------------------------

class TestWhitespaceCleaning:
    def test_strips_leading_trailing(self, basic_df):
        cleaned, audit = clean_dataframe(basic_df)
        assert cleaned.at[0, "name"] == "Alice Smith", "Leading/trailing whitespace not stripped"

    def test_email_stripped(self):
        df = pd.DataFrame({"email": ["  user@test.com  "]})
        cleaned, _ = clean_dataframe(df)
        assert cleaned.at[0, "email"] == "user@test.com"

    def test_audit_records_operation(self, basic_df):
        _, audit = clean_dataframe(basic_df)
        ops = [op.operation for op in audit.operations]
        assert "strip_whitespace" in ops


# ---------------------------------------------------------------------------
# 2. Capitalisation normalisation
# ---------------------------------------------------------------------------

class TestCapitalisationNormalisation:
    def test_name_title_cased(self):
        df = pd.DataFrame({"name": ["JOHN DOE", "jane smith"]})
        cleaned, _ = clean_dataframe(df)
        assert cleaned.at[0, "name"] == "John Doe"
        assert cleaned.at[1, "name"] == "Jane Smith"

    def test_email_lower_cased(self):
        df = pd.DataFrame({"email": ["USER@EXAMPLE.COM"]})
        cleaned, _ = clean_dataframe(df)
        assert cleaned.at[0, "email"] == "user@example.com"


# ---------------------------------------------------------------------------
# 3. Date standardisation
# ---------------------------------------------------------------------------

class TestDateStandardisation:
    DATE_FORMATS = ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d %b %Y", "%d %B %Y", "%Y/%m/%d"]

    def test_iso_date_unchanged(self):
        df = pd.DataFrame({"joining_date": ["2020-01-15"]})
        cleaned, _ = clean_dataframe(df, date_formats=self.DATE_FORMATS, output_date_format="%Y-%m-%d")
        assert cleaned.at[0, "joining_date"] == "2020-01-15"

    def test_dmy_slash_converted(self):
        df = pd.DataFrame({"joining_date": ["15/03/2019"]})
        cleaned, _ = clean_dataframe(df, date_formats=self.DATE_FORMATS, output_date_format="%Y-%m-%d")
        assert cleaned.at[0, "joining_date"] == "2019-03-15"

    def test_text_month_converted(self):
        df = pd.DataFrame({"joining_date": ["March 22, 2021"]})
        cleaned, _ = clean_dataframe(df, date_formats=self.DATE_FORMATS, output_date_format="%Y-%m-%d")
        assert cleaned.at[0, "joining_date"] == "2021-03-22"

    def test_unparseable_date_preserved(self):
        df = pd.DataFrame({"joining_date": ["not-a-date"]})
        cleaned, _ = clean_dataframe(df, date_formats=self.DATE_FORMATS)
        assert cleaned.at[0, "joining_date"] == "not-a-date"


# ---------------------------------------------------------------------------
# 4. Phone normalisation
# ---------------------------------------------------------------------------

class TestPhoneNormalisation:
    def test_removes_formatting(self):
        df = pd.DataFrame({"phone": ["+1 (555) 123-4567"]})
        cleaned, _ = clean_dataframe(df)
        assert cleaned.at[0, "phone"] == "+15551234567"

    def test_preserves_leading_plus(self):
        df = pd.DataFrame({"phone": ["+44 20 7946 0958"]})
        cleaned, _ = clean_dataframe(df)
        assert cleaned.at[0, "phone"].startswith("+")

    def test_does_not_invent_digits(self):
        df = pd.DataFrame({"phone": ["123"]})
        cleaned, _ = clean_dataframe(df)
        assert cleaned.at[0, "phone"] == "123"


# ---------------------------------------------------------------------------
# 5. Numeric conversion
# ---------------------------------------------------------------------------

class TestNumericConversion:
    def test_salary_string_converted(self):
        df = pd.DataFrame({"salary": ["50,000"]})
        cleaned, _ = clean_dataframe(df)
        assert cleaned.at[0, "salary"] == 50000.0

    def test_currency_symbols_stripped(self):
        df = pd.DataFrame({"salary": ["$45,000.00"]})
        cleaned, _ = clean_dataframe(df)
        assert cleaned.at[0, "salary"] == 45000.0

    def test_non_numeric_preserved(self):
        df = pd.DataFrame({"salary": ["eighty thousand"]})
        cleaned, _ = clean_dataframe(df)
        assert cleaned.at[0, "salary"] == "eighty thousand"


# ---------------------------------------------------------------------------
# 6. Categorical mappings
# ---------------------------------------------------------------------------

class TestCategoricalMappings:
    def test_hr_mapped(self):
        df = pd.DataFrame({"department": ["hr"]})
        mappings = {"department": {"hr": "Human Resources"}}
        cleaned, _ = clean_dataframe(df, categorical_mappings=mappings)
        assert cleaned.at[0, "department"] == "Human Resources"

    def test_case_insensitive(self):
        df = pd.DataFrame({"department": ["HR"]})
        mappings = {"department": {"hr": "Human Resources"}}
        cleaned, _ = clean_dataframe(df, categorical_mappings=mappings)
        assert cleaned.at[0, "department"] == "Human Resources"

    def test_unmapped_value_preserved(self):
        df = pd.DataFrame({"department": ["Unrelated Dept"]})
        mappings = {"department": {"hr": "Human Resources"}}
        cleaned, _ = clean_dataframe(df, categorical_mappings=mappings)
        assert cleaned.at[0, "department"] == "Unrelated Dept"


# ---------------------------------------------------------------------------
# 7. Missing value flagging
# ---------------------------------------------------------------------------

class TestMissingValuePolicy:
    def test_flag_creates_column(self):
        df = pd.DataFrame({"salary": [""]})
        policy = {"salary": "flag"}
        cleaned, _ = clean_dataframe(df, missing_value_policy=policy)
        assert "_missing_salary" in cleaned.columns
        assert cleaned.at[0, "_missing_salary"] == True  # noqa: E712

    def test_leave_blank_no_flag_column(self):
        df = pd.DataFrame({"city": [""]})
        policy = {"city": "leave_blank"}
        cleaned, _ = clean_dataframe(df, missing_value_policy=policy)
        assert "_missing_city" not in cleaned.columns

    def test_missing_not_filled_with_zero(self):
        df = pd.DataFrame({"salary": [None]})
        policy = {"salary": "flag"}
        cleaned, _ = clean_dataframe(df, missing_value_policy=policy)
        val = cleaned.at[0, "salary"]
        assert pd.isna(val) or str(val).strip() == "", \
            f"Missing salary was unexpectedly filled with: {val!r}"


# ---------------------------------------------------------------------------
# 8. Exact duplicate detection
# ---------------------------------------------------------------------------

class TestExactDuplicateDetection:
    def test_exact_duplicate_detected(self):
        df = pd.DataFrame({
            "record_id": ["EMP001", "EMP002", "EMP001"],
            "name":      ["Alice",  "Bob",    "Alice"],
            "email":     ["a@b.com", "c@d.com", "a@b.com"],
            "salary":    [50000,     60000,    50000],
        })
        result = detect_duplicates(df, unique_key_cols=["record_id"])
        assert result.exact_count >= 2

    def test_clean_dataframe_excludes_exact_dups(self):
        df = pd.DataFrame({
            "record_id": ["EMP001", "EMP001"],
            "name":      ["Alice",  "Alice"],
            "email":     ["a@b.com", "a@b.com"],
            "salary":    [50000,    50000],
        })
        result = detect_duplicates(df, unique_key_cols=["record_id"])
        assert len(result.clean_dataframe) == 1


# ---------------------------------------------------------------------------
# 9. Conflicting duplicate detection
# ---------------------------------------------------------------------------

class TestConflictingDuplicates:
    def test_conflicting_detected(self):
        df = pd.DataFrame({
            "record_id": ["EMP001", "EMP001"],
            "name":      ["Alice Smith", "Different Name"],
            "salary":    [50000, 99999],
        })
        result = detect_duplicates(df, unique_key_cols=["record_id"])
        assert result.conflicting_count >= 2

    def test_conflicting_not_in_clean(self):
        df = pd.DataFrame({
            "record_id": ["EMP001", "EMP001", "EMP002"],
            "name":      ["Alice",  "ALICE",  "Bob"],
            "salary":    [50000,    99999,    60000],
        })
        result = detect_duplicates(df, unique_key_cols=["record_id"])
        clean_ids = result.clean_dataframe["record_id"].tolist()
        assert "EMP001" not in clean_ids
        assert "EMP002" in clean_ids
