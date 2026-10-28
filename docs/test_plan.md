# Test Plan

## Overview

The test suite contains 72 pytest tests across 5 test files. Tests use temporary
directories and programmatically generated workbooks — no user files or external
services are required.

## Test Execution

```bash
# All tests
venv/bin/python -m pytest tests/ -v

# Single file
venv/bin/python -m pytest tests/test_data_cleaner.py -v

# One test by name
venv/bin/python -m pytest tests/test_rpa_workflow.py::TestEndToEndWorkflow::test_workflow_succeeds_on_clean_file -v
```

## Actual Test Results (last run)

```
platform linux -- Python 3.14.7, pytest-9.0.3, pluggy-1.7.0
collected 72 items

tests/test_consolidator.py          6 passed
tests/test_data_cleaner.py         25 passed
tests/test_data_validator.py       11 passed
tests/test_exception_handler.py    10 passed
tests/test_rpa_workflow.py         20 passed

72 passed in 0.76s
```

**All 72 tests pass.**

## Test Coverage by Requirement

| # | Requirement | Test(s) | File |
|---|-------------|---------|------|
| 1 | Column-name normalisation | `TestColumnNormalisation` (5 tests) | `test_rpa_workflow.py` |
| 2 | Whitespace cleaning | `TestWhitespaceCleaning` (3 tests) | `test_data_cleaner.py` |
| 3 | Date normalisation | `TestDateStandardisation` (4 tests) | `test_data_cleaner.py` |
| 4 | Email validation | `TestEmailValidation` (3 tests) | `test_data_validator.py` |
| 5 | Numeric field validation | `TestSalaryValidation` (3 tests) | `test_data_validator.py` |
| 6 | Exact duplicate detection | `TestExactDuplicateDetection` (2 tests) | `test_data_cleaner.py` |
| 7 | Conflicting duplicate identification | `TestConflictingDuplicates` (2 tests) | `test_data_cleaner.py` |
| 8 | Missing-value handling | `TestMissingValuePolicy` (3 tests) | `test_data_cleaner.py` |
| 9 | Column alias mapping | Implicit in `TestColumnNormalisation` + reader tests | `test_rpa_workflow.py` |
| 10 | Workbook consolidation | `TestConsolidation` (6 tests) | `test_consolidator.py` |
| 11 | Empty input directory | `TestEmptyDirectory` (2 tests) | `test_rpa_workflow.py` |
| 12 | Corrupted Excel files | `TestCorruptedFile` (1 test) | `test_rpa_workflow.py` |
| 13 | Missing mandatory columns | `TestMissingMandatoryColumns` (1 test) | `test_rpa_workflow.py` |
| 14 | Output write failures | `TestOutputWriteFailure` (1 test) | `test_rpa_workflow.py` |
| 15 | Partial failure handling | `test_failed_file_reported` | `test_rpa_workflow.py` |
| 16 | Performance calculations | `TestPerformanceCalculations` (4 tests) | `test_rpa_workflow.py` |
| 17 | End-to-end workflow | `TestEndToEndWorkflow` (5 tests) | `test_rpa_workflow.py` |

## Detailed Test Descriptions

### test_data_cleaner.py (25 tests)

**TestWhitespaceCleaning**
- `test_strips_leading_trailing` — verifies a name with leading/trailing spaces is
  cleaned to "Alice Smith".
- `test_email_stripped` — email with surrounding spaces is stripped.
- `test_audit_records_operation` — confirms `strip_whitespace` appears in the audit.

**TestCapitalisationNormalisation**
- `test_name_title_cased` — "JOHN DOE" → "John Doe", "jane smith" → "Jane Smith".
- `test_email_lower_cased` — "USER@EXAMPLE.COM" → "user@example.com".

**TestDateStandardisation**
- `test_iso_date_unchanged` — ISO-format date passes through unchanged.
- `test_dmy_slash_converted` — "15/03/2019" → "2019-03-15".
- `test_text_month_converted` — "March 22, 2021" → "2021-03-22".
- `test_unparseable_date_preserved` — "not-a-date" is returned as-is (not blanked).

