# System Architecture

## Overview

The project follows a layered, modular architecture. The Streamlit UI sits at the top and
delegates all work to the RPA workflow orchestrator. The orchestrator calls specialised
modules for each concern. No module imports from the UI layer. Data flows strictly
downward through the dependency graph.

```
┌─────────────────────────────────────────────────────┐
│                   app.py  (UI Layer)                 │
│        Streamlit dashboard — presents results,        │
│        accepts configuration, triggers workflow       │
└───────────────────────┬─────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────┐
│             src/rpa_workflow.py  (Orchestrator)      │
│  13 explicit stages, per-stage timing and status,    │
│  WorkflowResult data class, generator-based progress │
└──┬────┬────┬────┬────┬────┬────┬────┬────┬──────────┘
   │    │    │    │    │    │    │    │    │
   ▼    ▼    ▼    ▼    ▼    ▼    ▼    ▼    ▼
file_ excel_ data_ data_ data_  excel_ report_ perf_  exc_
disc. reader clean valid consol export  gen    anal   hand
```

## Module Responsibilities

### `src/file_discovery.py`
Scans the input directory for `.xlsx`/`.xlsm` files. Returns `FileInfo` objects with
discovery status. Raises `EmptyDirectoryError` or `FileDiscoveryError` rather than
returning empty lists silently. Excludes temp files (`~$*`) and files in the output
directory.

### `src/excel_reader.py`
Opens workbooks with openpyxl via pandas. Iterates sheets, drops fully blank rows and
columns, normalises column names to `snake_case`, applies the alias mapping, and tags
every row with `_source_file` and `_source_sheet`. Returns `ExtractionResult` objects
containing per-sheet `SheetResult` instances.

### `src/data_cleaner.py`
Stateless cleaning functions driven entirely by the configuration passed in. Pipeline:

1. Strip whitespace
2. Normalise capitalisation (name → Title Case, email → lower)
3. Standardise dates (multi-format parse → ISO output)
4. Normalise phone numbers (strip formatting; preserve leading `+`)
5. Normalise emails (already done in step 2; double-pass harmless)
6. Convert numeric fields (strip currency symbols and commas)
7. Apply categorical mappings
8. Apply missing-value policy (add `_missing_<col>` flag columns)

Returns `(cleaned_df, CleaningAudit)`. The `CleaningAudit` records every operation
with the count of affected records — this feeds the `Data_Quality_Report` worksheet.

Also contains `detect_duplicates()` which separates exact duplicates (all columns
identical) from conflicting duplicates (same unique key, different other values).

### `src/data_validator.py`
Validates a DataFrame against configurable rules. Produces a `ValidationReport`
with three DataFrames: `valid_df`, `review_df`, `invalid_df`. Every input record
appears in exactly one of these — none are silently discarded.

Rules: required fields, duplicate `record_id`, email regex, salary numeric/range,
date parseability, categorical allowed-values.

### `src/data_consolidator.py`
Accepts a list of `(label, DataFrame)` tuples and concatenates them into a master
DataFrame. Computes the column union across all sources. Returns `ConsolidationResult`
with per-source row counts.

### `src/excel_exporter.py`
Writes the six-worksheet master workbook using openpyxl directly (not xlsxwriter).
Uses an atomic write pattern: write to a temp file in the same directory, then
`Path.replace()`. This guarantees that a crash during writing never leaves a
partially-written output file that overwrites a good previous output.

Applies:
- Dark navy header fill with white bold font
- Alternating row fill
- Conditional fill: green=VALID, yellow=REVIEW, red=INVALID
- Frozen header rows
- Auto-fitted column widths (capped at 50 characters)
- AutoFilter on all data sheets

### `src/report_generator.py`
Writes plain-text / structured reports: timestamped log file, validation-errors CSV,
run-summary JSON. Also configures the root `logging.FileHandler`.

### `src/performance_analyzer.py`
Computes derived metrics: records/second, estimated manual time, estimated time saved,
estimated reduction %. Manual time is `total_records / (rate_per_min / 60)`. All
manual-side figures are labelled as estimates throughout.

Provides `StageTimer` (a `with`-block context manager using `time.perf_counter()`).

### `src/exception_handler.py`
Defines the custom exception hierarchy and `ExceptionHandler`, a collector that maps
Python exceptions to `ErrorCategory` values, builds `FailureRecord` objects, and
supplies recommended corrective actions for each category.

### `src/sample_generator.py`
Deterministic sample-data generator (fixed seed). Produces three intentionally dirty
workbooks that exercise every cleaning rule and validation scenario.

## Data Flow

```
Input directory
    │
    ▼  file_discovery
[FileInfo list]
    │
    ▼  excel_reader  (per file)
[ExtractionResult]   columns normalised, source-tagged
    │
    ▼  data_cleaner  (per file)
[cleaned DataFrame + CleaningAudit]
    │
    ▼  data_validator  (per file)
[valid_df | review_df | invalid_df]
    │
    ▼  detect_duplicates  (GLOBAL — all files combined)
[exact_dups | conflicting_dups | clean_df]
    │
    ▼  data_consolidator
[master DataFrame]
    │
    ▼  excel_exporter  ──► Master_Consolidated_<ts>.xlsx
    │
    ▼  report_generator ──► validation_errors_<ts>.csv
                         ──► run_summary_<ts>.json
                         ──► logs/rpa_run_<ts>.log
    │
    ▼  performance_analyzer
[PerformanceMetrics]
    │
    ▼  WorkflowResult  (returned to caller / Streamlit)
```

## Configuration Architecture

`config/settings.json` is the single source of truth for all business rules. It is
loaded once at workflow start and passed as a plain `dict` to every stage. No module
has a hard-coded dependency on a file path; the config dict is always injected.

Key configurable sections:

- `column_aliases` — maps canonical names to lists of accepted alternatives
- `required_columns` — columns that trigger a CRITICAL validation error if empty
- `unique_key_columns` — columns used for duplicate key detection
- `categorical_mappings` — value normalisation maps per column
- `missing_value_policy` — `"flag"` or `"leave_blank"` per column
- `validation_rules` — salary bounds, email regex, date format list
- `performance.manual_records_per_minute` — assumption for time-saved estimate

## Concurrency and Safety

The application is designed for single-user, single-run execution. The atomic output
write prevents partial-file corruption. No global mutable state is used; all workflow
state is held in `WorkflowResult` which is local to a single `RPAWorkflow` instance.
The Streamlit UI guards against accidental re-runs by disabling the Start button while
a run is in progress.
