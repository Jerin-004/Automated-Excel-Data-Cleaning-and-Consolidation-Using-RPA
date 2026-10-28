"""
exception_handler.py
====================
Custom exception hierarchy and a centralised ExceptionHandler that records
every failure with stage, file, category, and recommended action.
"""

from __future__ import annotations

import logging
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exception categories
# ---------------------------------------------------------------------------

class ErrorCategory(str, Enum):
    FILE_NOT_FOUND      = "FILE_NOT_FOUND"
    PERMISSION_ERROR    = "PERMISSION_ERROR"
    CORRUPTED_FILE      = "CORRUPTED_FILE"
    MISSING_COLUMNS     = "MISSING_COLUMNS"
    INVALID_DATA        = "INVALID_DATA"
    MISSING_VALUES      = "MISSING_VALUES"
    DUPLICATE_IDS       = "DUPLICATE_IDS"
    OUTPUT_WRITE_FAIL   = "OUTPUT_WRITE_FAIL"
    CONFIG_ERROR        = "CONFIG_ERROR"
    EMPTY_DIRECTORY     = "EMPTY_DIRECTORY"
    EMPTY_DATASET       = "EMPTY_DATASET"
    UNEXPECTED          = "UNEXPECTED"


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class RPABaseException(Exception):
    """Base class for all RPA exceptions."""
    category: ErrorCategory = ErrorCategory.UNEXPECTED

    def __init__(self, message: str, source_file: str = "", stage: str = "") -> None:
        super().__init__(message)
        self.source_file = source_file
        self.stage = stage


class FileDiscoveryError(RPABaseException):
    category = ErrorCategory.FILE_NOT_FOUND


class FilePermissionError(RPABaseException):
    category = ErrorCategory.PERMISSION_ERROR


class CorruptedFileError(RPABaseException):
    category = ErrorCategory.CORRUPTED_FILE


class MissingColumnsError(RPABaseException):
    category = ErrorCategory.MISSING_COLUMNS


class InvalidDataError(RPABaseException):
    category = ErrorCategory.INVALID_DATA


class OutputWriteError(RPABaseException):
    category = ErrorCategory.OUTPUT_WRITE_FAIL


class ConfigurationError(RPABaseException):
    category = ErrorCategory.CONFIG_ERROR


class EmptyDirectoryError(RPABaseException):
    category = ErrorCategory.EMPTY_DIRECTORY


class EmptyDatasetError(RPABaseException):
    category = ErrorCategory.EMPTY_DATASET


# ---------------------------------------------------------------------------
# Failure record
# ---------------------------------------------------------------------------

RECOMMENDED_ACTIONS: dict[ErrorCategory, str] = {
    ErrorCategory.FILE_NOT_FOUND:    "Verify that the input directory path is correct and the file exists.",
    ErrorCategory.PERMISSION_ERROR:  "Check read/write permissions on the file and directory.",
    ErrorCategory.CORRUPTED_FILE:    "Open the file manually in Excel to verify its integrity, then re-save.",
    ErrorCategory.MISSING_COLUMNS:   "Ensure the file contains all required columns or update the column alias mapping.",
    ErrorCategory.INVALID_DATA:      "Review the flagged records and correct the data before re-running.",
    ErrorCategory.MISSING_VALUES:    "Provide missing mandatory values or adjust the missing-value policy in settings.",
    ErrorCategory.DUPLICATE_IDS:     "Resolve duplicate record identifiers in the source file.",
    ErrorCategory.OUTPUT_WRITE_FAIL: "Check that the output directory exists and is writable.",
    ErrorCategory.CONFIG_ERROR:      "Review config/settings.json for syntax or value errors.",
    ErrorCategory.EMPTY_DIRECTORY:   "Add Excel files to the configured input directory.",
    ErrorCategory.EMPTY_DATASET:     "The file contains no data rows. Verify the worksheet content.",
    ErrorCategory.UNEXPECTED:        "Check the application log for the full traceback.",
}


@dataclass
class FailureRecord:
    timestamp: str
    stage: str
    source_file: str
    error_category: str
    message: str
    recommended_action: str
    traceback_snippet: str = ""


# ---------------------------------------------------------------------------
# Central handler
# ---------------------------------------------------------------------------

class ExceptionHandler:
    """Collects and manages all failures encountered during a workflow run."""

    def __init__(self) -> None:
        self._failures: list[FailureRecord] = []

    # ------------------------------------------------------------------
    def record(
        self,
        exc: Exception,
        stage: str,
        source_file: str = "",
        extra_message: str = "",
    ) -> FailureRecord:
        """
        Record an exception.  Returns the FailureRecord so callers can
        include it in structured results.
        """
        if isinstance(exc, RPABaseException):
            category = exc.category
            msg = str(exc)
            sf = exc.source_file or source_file
            st = exc.stage or stage
        else:
            category = _classify(exc)
            msg = str(exc)
            sf = source_file
            st = stage

        if extra_message:
            msg = f"{extra_message}: {msg}"

        tb = traceback.format_exc()
        # Truncate traceback to last 5 lines to avoid bloat in reports
        tb_lines = tb.strip().splitlines()
        tb_snippet = "\n".join(tb_lines[-5:]) if len(tb_lines) > 5 else tb

        rec = FailureRecord(
            timestamp=datetime.now().isoformat(timespec="seconds"),
            stage=st,
            source_file=sf,
            error_category=category.value,
            message=msg,
            recommended_action=RECOMMENDED_ACTIONS.get(category, ""),
            traceback_snippet=tb_snippet,
        )
        self._failures.append(rec)
        logger.error(
            "[%s] stage=%s file=%s  %s",
            category.value,
            st,
            sf or "<unknown>",
            msg,
        )
        return rec

    # ------------------------------------------------------------------
    def has_failures(self) -> bool:
        return bool(self._failures)

    def failures(self) -> list[FailureRecord]:
        return list(self._failures)

    def clear(self) -> None:
        self._failures.clear()

    def summary(self) -> dict:
        by_category: dict[str, int] = {}
        for f in self._failures:
            by_category[f.error_category] = by_category.get(f.error_category, 0) + 1
        return {
            "total_failures": len(self._failures),
            "by_category": by_category,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _classify(exc: Exception) -> ErrorCategory:
    """Map standard Python exceptions to RPA error categories."""
    if isinstance(exc, PermissionError):
        return ErrorCategory.PERMISSION_ERROR
    if isinstance(exc, FileNotFoundError):
        return ErrorCategory.FILE_NOT_FOUND
    if isinstance(exc, (ValueError, TypeError)):
        return ErrorCategory.INVALID_DATA
    return ErrorCategory.UNEXPECTED
