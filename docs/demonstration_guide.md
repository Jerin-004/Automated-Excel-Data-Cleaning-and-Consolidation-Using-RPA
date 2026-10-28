# Demonstration Guide

## Purpose

This guide provides a step-by-step sequence for demonstrating the project to a
university evaluator. It covers the command-line workflow, the Streamlit dashboard,
the generated Excel workbook, and 15 likely viva questions with answers.

---

## Pre-Demonstration Checklist

- [ ] Virtual environment activated: `source venv/bin/activate`
- [ ] Sample files generated: `python -m src.sample_generator --overwrite`
- [ ] Browser ready for Streamlit at `http://localhost:8501`
- [ ] File manager or terminal open at `data/output/` to show the generated workbook
- [ ] `config/settings.json` open to show configurable rules

---

## Step-by-Step Demonstration

### Step 1 — Show the Problem

Open `data/input/employees_north_region.xlsx` in a spreadsheet viewer and point out:

- Row with `"  alice smith  "` — leading/trailing whitespace
- Row with `"hr"` in Department — inconsistent capitalisation
- Row with date `"15/03/2019"` — non-ISO date format
- Row with empty salary — missing mandatory field
- Row with `"not_an_email"` — invalid email
- The exact duplicate row at the end of the sheet

Then open `employees_south_region.xlsx` and show:

- Different column headers: `emp_id`, `employee_name`, `mobile_number`, `date_of_joining`
- `"mktg"` in Department
- `EMP0025` appears in both files with different names/salaries (conflicting duplicate)

**Talking point:** "An employee would have to manually reconcile these three files,
which could take over an hour. The RPA system does it in under a second."

---

### Step 2 — Show the Project Structure

```bash
ls -la
ls src/
ls tests/
cat config/settings.json
```

Point out the modular structure and the configuration-driven approach.

---

### Step 3 — Run the Tests

```bash
venv/bin/python -m pytest tests/ -v
```

Show all 72 tests passing. Highlight key test classes:
- `TestEndToEndWorkflow` — full pipeline on a real file
- `TestCorruptedFile` — resilience to bad input
- `TestInputFilePreservation` — original files protected
- `TestPerformanceCalculations` — metrics accuracy

---

### Step 4 — Run the CLI Workflow

```bash
python run_workflow.py
```

Walk through the output:
- 13 stages progress bar
- Files discovered, extracted, cleaned, validated
- 26 duplicate records detected (cross-file)
- 45 clean records consolidated
- 17 exceptions recorded
- Master workbook path printed

---

### Step 5 — Inspect the Generated Workbook

```bash
ls -lh data/output/
```

Open `Master_Consolidated_<timestamp>.xlsx` and navigate each worksheet:

1. **Master_Data** — 45 clean records, all with consistent date format and
   title-cased names. Show the `_source_file` and `_source_sheet` columns.
2. **Data_Quality_Report** — list every cleaning operation: how many strip_whitespace
   events, how many date conversions, how many categorical mappings.
3. **Exceptions** — 17 records with their `_validation_errors` column showing
   exactly why each record was flagged.
4. **Processing_Log** — per-file row counts, duplicate counts, exception counts,
   and processing duration.
5. **Duplicate_Records** — 26 rows showing which records were duplicated and
   whether they were exact or conflicting.
6. **Run_Summary** — all KPIs including the time estimate comparison.

---

### Step 6 — Launch the Dashboard

```bash
streamlit run app.py
```

Navigate to `http://localhost:8501`.

1. **Sidebar** — show the configuration panel. Change the manual rate assumption
   to 200 records/minute and observe the estimate change after running.
2. **Generate Sample Files** button — click it to show in-dashboard generation.
3. **Execution tab** — show the discovered files list, then click Start Automation.
   Watch the real-time progress bar advance through all 13 stages.
