"""
data_consolidator.py
====================
Consolidates cleaned, validated DataFrames from multiple source files
into a single master DataFrame.

Responsibilities
----------------
* Accept a list of (filename, DataFrame) tuples.
* Align columns across sources (union of all columns, fill missing with NaN).
* Preserve source metadata columns (_source_file, _source_sheet).
* Return a structured ConsolidationResult.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class ConsolidationResult:
    master_df: pd.DataFrame
    total_records: int
    source_counts: dict[str, int]  # filename → row count contributed
    column_union: list[str]
    warnings: list[str] = field(default_factory=list)


def consolidate(
    sources: list[tuple[str, pd.DataFrame]],
) -> ConsolidationResult:
    """
    Merge multiple DataFrames into one master DataFrame.

    Parameters
    ----------
    sources : List of (label, DataFrame) — label is typically the filename.

    Returns
    -------
    ConsolidationResult
    """
    if not sources:
        logger.warning("No sources provided to consolidator — returning empty DataFrame.")
        return ConsolidationResult(
            master_df=pd.DataFrame(),
            total_records=0,
            source_counts={},
            column_union=[],
            warnings=["No source DataFrames were provided."],
        )

    frames: list[pd.DataFrame] = []
    source_counts: dict[str, int] = {}
    warnings: list[str] = []

    for label, df in sources:
        if df.empty:
            warnings.append(f"'{label}' contributed 0 rows — skipped.")
            continue
        frames.append(df)
        source_counts[label] = len(df)
        logger.info("  Consolidating '%s': %d rows", label, len(df))

    if not frames:
        logger.warning("All source DataFrames were empty.")
        return ConsolidationResult(
            master_df=pd.DataFrame(),
            total_records=0,
            source_counts=source_counts,
            column_union=[],
            warnings=warnings,
        )

    master_df = pd.concat(frames, ignore_index=True, sort=False)

    # Derive column union (in order of first appearance)
    seen: dict[str, None] = {}
    for df in frames:
        for col in df.columns:
            seen[col] = None
    column_union = list(seen.keys())

    logger.info(
        "Consolidation complete: %d records from %d source(s), %d columns.",
        len(master_df), len(frames), len(column_union),
    )

    return ConsolidationResult(
        master_df=master_df,
        total_records=len(master_df),
        source_counts=source_counts,
        column_union=column_union,
        warnings=warnings,
    )
