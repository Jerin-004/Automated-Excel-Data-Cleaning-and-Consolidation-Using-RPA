"""
data_validator.py
=================
Configurable validation rules for employee / customer datasets.

Validation separates records into three groups:
  * VALID       — passes all rules.
  * REVIEW      — fails one or more non-critical rules (soft failures).
  * INVALID     — fails a critical rule (missing mandatory field, etc.).

Design principles
-----------------
* All rules are configurable — no hard-coded organisation-specific logic.
* Errors are collected per-record and returned in a structured report.
* Records are never silently discarded.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Validation result codes
# ---------------------------------------------------------------------------

class ValidationStatus:
    VALID   = "VALID"
    REVIEW  = "REVIEW"
    INVALID = "INVALID"


# ---------------------------------------------------------------------------
# Per-record validation error
# ---------------------------------------------------------------------------

@dataclass
class ValidationError:
    record_index: int
    field: str
    rule: str
    value: Any
    message: str
    severity: str  # "critical" | "warning"


# ---------------------------------------------------------------------------
# Validation report
# ---------------------------------------------------------------------------

@dataclass
class ValidationReport:
    valid_df:   pd.DataFrame
    review_df:  pd.DataFrame
    invalid_df: pd.DataFrame
    errors:     list[ValidationError] = field(default_factory=list)

    @property
    def valid_count(self) -> int:
        return len(self.valid_df)

    @property
    def review_count(self) -> int:
        return len(self.review_df)

    @property
    def invalid_count(self) -> int:
        return len(self.invalid_df)

    @property
    def total_count(self) -> int:
        return self.valid_count + self.review_count + self.invalid_count

    def summary(self) -> dict:
        return {
            "valid":   self.valid_count,
            "review":  self.review_count,
            "invalid": self.invalid_count,
            "total":   self.total_count,
            "error_count": len(self.errors),
        }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

DEFAULT_EMAIL_REGEX = r"^[\w\.\-]+@[\w\.\-]+\.\w{2,}$"


def validate_dataframe(
    df: pd.DataFrame,
    required_columns: list[str] | None = None,
    salary_min: float = 0.0,
    salary_max: float = 10_000_000.0,
    email_regex: str = DEFAULT_EMAIL_REGEX,
    categorical_valid_values: dict[str, list[str]] | None = None,
) -> ValidationReport:
    """
    Validate *df* against configured rules.

    Returns
    -------
    ValidationReport with three DataFrames (valid, review, invalid) and
    a list of ValidationError objects.
    """
    required_columns       = required_columns or []
    categorical_valid_values = categorical_valid_values or {}

    df = df.copy()
    df["_validation_status"] = ValidationStatus.VALID
    df["_validation_errors"] = ""

    errors: list[ValidationError] = []
    status_map: dict[int, str] = {}   # index → worst status
    error_msgs: dict[int, list[str]] = {}

    def _add_error(
        idx: int,
        field_: str,
        rule: str,
        value: Any,
        message: str,
        severity: str,
    ) -> None:
        errors.append(ValidationError(idx, field_, rule, value, message, severity))
        worst = ValidationStatus.INVALID if severity == "critical" else ValidationStatus.REVIEW
        current = status_map.get(idx, ValidationStatus.VALID)
        if _severity_rank(worst) > _severity_rank(current):
            status_map[idx] = worst
        if idx not in error_msgs:
            error_msgs[idx] = []
        error_msgs[idx].append(f"[{severity.upper()}] {field_}: {message}")

    # 1. Required fields
    for col in required_columns:
        if col not in df.columns:
            # Column entirely missing — mark all records
            for idx in df.index:
                _add_error(idx, col, "required_column_missing",
                           None, f"Column '{col}' is absent from the dataset.", "critical")
        else:
            missing_mask = df[col].apply(lambda v: pd.isna(v) or str(v).strip() == "")
            for idx in df.index[missing_mask]:
                _add_error(idx, col, "required_field_empty",
                           df.at[idx, col], f"Required field '{col}' is empty.", "critical")

    # 2. Duplicate record IDs
    if "record_id" in df.columns:
        dup_mask = df.duplicated(subset=["record_id"], keep=False)
        for idx in df.index[dup_mask]:
            _add_error(idx, "record_id", "duplicate_id",
                       df.at[idx, "record_id"], "Duplicate Record_ID detected.", "critical")

    # 3. Email format
    if "email" in df.columns:
        pat = re.compile(email_regex)
        for idx in df.index:
            val = df.at[idx, "email"]
            if pd.isna(val) or str(val).strip() == "":
                continue  # handled by required-field check if email is required
            if not pat.match(str(val).strip()):
                _add_error(idx, "email", "invalid_email_format",
                           val, f"'{val}' is not a valid email address.", "warning")

    # 4. Salary validation
    if "salary" in df.columns:
        for idx in df.index:
            val = df.at[idx, "salary"]
            if pd.isna(val) or str(val).strip() == "":
                continue  # handled by required-field check
            try:
                num = float(val)
            except (ValueError, TypeError):
                _add_error(idx, "salary", "non_numeric_salary",
                           val, f"Salary '{val}' is not a valid number.", "critical")
                continue
            if num < 0:
                _add_error(idx, "salary", "negative_salary",
                           val, f"Salary {num} is negative.", "warning")
            elif num < salary_min:
                _add_error(idx, "salary", "salary_below_minimum",
                           val, f"Salary {num} is below minimum {salary_min}.", "warning")
            elif num > salary_max:
                _add_error(idx, "salary", "salary_exceeds_maximum",
                           val, f"Salary {num} exceeds maximum {salary_max}.", "warning")

    # 5. Date fields — check parsability
    date_cols = [c for c in df.columns if "date" in c and not c.startswith("_")]
    for col in date_cols:
        for idx in df.index:
            val = df.at[idx, col]
            if pd.isna(val) or str(val).strip() == "":
                continue
            try:
                pd.to_datetime(str(val).strip())
            except Exception:
                _add_error(idx, col, "invalid_date",
                           val, f"'{val}' cannot be parsed as a date.", "warning")

    # 6. Categorical value check
    for col, valid_vals in categorical_valid_values.items():
        if col not in df.columns:
            continue
        lower_valid = {v.lower() for v in valid_vals}
        for idx in df.index:
            val = df.at[idx, col]
            if pd.isna(val) or str(val).strip() == "":
                continue
            if str(val).strip().lower() not in lower_valid:
                _add_error(idx, col, "invalid_categorical_value",
                           val, f"'{val}' is not in the allowed values for '{col}'.", "warning")

    # --- Apply collected statuses
    for idx, status in status_map.items():
        df.at[idx, "_validation_status"] = status
        df.at[idx, "_validation_errors"] = " | ".join(error_msgs.get(idx, []))

    valid_df   = df[df["_validation_status"] == ValidationStatus.VALID].copy()
    review_df  = df[df["_validation_status"] == ValidationStatus.REVIEW].copy()
    invalid_df = df[df["_validation_status"] == ValidationStatus.INVALID].copy()

    report = ValidationReport(
        valid_df=valid_df,
        review_df=review_df,
        invalid_df=invalid_df,
        errors=errors,
    )

    logger.info(
        "Validation: %d valid, %d review, %d invalid  (%d errors).",
        report.valid_count, report.review_count, report.invalid_count, len(errors),
    )
    return report


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _severity_rank(status: str) -> int:
    return {
        ValidationStatus.VALID:   0,
        ValidationStatus.REVIEW:  1,
        ValidationStatus.INVALID: 2,
    }.get(status, 0)
