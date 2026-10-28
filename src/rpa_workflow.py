"""
rpa_workflow.py
===============
Central RPA workflow orchestrator.

Stages
------
 1  Initialize
 2  Validate configuration
 3  Discover Excel files
 4  Extract records
 5  Normalize columns / apply aliases
 6  Clean records
 7  Validate records
 8  Detect duplicates
 9  Consolidate
10  Generate master workbook
11  Generate reports and logs
12  Calculate performance metrics
13  Display execution summary

Each stage returns a structured result.
The workflow continues processing independent files when one file fails.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Generator, Optional

import pandas as pd

from src.data_cleaner import CleaningAudit, clean_dataframe, detect_duplicates
from src.data_consolidator import ConsolidationResult, consolidate
from src.data_validator import ValidationReport, validate_dataframe
from src.exception_handler import (
    ConfigurationError,
    EmptyDirectoryError,
    ExceptionHandler,
    RPABaseException,
)
from src.excel_exporter import export_master_workbook, generate_output_filename
from src.excel_reader import ExtractionResult, read_workbook
from src.file_discovery import FileInfo, discover_files
from src.performance_analyzer import PerformanceMetrics, StageTimer
from src.report_generator import (
    build_processing_log,
    configure_file_logging,
    save_run_summary_json,
    save_validation_csv,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Workflow status
# ---------------------------------------------------------------------------

class WorkflowStatus(str, Enum):
    PENDING         = "PENDING"
    RUNNING         = "RUNNING"
    SUCCESS         = "SUCCESS"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    FAILED          = "FAILED"


TOTAL_STAGES = 13


# ---------------------------------------------------------------------------
# Stage result
# ---------------------------------------------------------------------------

@dataclass
class StageResult:
    stage_number: int
    stage_name:   str
    status:       str = WorkflowStatus.SUCCESS
    duration_s:   float = 0.0
    detail:       dict  = field(default_factory=dict)
    error:        str   = ""


# ---------------------------------------------------------------------------
# Full workflow result
# ---------------------------------------------------------------------------

@dataclass
class WorkflowResult:
    status:            WorkflowStatus = WorkflowStatus.PENDING
    start_time:        str  = ""
    end_time:          str  = ""
    total_duration_s:  float = 0.0
    stage_results:     list[StageResult] = field(default_factory=list)

    # Data products
    files_discovered:  list[FileInfo]  = field(default_factory=list)
    file_results:      list[dict]      = field(default_factory=list)   # per-file stats
    master_df:         pd.DataFrame    = field(default_factory=pd.DataFrame)
    exceptions_df:     pd.DataFrame    = field(default_factory=pd.DataFrame)
    duplicates_df:     pd.DataFrame    = field(default_factory=pd.DataFrame)
    cleaning_summary:  list[dict]      = field(default_factory=list)
    output_workbook:   Optional[Path]  = None
    output_csv:        Optional[Path]  = None
    log_file:          Optional[Path]  = None

    # Metrics
    metrics:           Optional[PerformanceMetrics] = None
    failures:          list[dict] = field(default_factory=list)   # FailureRecord dicts


# ---------------------------------------------------------------------------
# Workflow engine
# ---------------------------------------------------------------------------

class RPAWorkflow:
    """
    Orchestrates the 13-stage RPA pipeline.

    Usage::

        wf = RPAWorkflow(config)
        for progress, stage_name in wf.run_iter():
            print(f"{progress:.0%} — {stage_name}")
        result = wf.result
    """

    def __init__(self, config: dict) -> None:
        self._config  = config
        self._handler = ExceptionHandler()
        self._result  = WorkflowResult()
        self._ts      = datetime.now().strftime("%Y%m%d_%H%M%S")

    @property
    def result(self) -> WorkflowResult:
        return self._result

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    def run(self) -> WorkflowResult:
        """Run all stages synchronously. Returns the final WorkflowResult."""
        for _ in self.run_iter():
            pass
        return self._result

    def run_iter(self) -> Generator[tuple[float, str], None, None]:
        """
        Run the workflow as a generator.

        Yields (fraction_complete, current_stage_name) after each stage.
        """
        self._result.status     = WorkflowStatus.RUNNING
        self._result.start_time = datetime.now().isoformat(timespec="seconds")
        overall_start           = time.perf_counter()

        stages = [
            ("Initialize",               self._stage_initialize),
            ("Validate Configuration",   self._stage_validate_config),
            ("Discover Files",           self._stage_discover_files),
            ("Extract Records",          self._stage_extract_records),
            ("Normalize Columns",        self._stage_normalize_columns),
            ("Clean Records",            self._stage_clean),
            ("Validate Records",         self._stage_validate),
            ("Detect Duplicates",        self._stage_detect_duplicates),
            ("Consolidate Data",         self._stage_consolidate),
            ("Generate Master Workbook", self._stage_export),
            ("Generate Reports",         self._stage_reports),
            ("Calculate Performance",    self._stage_performance),
            ("Display Summary",          self._stage_summary),
        ]

        aborted = False
        for i, (name, fn) in enumerate(stages, start=1):
            with StageTimer(name) as timer:
                try:
                    detail = fn() or {}
                    sr = StageResult(
                        stage_number=i,
                        stage_name=name,
                        status=WorkflowStatus.SUCCESS,
                        duration_s=timer.elapsed,
                        detail=detail,
                    )
                except RPABaseException as exc:
                    sr = StageResult(
                        stage_number=i,
                        stage_name=name,
                        status=WorkflowStatus.FAILED,
                        duration_s=timer.elapsed,
                        error=str(exc),
                    )
                    self._handler.record(exc, stage=name)
                    # Critical stages abort the pipeline
                    if i <= 3:   # init / config / discovery are fatal
                        self._result.stage_results.append(sr)
                        self._result.status    = WorkflowStatus.FAILED
                        self._result.failures  = [
                            vars(f) for f in self._handler.failures()
                        ]
                        aborted = True
                        yield i / TOTAL_STAGES, name
                        break
                except Exception as exc:
                    sr = StageResult(
                        stage_number=i,
                        stage_name=name,
                        status=WorkflowStatus.FAILED,
                        duration_s=timer.elapsed,
                        error=str(exc),
                    )
                    self._handler.record(exc, stage=name)
                    if i <= 3:
                        self._result.stage_results.append(sr)
                        self._result.status   = WorkflowStatus.FAILED
                        self._result.failures = [vars(f) for f in self._handler.failures()]
                        aborted = True
                        yield i / TOTAL_STAGES, name
                        break

                self._result.stage_results.append(sr)
            yield i / TOTAL_STAGES, name

        overall_end = time.perf_counter()
        self._result.total_duration_s = overall_end - overall_start
        self._result.end_time         = datetime.now().isoformat(timespec="seconds")

        if not aborted:
            failed_files = sum(1 for r in self._result.file_results if r.get("status") == "FAILED")
            if self._handler.has_failures() or failed_files:
                all_failed = failed_files == len(self._result.file_results) and failed_files > 0
                self._result.status = (
                    WorkflowStatus.FAILED if all_failed else WorkflowStatus.PARTIAL_SUCCESS
                )
            else:
                self._result.status = WorkflowStatus.SUCCESS

        self._result.failures = [vars(f) for f in self._handler.failures()]
        logger.info("Workflow finished: %s  (%.2fs)", self._result.status, self._result.total_duration_s)

    # ------------------------------------------------------------------
    # Stage implementations
    # ------------------------------------------------------------------

    def _stage_initialize(self) -> dict:
        """Stage 1 — configure logging and resolve paths."""
        cfg = self._config

        logs_dir    = Path(cfg.get("logs_directory",    "logs")).resolve()
        reports_dir = Path(cfg.get("reports_directory", "reports")).resolve()
        output_dir  = Path(cfg.get("output_directory",  "data/output")).resolve()

        logs_dir.mkdir(parents=True, exist_ok=True)
        reports_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)

        log_path = configure_file_logging(logs_dir, self._ts)
        self._result.log_file = log_path

        logger.info("=== RPA Workflow started  %s ===", self._ts)
        return {"log_file": str(log_path)}

    def _stage_validate_config(self) -> dict:
        """Stage 2 — validate required configuration keys."""
        required_keys = ["input_directory", "output_directory"]
        missing = [k for k in required_keys if k not in self._config]
        if missing:
            raise ConfigurationError(
                f"Missing required configuration keys: {missing}",
                stage="Validate Configuration",
            )
        return {"validated_keys": list(self._config.keys())}

    def _stage_discover_files(self) -> dict:
        """Stage 3 — discover Excel files in the input directory."""
        cfg        = self._config
        input_dir  = Path(cfg["input_directory"]).resolve()
        output_dir = Path(cfg.get("output_directory", "data/output")).resolve()

        files = discover_files(input_dir, output_dir=output_dir)
        self._result.files_discovered = files
        processable = [f for f in files if f.is_processable]
        logger.info("Discovered %d processable file(s).", len(processable))
        return {"discovered": len(files), "processable": len(processable)}

    # ------------------------------------------------------------------
    # Per-file processing state (populated by stages 4–8)
    # ------------------------------------------------------------------
    def _stage_extract_records(self) -> dict:
        """Stage 4 — extract data from each workbook."""
        cfg            = self._config
        aliases        = cfg.get("column_aliases", {})
        # Do NOT enforce required columns at read time — validate later
        self._extractions: dict[str, ExtractionResult] = {}

        processable = [f for f in self._result.files_discovered if f.is_processable]
        for fi in processable:
            t0 = time.perf_counter()
            try:
                ext = read_workbook(fi.path, column_aliases=aliases)
                self._extractions[fi.filename] = ext
                duration = time.perf_counter() - t0
                self._result.file_results.append({
                    "filename":         fi.filename,
                    "status":           "EXTRACTED",
                    "sheets_processed": len(ext.sheets),
                    "rows_extracted":   ext.total_rows,
                    "rows_after_clean": 0,
                    "duplicates":       0,
                    "exceptions":       0,
                    "duration_s":       duration,
                    "error_message":    "",
                })
            except Exception as exc:
                duration = time.perf_counter() - t0
                self._handler.record(exc, stage="Extract Records", source_file=fi.filename)
                self._result.file_results.append({
                    "filename":         fi.filename,
                    "status":           "FAILED",
                    "sheets_processed": 0,
                    "rows_extracted":   0,
                    "rows_after_clean": 0,
                    "duplicates":       0,
                    "exceptions":       0,
                    "duration_s":       duration,
                    "error_message":    str(exc),
                })

        total_rows = sum(e.total_rows for e in self._extractions.values())
        return {"files_extracted": len(self._extractions), "total_rows": total_rows}

    def _stage_normalize_columns(self) -> dict:
        """Stage 5 — column normalization already done in excel_reader; record stats."""
        total_mapped = 0
        for ext in self._extractions.values():
            for sheet in ext.sheets:
                total_mapped += len(sheet.columns_mapped)
        return {"total_columns_remapped": total_mapped}

    def _stage_clean(self) -> dict:
        """Stage 6 — clean each extracted DataFrame."""
        cfg                  = self._config
        date_formats         = cfg.get("validation_rules", {}).get("date_formats", [])
        output_date_fmt      = cfg.get("validation_rules", {}).get("output_date_format", "%Y-%m-%d")
        categorical_mappings = cfg.get("categorical_mappings", {})
        missing_value_policy = cfg.get("missing_value_policy", {})

        self._cleaned: dict[str, pd.DataFrame] = {}
        self._audits:  dict[str, CleaningAudit] = {}

        for fname, ext in self._extractions.items():
            combined = ext.combined_dataframe
            if combined.empty:
                continue
            try:
                cleaned, audit = clean_dataframe(
                    combined,
                    date_formats=date_formats,
                    output_date_format=output_date_fmt,
                    categorical_mappings=categorical_mappings,
                    missing_value_policy=missing_value_policy,
                )
                self._cleaned[fname] = cleaned
                self._audits[fname]  = audit

                # Update file result row
                for r in self._result.file_results:
                    if r["filename"] == fname:
                        r["rows_after_clean"] = len(cleaned)
                        break

                # Accumulate cleaning summary
                self._result.cleaning_summary.append({
                    "source_file": fname,
                    "rows_before": audit.rows_before,
                    "rows_after":  audit.rows_after,
                    "operations":  [vars(op) for op in audit.operations],
                })
            except Exception as exc:
                self._handler.record(exc, stage="Clean Records", source_file=fname)

        return {"files_cleaned": len(self._cleaned)}

    def _stage_validate(self) -> dict:
        """Stage 7 — validate cleaned records."""
        cfg              = self._config
        required_cols    = cfg.get("required_columns", [])
        vr               = cfg.get("validation_rules", {})
        salary_min       = float(vr.get("salary_min", 0))
        salary_max       = float(vr.get("salary_max", 10_000_000))
        email_regex      = vr.get("email_regex", r"^[\w\.\-]+@[\w\.\-]+\.\w{2,}$")
        cat_map          = cfg.get("categorical_mappings", {})
        # Build valid-values list from categorical mappings
        cat_valid        = {
            col: list(set(cat_map[col].values()))
            for col in cat_map
        }

        self._validation_reports: dict[str, ValidationReport] = {}
        all_exceptions: list[pd.DataFrame] = []

        for fname, df in self._cleaned.items():
            try:
                report = validate_dataframe(
                    df,
                    required_columns=required_cols,
                    salary_min=salary_min,
                    salary_max=salary_max,
                    email_regex=email_regex,
                    categorical_valid_values=cat_valid,
                )
                self._validation_reports[fname] = report

                # Collect exception records
                exc_df = pd.concat(
                    [report.review_df, report.invalid_df], ignore_index=True
                )
                if not exc_df.empty:
                    all_exceptions.append(exc_df)

                # Update file result
                for r in self._result.file_results:
                    if r["filename"] == fname:
                        r["exceptions"] = report.review_count + report.invalid_count
                        break
            except Exception as exc:
                self._handler.record(exc, stage="Validate Records", source_file=fname)

        if all_exceptions:
            self._result.exceptions_df = pd.concat(all_exceptions, ignore_index=True)

        total_review  = sum(r.review_count  for r in self._validation_reports.values())
        total_invalid = sum(r.invalid_count for r in self._validation_reports.values())
        return {"review": total_review, "invalid": total_invalid}

    def _stage_detect_duplicates(self) -> dict:
        """Stage 8 — duplicate detection across the COMBINED valid records (cross-file)."""
        cfg             = self._config
        unique_key_cols = cfg.get("unique_key_columns",   ["record_id"])
        check_cols      = cfg.get("duplicate_check_columns", unique_key_cols)

        # Combine all valid+review records from every file into one DataFrame
        combined_frames: list[pd.DataFrame] = []
        for fname, report in self._validation_reports.items():
            valid_df = pd.concat(
                [report.valid_df, report.review_df], ignore_index=True
            )
            if not valid_df.empty:
                combined_frames.append(valid_df)

        self._valid_for_consolidation: list[tuple[str, pd.DataFrame]] = []

        if not combined_frames:
            self._result.duplicates_df = pd.DataFrame()
            return {"total_duplicates": 0}

        all_valid = pd.concat(combined_frames, ignore_index=True)

        try:
            dup_result = detect_duplicates(all_valid, unique_key_cols, check_cols)
        except Exception as exc:
            self._handler.record(exc, stage="Detect Duplicates")
            # Fallback: use all valid records without dedup
            self._valid_for_consolidation = [("all_files", all_valid)]
            return {"total_duplicates": 0}

        # Build per-file duplicate counts for the processing log
        dup_ids: set = set()
        for df_dups in [dup_result.exact_duplicates, dup_result.conflicting_duplicates]:
            if not df_dups.empty and "_source_file" in df_dups.columns:
                for _, row in df_dups.iterrows():
                    dup_ids.add(row.get("_source_file", ""))

        # Tally per file from the duplicate DataFrames
        file_dup_counts: dict[str, int] = {}
        for df_dups in [dup_result.exact_duplicates, dup_result.conflicting_duplicates]:
            if df_dups.empty or "_source_file" not in df_dups.columns:
                continue
            for fname, group in df_dups.groupby("_source_file"):
                file_dup_counts[fname] = file_dup_counts.get(fname, 0) + len(group)

        for r in self._result.file_results:
            r["duplicates"] = file_dup_counts.get(r["filename"], 0)

        # Collect duplicate DataFrames
        dup_frames = []
        if not dup_result.exact_duplicates.empty:
            dup_frames.append(dup_result.exact_duplicates)
        if not dup_result.conflicting_duplicates.empty:
            dup_frames.append(dup_result.conflicting_duplicates)
        if dup_frames:
            self._result.duplicates_df = pd.concat(dup_frames, ignore_index=True)
        else:
            self._result.duplicates_df = pd.DataFrame()

        # The clean (deduped) records go to consolidation as a single batch
        # We preserve the _source_file tag so per-file attribution is maintained
        if not dup_result.clean_dataframe.empty:
            # Split back by source file for source_counts tracking
            if "_source_file" in dup_result.clean_dataframe.columns:
                for fname, grp in dup_result.clean_dataframe.groupby("_source_file"):
                    self._valid_for_consolidation.append((str(fname), grp.copy()))
            else:
                self._valid_for_consolidation.append(("combined", dup_result.clean_dataframe))

        total_dups = (
            len(self._result.duplicates_df)
            if not self._result.duplicates_df.empty else 0
        )
        logger.info("Global duplicate detection: %d duplicate records found.", total_dups)
        return {"total_duplicates": total_dups}

    def _stage_consolidate(self) -> dict:
        """Stage 9 — consolidate into master DataFrame."""
        cons_result      = consolidate(self._valid_for_consolidation)
        self._result.master_df = cons_result.master_df
        self._consolidation    = cons_result
        return {
            "total_records": cons_result.total_records,
            "sources":       list(cons_result.source_counts.keys()),
        }

    def _stage_export(self) -> dict:
        """Stage 10 — write the master Excel workbook."""
        cfg     = self._config
        out_dir = Path(cfg.get("output_directory", "data/output")).resolve()
        prefix  = cfg.get("output_filename_prefix", "Master_Consolidated")

        out_path = generate_output_filename(out_dir, prefix)
        processing_log = build_processing_log(self._result.file_results)

        # Accumulate all per-file stats for Run_Summary
        metrics = self._build_metrics(duration_s=0)  # placeholder; updated in stage 12
        run_stats = metrics.to_display_dict()

        output_path = export_master_workbook(
            output_path    = out_path,
            master_df      = self._result.master_df,
            exceptions_df  = self._result.exceptions_df,
            duplicates_df  = self._result.duplicates_df,
            processing_log = processing_log,
            cleaning_summary = self._result.cleaning_summary,
            run_stats      = run_stats,
        )
        self._result.output_workbook = output_path
        # Mark successful file statuses
        for r in self._result.file_results:
            if r["status"] == "EXTRACTED":
                r["status"] = "SUCCESS"

        return {"output_path": str(output_path)}

    def _stage_reports(self) -> dict:
        """Stage 11 — save CSV and JSON reports."""
        cfg         = self._config
        reports_dir = Path(cfg.get("reports_directory", "reports")).resolve()

        csv_path  = save_validation_csv(self._result.exceptions_df, reports_dir, self._ts)
        self._result.output_csv = csv_path

        # JSON summary written after metrics in stage 12 — save placeholder now
        return {"csv_report": str(csv_path)}

    def _stage_performance(self) -> dict:
        """Stage 12 — compute and store performance metrics."""
        m = self._build_metrics(self._result.total_duration_s).calculate()
        self._result.metrics = m

        # Save JSON run summary with final metrics
        cfg         = self._config
        reports_dir = Path(cfg.get("reports_directory", "reports")).resolve()
        save_run_summary_json(m.to_display_dict(), reports_dir, self._ts)

        return m.to_display_dict()

    def _stage_summary(self) -> dict:
        """Stage 13 — log execution summary."""
        m = self._result.metrics
        if m:
            logger.info("=== RUN SUMMARY ===")
            for k, v in m.to_display_dict().items():
                logger.info("  %-50s %s", k, v)
        return {}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_metrics(self, duration_s: float) -> PerformanceMetrics:
        cfg = self._config
        rate = cfg.get("performance", {}).get("manual_records_per_minute", 100)

        total_input   = sum(r.get("rows_extracted", 0) for r in self._result.file_results)
        total_cleaned = sum(r.get("rows_after_clean", 0) for r in self._result.file_results)
        total_dups    = (
            len(self._result.duplicates_df)
            if not self._result.duplicates_df.empty else 0
        )
        total_review  = sum(
            rpt.review_count for rpt in getattr(self, "_validation_reports", {}).values()
        )
        total_invalid = sum(
            rpt.invalid_count for rpt in getattr(self, "_validation_reports", {}).values()
        )
        files_ok   = sum(1 for r in self._result.file_results if r.get("status") == "SUCCESS")
        files_fail = sum(1 for r in self._result.file_results if r.get("status") == "FAILED")

        return PerformanceMetrics(
            total_input_records     = total_input,
            total_cleaned_records   = total_cleaned,
            total_duplicate_records = total_dups,
            total_review_records    = total_review,
            total_invalid_records   = total_invalid,
            files_processed         = files_ok,
            files_failed            = files_fail,
            automation_duration_s   = duration_s,
            manual_rate_per_minute  = float(rate),
        )


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------

def load_config(config_path: str | Path = "config/settings.json") -> dict:
    """Load and return the JSON configuration file."""
    path = Path(config_path)
    if not path.exists():
        raise ConfigurationError(
            f"Configuration file not found: {path}",
            stage="Load Config",
        )
    with open(path) as fh:
        return json.load(fh)
