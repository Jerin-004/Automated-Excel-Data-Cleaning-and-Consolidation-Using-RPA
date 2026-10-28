"""
report_generator.py
===================
Generates the plain-text / structured execution reports and logs.

Produces:
  * Execution log  (logs/rpa_run_<timestamp>.log)
  * CSV validation errors report  (reports/validation_errors_<timestamp>.csv)
  * JSON run summary  (reports/run_summary_<timestamp>.json)
"""

from __future__ import annotations

import csv
import json
import logging
import os
from datetime import datetime
from pathlib import Path

import pandas as pd

from src.exception_handler import FailureRecord

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def save_validation_csv(
    exceptions_df: pd.DataFrame,
    reports_dir: str | Path,
    timestamp: str | None = None,
) -> Path:
    """Save exceptions/validation errors as a CSV file."""
    reports_dir = Path(reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    ts = timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    path = reports_dir / f"validation_errors_{ts}.csv"

    if exceptions_df.empty:
        # Write an empty CSV with a note
        with open(path, "w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["note"])
            writer.writerow(["No validation errors found."])
    else:
        exceptions_df.to_csv(path, index=False)

    logger.info("Validation CSV saved: %s", path)
    return path


def save_run_summary_json(
    run_stats: dict,
    reports_dir: str | Path,
    timestamp: str | None = None,
) -> Path:
    """Save the run statistics as a JSON file."""
    reports_dir = Path(reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    ts = timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    path = reports_dir / f"run_summary_{ts}.json"

    with open(path, "w") as fh:
        json.dump(run_stats, fh, indent=2, default=str)

    logger.info("Run summary JSON saved: %s", path)
    return path


def configure_file_logging(
    logs_dir: str | Path,
    timestamp: str | None = None,
    level: int = logging.INFO,
) -> Path:
    """
    Add a file handler to the root logger.

    Returns the log file path.
    """
    logs_dir = Path(logs_dir)
    logs_dir.mkdir(parents=True, exist_ok=True)
    ts = timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = logs_dir / f"rpa_run_{ts}.log"

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(level)
    fmt = logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(fmt)
    logging.getLogger().addHandler(file_handler)
    logger.info("File logging configured: %s", log_path)
    return log_path


def build_processing_log(file_results: list[dict]) -> list[dict]:
    """
    Convert raw file-result dicts to a consistent Processing_Log structure.
    """
    log_rows: list[dict] = []
    for r in file_results:
        log_rows.append({
            "filename":         r.get("filename", ""),
            "status":           r.get("status", "UNKNOWN"),
            "sheets_processed": r.get("sheets_processed", 0),
            "rows_extracted":   r.get("rows_extracted", 0),
            "rows_after_clean": r.get("rows_after_clean", 0),
            "duplicates":       r.get("duplicates", 0),
            "exceptions":       r.get("exceptions", 0),
            "duration_s":       round(r.get("duration_s", 0), 3),
            "error_message":    r.get("error_message", ""),
        })
    return log_rows


def build_failure_log_rows(failures: list[FailureRecord]) -> list[dict]:
    """Convert FailureRecord objects to plain dicts for export."""
    return [
        {
            "Timestamp":          f.timestamp,
            "Stage":              f.stage,
            "Source File":        f.source_file,
            "Error Category":     f.error_category,
            "Message":            f.message,
            "Recommended Action": f.recommended_action,
        }
        for f in failures
    ]
