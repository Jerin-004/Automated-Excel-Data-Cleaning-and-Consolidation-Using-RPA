"""
run_workflow.py
===============
CLI entry point — runs the full RPA workflow against the configured input
directory and prints a summary to stdout.

Usage:
    python run_workflow.py [--config path/to/settings.json]
"""
from __future__ import annotations

import sys
import logging
from pathlib import Path

# Configure console logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)

from src.rpa_workflow import RPAWorkflow, WorkflowStatus, load_config

def main() -> int:
    config_path = "config/settings.json"
    for arg in sys.argv[1:]:
        if arg.startswith("--config="):
            config_path = arg.split("=", 1)[1]

    print("\n" + "="*65)
    print("  RPA Excel Data Cleaning and Consolidation")
    print("="*65)

    config = load_config(config_path)
    wf     = RPAWorkflow(config)

    print()
    for fraction, stage_name in wf.run_iter():
        bar_filled = int(fraction * 30)
        bar = "█" * bar_filled + "░" * (30 - bar_filled)
        print(f"\r  [{bar}] {fraction:5.0%}  {stage_name:<35}", end="", flush=True)
    print()  # newline after progress bar

    result = wf.result
    m      = result.metrics

    print("\n" + "="*65)
    print(f"  WORKFLOW STATUS: {result.status}")
    print("="*65)
    print(f"  Duration          : {result.total_duration_s:.3f} s")
    print(f"  Files discovered  : {len(result.files_discovered)}")
    if m:
        print(f"  Files processed   : {m.files_processed}")
        print(f"  Files failed      : {m.files_failed}")
        print(f"  Total input rows  : {m.total_input_records}")
        print(f"  Cleaned rows      : {m.total_cleaned_records}")
        print(f"  Duplicates found  : {m.total_duplicate_records}")
        print(f"  Records for review: {m.total_review_records}")
        print(f"  Invalid records   : {m.total_invalid_records}")
        print(f"  Records/second    : {m.records_per_second}")
        print(f"  Est. manual time  : {m.estimated_manual_duration_s:.1f} s (ESTIMATE)")
        print(f"  Est. time saved   : {m.estimated_time_saved_s:.1f} s (ESTIMATE)")
        print(f"  Est. reduction    : {m.estimated_reduction_pct:.1f}%  (ESTIMATE)")

    if result.output_workbook:
        print(f"\n  Master workbook   : {result.output_workbook}")
    if result.output_csv:
        print(f"  Validation CSV    : {result.output_csv}")
    if result.log_file:
        print(f"  Execution log     : {result.log_file}")

    # Per-file table
    if result.file_results:
        print("\n  Per-File Results:")
        print(f"  {'Filename':<40} {'Status':<20} {'Rows':>6} {'Dups':>5} {'Exc':>5}")
        print("  " + "-"*80)
        for r in result.file_results:
            print(
                f"  {r['filename']:<40} {r['status']:<20} "
                f"{r['rows_extracted']:>6} {r['duplicates']:>5} {r['exceptions']:>5}"
            )

    if result.failures:
        print(f"\n  ⚠ {len(result.failures)} failure(s) recorded:")
        for f in result.failures:
            print(f"    [{f['error_category']}] {f['stage']} / {f['source_file']}: {f['message']}")

    print("\n" + "="*65 + "\n")
    return 0 if result.status in (WorkflowStatus.SUCCESS, WorkflowStatus.PARTIAL_SUCCESS) else 1


if __name__ == "__main__":
    sys.exit(main())
