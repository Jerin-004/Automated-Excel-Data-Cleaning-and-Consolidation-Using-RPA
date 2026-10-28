"""
test_exception_handler.py
==========================
Tests for src/exception_handler.py
"""

import pytest

from src.exception_handler import (
    ConfigurationError,
    CorruptedFileError,
    EmptyDirectoryError,
    ErrorCategory,
    ExceptionHandler,
    FileDiscoveryError,
    FilePermissionError,
    InvalidDataError,
    MissingColumnsError,
    OutputWriteError,
)


# ---------------------------------------------------------------------------
# Custom exception hierarchy
# ---------------------------------------------------------------------------

class TestCustomExceptions:
    def test_file_discovery_error_is_base(self):
        exc = FileDiscoveryError("not found", source_file="test.xlsx", stage="Stage1")
        assert isinstance(exc, Exception)
        assert exc.source_file == "test.xlsx"

    def test_corrupted_file_has_category(self):
        exc = CorruptedFileError("corrupt")
        assert exc.category == ErrorCategory.CORRUPTED_FILE

    def test_missing_columns_has_category(self):
        exc = MissingColumnsError("missing cols")
        assert exc.category == ErrorCategory.MISSING_COLUMNS


# ---------------------------------------------------------------------------
# ExceptionHandler recording
# ---------------------------------------------------------------------------

class TestExceptionHandlerRecording:
    def test_records_rpa_exception(self):
        handler = ExceptionHandler()
        exc = CorruptedFileError("corrupt file", source_file="bad.xlsx", stage="Read")
        rec = handler.record(exc, stage="Read")
        assert handler.has_failures()
        assert rec.error_category == ErrorCategory.CORRUPTED_FILE.value

    def test_records_standard_exception(self):
        handler = ExceptionHandler()
        exc = PermissionError("access denied")
        handler.record(exc, stage="Export", source_file="out.xlsx")
        assert handler.has_failures()
        failures = handler.failures()
        assert failures[0].error_category == ErrorCategory.PERMISSION_ERROR.value

    def test_multiple_failures_tracked(self):
        handler = ExceptionHandler()
        handler.record(CorruptedFileError("f1"), stage="S1", source_file="f1.xlsx")
        handler.record(OutputWriteError("f2"),   stage="S2", source_file="f2.xlsx")
        assert len(handler.failures()) == 2

    def test_summary_counts_by_category(self):
        handler = ExceptionHandler()
        handler.record(CorruptedFileError("a"), stage="S1", source_file="a.xlsx")
        handler.record(CorruptedFileError("b"), stage="S1", source_file="b.xlsx")
        handler.record(OutputWriteError("c"),   stage="S2", source_file="c.xlsx")
        summary = handler.summary()
        assert summary["total_failures"] == 3
        assert summary["by_category"][ErrorCategory.CORRUPTED_FILE.value] == 2

    def test_clear_resets_handler(self):
        handler = ExceptionHandler()
        handler.record(CorruptedFileError("x"), stage="S", source_file="x.xlsx")
        handler.clear()
        assert not handler.has_failures()

    def test_recommended_action_populated(self):
        handler = ExceptionHandler()
        rec = handler.record(EmptyDirectoryError("empty"), stage="Discovery")
        assert len(rec.recommended_action) > 0


# ---------------------------------------------------------------------------
# Partial failure handling
# ---------------------------------------------------------------------------

class TestPartialFailureReporting:
    def test_failure_record_contains_stage(self):
        handler = ExceptionHandler()
        rec = handler.record(
            FileDiscoveryError("not found"),
            stage="File Discovery",
            source_file="missing.xlsx",
        )
        assert rec.stage == "File Discovery"
        assert rec.source_file == "missing.xlsx"