**TestPhoneNormalisation**
- `test_removes_formatting` — "+1 (555) 123-4567" → "+15551234567".
- `test_preserves_leading_plus` — leading `+` is kept.
- `test_does_not_invent_digits` — "123" stays "123".

**TestNumericConversion**
- `test_salary_string_converted` — "50,000" → 50000.0.
- `test_currency_symbols_stripped` — "$45,000.00" → 45000.0.
- `test_non_numeric_preserved` — "eighty thousand" is not converted.

**TestCategoricalMappings**
- `test_hr_mapped` — "hr" → "Human Resources".
- `test_case_insensitive` — "HR" matches mapping.
- `test_unmapped_value_preserved` — unknown department is preserved.

**TestMissingValuePolicy**
- `test_flag_creates_column` — empty salary generates `_missing_salary` column.
- `test_leave_blank_no_flag_column` — leave_blank policy creates no flag column.
- `test_missing_not_filled_with_zero` — None salary is not replaced with 0.

**TestExactDuplicateDetection**
- `test_exact_duplicate_detected` — two identical rows detected.
- `test_clean_dataframe_excludes_exact_dups` — only one copy in clean output.

**TestConflictingDuplicates**
- `test_conflicting_detected` — same ID, different name → both rows flagged.
- `test_conflicting_not_in_clean` — EMP001 removed from clean; EMP002 remains.

### test_data_validator.py (11 tests)

**TestEmailValidation**
- Valid email generates no email errors.
- Invalid email generates `invalid_email_format` error.
- Empty required email generates a `critical` error.

**TestSalaryValidation**
- Valid salary generates no errors.
- Negative salary generates `negative_salary` warning.
- Non-numeric salary generates `non_numeric_salary` critical error.

**TestRequiredFields**
- Empty required field → record is INVALID.
- All fields present → all records VALID.

**TestDuplicateIds**
- Two rows with same `record_id` → both flagged with `duplicate_id`.

**TestNoSilentDiscard**
- REVIEW + VALID + INVALID counts always equal input row count.

### test_consolidator.py (6 tests)

- Combined row count equals sum of sources.
- Column union contains columns from all sources.
- Source counts tracked per filename.
- Empty sources list returns empty result.
- Single-source consolidation works correctly.
- All-empty DataFrames produce a warning, not an exception.

### test_exception_handler.py (10 tests)

- `CorruptedFileError` has the correct `ErrorCategory`.
- `MissingColumnsError` has the correct `ErrorCategory`.
- RPA exceptions are recorded with correct source file and stage.
- Standard Python `PermissionError` is classified as `PERMISSION_ERROR`.
- Multiple failures are all tracked.
- `summary()` returns correct counts by category.
- `clear()` resets the handler.
- Recommended action is populated for known error categories.
- Failure record contains correct stage and source file.

### test_rpa_workflow.py (20 tests)

**TestColumnNormalisation** (5) — spaces, dots, mixed case, multiple spaces.
**TestEmptyDirectory** (2) — missing and empty directories raise correct exceptions.
**TestCorruptedFile** (1) — non-xlsx bytes raise `CorruptedFileError`.
**TestMissingMandatoryColumns** (1) — missing col → critical validation error.
**TestOutputWriteFailure** (1) — write to locked dir raises `OutputWriteError`.
**TestInputFilePreservation** (1) — MD5 hash unchanged after workflow run.
**TestPerformanceCalculations** (4) — basic calc, zero records, zero duration, negative time saved.
**TestEndToEndWorkflow** (5) — success status, master not empty, all 6 worksheets present, failed file reported, metrics populated.

## Test Design Principles

- All tests are isolated: each uses `tempfile.TemporaryDirectory` or in-memory DataFrames.
- No test reads from `data/input/` or any user file.
- No test connects to external services.
- Temporary files and directories are always cleaned up by `pytest` fixtures.
- Original input files are verified to be unchanged by an MD5 comparison.
- Edge cases (empty DataFrame, zero duration, zero records) are explicitly tested.
