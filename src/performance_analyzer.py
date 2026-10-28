"""
performance_analyzer.py
========================
Measures and reports automation performance metrics.

All manual-processing figures are *estimates* based on a configurable
assumed rate. They are clearly labelled as estimates throughout.

Formulas
--------
  Estimated Manual Time (s)  = total_input_records / (manual_rate_per_min / 60)
  Estimated Time Saved (s)   = Estimated Manual Time - Actual Automation Time
  Estimated Reduction (%)    = (Time Saved / Estimated Manual Time) * 100
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PerformanceMetrics:
    # Counts
    total_input_records:     int   = 0
    total_cleaned_records:   int   = 0
    total_duplicate_records: int   = 0
    total_review_records:    int   = 0
    total_invalid_records:   int   = 0
    files_processed:         int   = 0
    files_failed:            int   = 0

    # Timing
    automation_duration_s:   float = 0.0

    # Derived (populated by calculate())
    records_per_second:            float = 0.0
    estimated_manual_duration_s:   float = 0.0
    estimated_time_saved_s:        float = 0.0
    estimated_reduction_pct:       float = 0.0

    # Assumptions
    manual_rate_per_minute: float = 100.0   # configurable

    def calculate(self) -> "PerformanceMetrics":
        """Compute all derived metrics in-place and return self."""
        # Records per second
        if self.automation_duration_s > 0:
            self.records_per_second = round(
                self.total_input_records / self.automation_duration_s, 2
            )
        else:
            self.records_per_second = float("inf") if self.total_input_records > 0 else 0.0

        # Estimated manual time
        manual_rate_per_second = self.manual_rate_per_minute / 60.0
        if manual_rate_per_second > 0 and self.total_input_records > 0:
            self.estimated_manual_duration_s = (
                self.total_input_records / manual_rate_per_second
            )
        else:
            self.estimated_manual_duration_s = 0.0

        # Time saved
        self.estimated_time_saved_s = (
            self.estimated_manual_duration_s - self.automation_duration_s
        )

        # Percentage reduction
        if self.estimated_manual_duration_s > 0:
            self.estimated_reduction_pct = round(
                (self.estimated_time_saved_s / self.estimated_manual_duration_s) * 100, 2
            )
        else:
            self.estimated_reduction_pct = 0.0

        return self

    def to_display_dict(self) -> dict:
        """Return a human-readable dict for reports and the dashboard."""
        def fmt_time(seconds: float) -> str:
            if seconds == float("inf") or seconds != seconds:  # inf or NaN
                return "< 0.001 s"
            if abs(seconds) < 60:
                return f"{seconds:.2f} s"
            m = int(abs(seconds)) // 60
            s = abs(seconds) % 60
            sign = "-" if seconds < 0 else ""
            return f"{sign}{m}m {s:.1f}s"

        return {
            "Total Input Records":                   self.total_input_records,
            "Total Cleaned Records":                 self.total_cleaned_records,
            "Total Duplicate Records Detected":      self.total_duplicate_records,
            "Records Requiring Review":              self.total_review_records,
            "Invalid Records":                       self.total_invalid_records,
            "Files Successfully Processed":          self.files_processed,
            "Files Failed":                          self.files_failed,
            "Actual Automation Duration":            fmt_time(self.automation_duration_s),
            "Records Processed per Second":          (
                f"{self.records_per_second:.1f}"
                if self.records_per_second != float("inf")
                else "N/A (< 1 ms)"
            ),
            "Estimated Manual Duration (@ 100 rec/min — ESTIMATE)":
                fmt_time(self.estimated_manual_duration_s),
            "Estimated Time Saved (ESTIMATE)":       fmt_time(self.estimated_time_saved_s),
            "Estimated Time Reduction % (ESTIMATE)": f"{self.estimated_reduction_pct:.1f}%",
            "Manual Rate Assumption":
                f"{self.manual_rate_per_minute} records/minute (configurable estimate)",
        }


# ---------------------------------------------------------------------------
# Timer helper
# ---------------------------------------------------------------------------

class StageTimer:
    """High-resolution stage timer using time.perf_counter()."""

    def __init__(self, stage_name: str) -> None:
        self.stage_name = stage_name
        self._start: float = 0.0
        self._end:   float = 0.0

    def __enter__(self) -> "StageTimer":
        self._start = time.perf_counter()
        return self

    def __exit__(self, *_) -> None:
        self._end = time.perf_counter()

    @property
    def elapsed(self) -> float:
        return self._end - self._start