4. **Overview tab** — show the KPI cards after the run completes.
5. **Data Preview tab** — show Master Data, Exceptions, Duplicates tabs.
6. **Reports tab** — show the download buttons; click to download the workbook.
7. **Performance tab** — show the bar chart comparing automation vs manual estimate.
   Emphasise that manual figures are labelled as estimates.

---

### Step 7 — Demonstrate Exception Handling

```bash
# Create a corrupt file
echo "not an xlsx file" > data/input/corrupt_test.xlsx
python run_workflow.py
```

Show that:
- The corrupt file is reported as FAILED in the Per-File Results table
- Processing continues on the other files
- Status is `PARTIAL_SUCCESS` not `FAILED`
- The failure is recorded in the log file

Then clean up: `rm data/input/corrupt_test.xlsx`

---

## 15 Likely Viva Questions and Answers

**Q1. What is RPA and why is it appropriate for this project?**

Robotic Process Automation automates repetitive, rule-based tasks that humans
currently perform manually. This project automates exactly such a task — reading,
cleaning, and consolidating spreadsheet data — which has well-defined rules, requires
no human judgement for the routine cases, and produces measurable output. The workflow
is structured as explicit automation stages with status tracking, audit trails, and
exception handling, which are core RPA concepts.

---

**Q2. How does the application handle files with different column names?**

`config/settings.json` contains a `column_aliases` mapping. When `excel_reader.py`
reads a workbook, it normalises every column name to `snake_case` and then applies a
reverse alias lookup. For example, `emp_id`, `employee_id`, and `id` all map to the
canonical name `record_id`. This allows files from different source systems to be
processed without any code changes.

---

**Q3. How are duplicates detected across multiple files?**

Stage 8 first collects all valid and review records from every file into a single
combined DataFrame. It then calls `detect_duplicates()` once on the entire dataset.
This means that if EMP0025 appears in `employees_north_region.xlsx` and
`employees_south_region.xlsx` with different salaries, both records are flagged as
conflicting duplicates. A per-file approach would miss this entirely.

---

**Q4. What is the difference between an exact duplicate and a conflicting duplicate?**

An exact duplicate has identical values in every column — it is a copy of a record.
The original is kept; the copy is removed.

A conflicting duplicate shares the same unique key (e.g. `record_id`) but has
different values in other columns. Both records are removed from the clean dataset and
placed in the `Duplicate_Records` worksheet, because the system cannot determine
which version is correct without human review.

---

**Q5. How does the application ensure original input files are never modified?**

The application only opens input files with `pd.read_excel(..., dtype=str)` in
read-only mode. It never writes to the input directory. The atomic write pattern
(temp file → rename) ensures output is only written to the output directory. The
test `TestInputFilePreservation.test_original_file_unchanged` verifies this by
comparing MD5 hashes before and after a full workflow run.

---

**Q6. What happens if the output directory is not writable?**

The `excel_exporter.export_master_workbook()` function wraps both the `mkdir()` call
and the file-write operation in a try/except. If either fails, it raises
`OutputWriteError`, cleans up the temp file, and leaves any previous output file
intact. The workflow catches this, records it via `ExceptionHandler`, and continues
to the reporting stage so logs and the CSV report are still written.

---

**Q7. How is the manual processing time estimate calculated?**

```
Estimated Manual Time (s) = Total Input Records / (Manual Rate / 60)
```

The default manual rate is 100 records per minute, which is a configurable assumption
in `settings.json`. The result is clearly labelled as an estimate throughout the
application — in the dashboard, in the Excel workbook, and in the JSON report.
It is never presented as an experimentally measured value.

---

**Q8. What validation rules are applied and how are they configured?**

All rules are in `config/settings.json` under `validation_rules`. The current rules
check: required fields (empty = critical), duplicate `record_id` (critical), email
format regex (warning), salary numeric type (critical), negative salary (warning),
salary min/max bounds (warning), date parseability (warning), and categorical
allowed-values (warning). Critical failures mark a record INVALID; warnings mark it
REVIEW. All rules can be changed without modifying any code.

---

