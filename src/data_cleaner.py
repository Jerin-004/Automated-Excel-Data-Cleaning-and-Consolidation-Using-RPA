"""
data_cleaner.py
===============
Reusable cleaning functions for tabular employee / customer data.

Design principles
-----------------
* Never fabricate data to fill missing fields.
* Never silently discard records.
* Keep an audit trail of every operation in a CleaningAudit object.
* All cleaning rules are driven by configuration, not hard-coded logic.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Columns added by excel_reader.py — excluded from cleaning
_META_COLS = {"_source_file", "_source_sheet"}


def _is_string_col(series: pd.Series) -> bool:
    """Return True if *series* holds string/object data (pandas 3 compat)."""
    return pd.api.types.is_string_dtype(series) or series.dtype == object


# ---------------------------------------------------------------------------
# Audit trail
# ---------------------------------------------------------------------------

@dataclass
class CleaningOperation:
    operation: str
    column: str
    records_affected: int
    detail: str = ""


@dataclass
class CleaningAudit:
    operations: list[CleaningOperation] = field(default_factory=list)
    rows_before: int = 0
    rows_after:  int = 0

    def record(self, operation: str, column: str, affected: int, detail: str = "") -> None:
        self.operations.append(
            CleaningOperation(operation, column, affected, detail)
        )
        if affected:
            logger.debug("  [%s] col=%s  affected=%d  %s", operation, column, affected, detail)

    def summary(self) -> dict:
        return {
            "rows_before": self.rows_before,
            "rows_after":  self.rows_after,
            "operations":  [
                {
                    "operation": op.operation,
                    "column":    op.column,
                    "affected":  op.records_affected,
                    "detail":    op.detail,
                }
                for op in self.operations
            ],
        }


# ---------------------------------------------------------------------------
# Master clean function
# ---------------------------------------------------------------------------

def clean_dataframe(
    df: pd.DataFrame,
    date_formats: list[str] | None = None,
    output_date_format: str = "%Y-%m-%d",
    categorical_mappings: dict[str, dict[str, str]] | None = None,
    missing_value_policy: dict[str, str] | None = None,
) -> tuple[pd.DataFrame, CleaningAudit]:
    """
    Apply the full cleaning pipeline to *df*.

    Returns
    -------
    (cleaned_df, audit)
    """
    audit = CleaningAudit(rows_before=len(df))
    df = df.copy()

    date_formats       = date_formats or []
    categorical_mappings = categorical_mappings or {}
    missing_value_policy = missing_value_policy or {}

    data_cols = [c for c in df.columns if c not in _META_COLS]

    # 1. Strip whitespace from all string cells
    df, audit = _strip_whitespace(df, data_cols, audit)

    # 2. Normalize capitalization on string columns
    df, audit = _normalize_capitalization(df, data_cols, audit)

    # 3. Standardize date columns
    df, audit = _standardize_dates(df, data_cols, date_formats, output_date_format, audit)

    # 4. Normalize phone numbers
    if "phone" in df.columns:
        df, audit = _normalize_phones(df, audit)

    # 5. Normalize email addresses
    if "email" in df.columns:
        df, audit = _normalize_emails(df, audit)

    # 6. Convert numeric fields
    df, audit = _convert_numeric(df, data_cols, audit)

    # 7. Apply categorical mappings
    df, audit = _apply_categorical_mappings(df, categorical_mappings, audit)

    # 8. Apply missing-value policy (flag only — do NOT fill or remove)
    df, audit = _apply_missing_value_policy(df, missing_value_policy, audit)

    audit.rows_after = len(df)
    return df, audit


# ---------------------------------------------------------------------------
# Individual cleaning steps
# ---------------------------------------------------------------------------

def _strip_whitespace(
    df: pd.DataFrame, cols: list[str], audit: CleaningAudit
) -> tuple[pd.DataFrame, CleaningAudit]:
    for col in cols:
        if col not in df.columns:
            continue
        if _is_string_col(df[col]):
            before = df[col].copy()
            df[col] = df[col].apply(lambda v: v.strip() if isinstance(v, str) else v)
            changed = (before != df[col]).sum()
            audit.record("strip_whitespace", col, int(changed))
    return df, audit


def _normalize_capitalization(
    df: pd.DataFrame, cols: list[str], audit: CleaningAudit
) -> tuple[pd.DataFrame, CleaningAudit]:
    """
    Title-case the 'name' column.
    Lower-case email.
    Other string columns: leave as-is (respect intentional casing).
    """
    name_col = "name"
    if name_col in df.columns and _is_string_col(df[name_col]):
        before = df[name_col].copy()
        df[name_col] = df[name_col].apply(
            lambda v: v.title() if isinstance(v, str) and v else v
        )
        changed = (before != df[name_col]).sum()
        audit.record("normalize_capitalization", name_col, int(changed), "title-cased")

    email_col = "email"
    if email_col in df.columns and _is_string_col(df[email_col]):
        before = df[email_col].copy()
        df[email_col] = df[email_col].apply(
            lambda v: v.lower() if isinstance(v, str) and v else v
        )
        changed = (before != df[email_col]).sum()
        audit.record("normalize_capitalization", email_col, int(changed), "lower-cased")

    return df, audit


def _standardize_dates(
    df: pd.DataFrame,
    cols: list[str],
    date_formats: list[str],
    output_format: str,
    audit: CleaningAudit,
) -> tuple[pd.DataFrame, CleaningAudit]:
    """Attempt to parse date-like column values and reformat them."""
    date_cols = [c for c in cols if "date" in c and c in df.columns]

    for col in date_cols:
        affected = 0
        new_values = []
        for val in df[col]:
            parsed = _try_parse_date(val, date_formats)
            if parsed is not None:
                formatted = parsed.strftime(output_format)
                if str(val) != formatted:
                    affected += 1
                new_values.append(formatted)
            else:
                new_values.append(val)  # leave unparseable values unchanged
        df[col] = new_values
        if affected:
            audit.record("standardize_date", col, affected, f"→ {output_format}")

    return df, audit


def _try_parse_date(value: Any, formats: list[str]) -> Optional[datetime]:
    if pd.isna(value) or value == "" or value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    for fmt in formats:
        try:
            return datetime.strptime(s, fmt)
        except (ValueError, TypeError):
            continue
    # Last resort: pandas flexible parser (no format inference warning)
    try:
        return pd.to_datetime(s, dayfirst=False, format="mixed").to_pydatetime()
    except Exception:
        return None


def _normalize_phones(
    df: pd.DataFrame, audit: CleaningAudit
) -> tuple[pd.DataFrame, CleaningAudit]:
    """
    Remove formatting characters from phone numbers.
    Never invent or pad missing digits.
    """
    col = "phone"
    affected = 0
    result = []
    for val in df[col]:
        if pd.isna(val) or val == "":
            result.append(val)
            continue
        s = str(val).strip()
        cleaned = re.sub(r"[\s\-\.\(\)\/]", "", s)
        # Preserve leading +
        if s.startswith("+") and not cleaned.startswith("+"):
            cleaned = "+" + cleaned.lstrip("+")
        if cleaned != s:
            affected += 1
        result.append(cleaned)
    df[col] = result
    audit.record("normalize_phone", col, affected)
    return df, audit


def _normalize_emails(
    df: pd.DataFrame, audit: CleaningAudit
) -> tuple[pd.DataFrame, CleaningAudit]:
    """Lower-case and strip email addresses."""
    col = "email"
    before = df[col].copy()
    df[col] = df[col].apply(
        lambda v: v.strip().lower() if isinstance(v, str) else v
    )
    changed = int((before.fillna("") != df[col].fillna("")).sum())
    audit.record("normalize_email", col, changed)
    return df, audit


def _convert_numeric(
    df: pd.DataFrame, cols: list[str], audit: CleaningAudit
) -> tuple[pd.DataFrame, CleaningAudit]:
    """
    Attempt numeric conversion for salary and similar columns.
    Non-convertible values are left as-is for the validator to flag.
    """
    numeric_hints = {"salary", "pay", "ctc", "compensation", "annual_salary"}
    for col in cols:
        if col not in df.columns:
            continue
        if col in numeric_hints or col.endswith("_amount") or col.endswith("_salary"):
            affected = 0
            result = []
            for val in df[col]:
                if pd.isna(val) or str(val).strip() == "":
                    result.append(val)
                    continue
                cleaned = re.sub(r"[,\s\$£€]", "", str(val).strip())
                try:
                    num = float(cleaned)
                    if str(val).strip() != str(num):
                        affected += 1
                    result.append(num)
                except (ValueError, TypeError):
                    result.append(val)  # leave non-numeric as-is
            df[col] = result
            if affected:
                audit.record("convert_numeric", col, affected)
    return df, audit


def _apply_categorical_mappings(
    df: pd.DataFrame,
    mappings: dict[str, dict[str, str]],
    audit: CleaningAudit,
) -> tuple[pd.DataFrame, CleaningAudit]:
    """
    Standardise categorical columns using configurable value maps.
    Comparison is case-insensitive; original value preserved if no match.
    """
    for col, mapping in mappings.items():
        if col not in df.columns:
            continue
        lower_map = {k.lower(): v for k, v in mapping.items()}
        affected = 0
        result = []
        for val in df[col]:
            if pd.isna(val) or str(val).strip() == "":
                result.append(val)
                continue
            key = str(val).strip().lower()
            if key in lower_map:
                mapped = lower_map[key]
                if str(val).strip() != mapped:
                    affected += 1
                result.append(mapped)
            else:
                result.append(val)
        df[col] = result
        if affected:
            audit.record("categorical_mapping", col, affected, f"{len(lower_map)} mappings")
    return df, audit


def _apply_missing_value_policy(
    df: pd.DataFrame,
    policy: dict[str, str],
    audit: CleaningAudit,
) -> tuple[pd.DataFrame, CleaningAudit]:
    """
    Apply the configured missing-value policy.

    Policies:
    ---------
    "flag"       — add a _missing_<col> boolean column (record is kept for review).
    "leave_blank"— do nothing (already blank).

    This function does NOT remove or fill records.
    """
    for col, action in policy.items():
        if col not in df.columns:
            continue
        is_missing = df[col].apply(lambda v: pd.isna(v) or str(v).strip() == "")
        count = int(is_missing.sum())
        if action == "flag" and count > 0:
            flag_col = f"_missing_{col}"
            df[flag_col] = is_missing
            audit.record("flag_missing", col, count, f"flag column → {flag_col}")
    return df, audit


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------

@dataclass
class DuplicateResult:
    exact_duplicates: pd.DataFrame
    conflicting_duplicates: pd.DataFrame
    clean_dataframe: pd.DataFrame
    exact_count: int
    conflicting_count: int


def detect_duplicates(
    df: pd.DataFrame,
    unique_key_cols: list[str],
    check_cols: list[str] | None = None,
) -> DuplicateResult:
    """
    Identify exact and conflicting duplicate records.

    Parameters
    ----------
    df              : Input DataFrame.
    unique_key_cols : Columns that must be unique (e.g. ["record_id"]).
    check_cols      : Broader set for fuzzy duplicate detection.

    Returns
    -------
    DuplicateResult with separate DataFrames for each category.
    """
    df = df.copy()
    check_cols = check_cols or unique_key_cols

    # --- Exact duplicates: every data column identical
    data_cols = [c for c in df.columns if not c.startswith("_")]
    exact_mask = df.duplicated(subset=data_cols, keep=False)
    exact_dups = df[exact_mask].copy()
    exact_dups["_duplicate_type"] = "Exact"

    # Remove exact duplicates from the working set (keep first)
    df_no_exact = df.drop_duplicates(subset=data_cols, keep="first")

    # --- Conflicting duplicates: same key, different other values
    valid_key_cols = [c for c in unique_key_cols if c in df_no_exact.columns]
    conflicting = pd.DataFrame()
    if valid_key_cols:
        dup_key_mask = df_no_exact.duplicated(subset=valid_key_cols, keep=False)
        conflicting = df_no_exact[dup_key_mask].copy()
        conflicting["_duplicate_type"] = "Conflicting"

        # Remove conflicting from clean set (keep none — flag all for review)
        df_clean = df_no_exact[~dup_key_mask].copy()
    else:
        df_clean = df_no_exact.copy()

    logger.info(
        "Duplicate detection: %d exact, %d conflicting, %d clean records.",
        len(exact_dups), len(conflicting), len(df_clean),
    )

    return DuplicateResult(
        exact_duplicates=exact_dups,
        conflicting_duplicates=conflicting,
        clean_dataframe=df_clean,
        exact_count=len(exact_dups),
        conflicting_count=len(conflicting),
    )