**Q9. How does the Streamlit progress bar show real-time progress?**

`RPAWorkflow.run_iter()` is a Python generator. Each call to `next()` on the generator
executes one stage and `yield`s `(fraction_complete, stage_name)`. The Streamlit
`app.py` drives this with a `for` loop, calling `st.progress(fraction)` after each
yield. The progress bar reflects actual pipeline progress, not a timer.

---

**Q10. Why was pandas 3.x chosen instead of 2.x?**

During development, pandas 2.2.3 produced a segmentation fault when running on
Python 3.14. The crash occurred inside the pandas C extension for datetime parsing
(`pandas_datetime.so`). Upgrading to pandas 3.1.0 resolved the segfault. This is
documented in `requirements.txt` with `pandas>=3.1.0` and noted in the README
troubleshooting section.

---

**Q11. How does the application avoid writing a corrupt output file on failure?**

It uses an atomic write pattern. The workbook is first written to a temp file in the
same directory (via `tempfile.mkstemp`). Only when writing is complete does the code
call `tmp_path.replace(output_path)`. On Linux, `Path.replace()` is an atomic
rename syscall (`rename(2)`). If the process crashes or the disk is full during
writing, the temp file is incomplete but the previous good output is untouched.

---

**Q12. How many tests were written and what do they cover?**

72 tests across 5 test files, covering: column normalisation, whitespace cleaning,
date standardisation, phone/email normalisation, numeric conversion, categorical
mappings, missing-value policy, exact duplicate detection, conflicting duplicate
detection, email/salary validation, required fields, duplicate ID detection,
consolidation, empty directory handling, corrupted file handling, missing mandatory
columns, output write failures, input file preservation, performance metric
calculations, and full end-to-end workflow execution.

---

**Q13. How would you extend this to process 100 000 rows efficiently?**

Several options: (1) Use `pandas.read_excel` with `chunksize` to process large files
in batches. (2) Use `polars` instead of pandas for significantly faster data
processing. (3) Parallelise file reading across CPU cores using `concurrent.futures`.
(4) Cap the Streamlit preview to avoid loading the full DataFrame into the browser.
The architecture supports these changes because data processing is isolated in the
`src/` modules — the UI and orchestrator do not need to change.

---

**Q14. What would happen if two users ran the workflow simultaneously?**

Both runs would write to separate timestamped output files (e.g.
`Master_Consolidated_20261028_213156.xlsx` and `Master_Consolidated_20261028_213200.xlsx`),
so there is no file collision. However, if both runs read the same input files at the
same time, there is no lock mechanism to prevent this. For production use, a file-lock
or a queue-based trigger would be added. This is noted as a known limitation.

---

**Q15. What is the purpose of the `_source_file` and `_source_sheet` columns?**

These columns are added by `excel_reader.py` as audit metadata. They allow every
record in the master workbook to be traced back to the exact file and worksheet it
came from. This is essential for data governance: if a record is found to be incorrect
after consolidation, the data steward can open the original source file and correct it.
These columns are preserved throughout cleaning, validation, and deduplication.

---

## Screenshot Locations

The following locations in the application are suitable for screenshots during a
presentation:

1. **Input files with dirty data** — open `data/input/employees_north_region.xlsx`
   in a spreadsheet viewer before running the workflow.
2. **CLI workflow progress bar** — terminal output of `python run_workflow.py`.
3. **Streamlit Start Automation** — `Execution` tab, progress bar advancing.
4. **KPI Cards** — `Overview` tab after a successful run.
5. **Master Data preview** — `Data Preview → Master Data` tab.
6. **Exceptions preview** — `Data Preview → Exceptions` tab, showing error messages.
7. **Performance chart** — `Performance` tab, bar chart comparing automation vs manual.
8. **Excel output — Master_Data sheet** — professional formatting with green/yellow/red rows.
9. **Excel output — Duplicate_Records sheet** — showing cross-file conflicts.
10. **Test results** — terminal output of `pytest tests/ -v`.
