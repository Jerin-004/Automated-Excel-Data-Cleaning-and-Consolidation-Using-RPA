"""
excel_reader.py
===============
Reads Excel workbooks and returns normalised DataFrames.

Responsibilities
----------------
* Open workbooks with openpyxl / pandas.
* Iterate over all non-empty worksheets.
* Strip completely blank rows and columns.
* Normalise column names (lower-case, strip, underscores).
* Apply configurable column-alias mapping.
* Tag each row with its source filename and sheet name.
* Return structured ExtractionResult objects.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pandas as pd

from src.exception_handler import (
    CorruptedFileError,
    EmptyDatasetError,
    FilePermissionError,
    MissingColumnsError,
)

logger = logging.getLogger(__name__)

SOURCE_FILE_COL  = "_source_file"
SOURCE_SHEET_COL = "_source_sheet"


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class SheetResult:
    sheet_name: str
    dataframe: pd.DataFrame          # normalised, tagged
    raw_row_count: int
    extracted_row_count: int
    columns_found: list[str]
    columns_mapped: dict[str, str]   # original → canonical
    warnings: list[str] = field(default_factory=list)


@dataclass
class ExtractionResult:
    filename: str
    filepath: Path
    sheets: list[SheetResult] = field(default_factory=list)
    failed_sheets: list[dict] = field(default_factory=list)

    @property
    def total_rows(self) -> int:
        return sum(s.extracted_row_count for s in self.sheets)

    @property
    def combined_dataframe(self) -> pd.DataFrame:
        if not self.sheets:
            return pd.DataFrame()
        return pd.concat([s.dataframe for s in self.sheets], ignore_index=True)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def read_workbook(
    filepath: str | Path,
    column_aliases: dict[str, list[str]] | None = None,
    required_columns: list[str] | None = None,
) -> ExtractionResult:
    """
    Read all sheets from an Excel workbook.

    Parameters
    ----------
    filepath         : Path to the .xlsx / .xlsm file.
    column_aliases   : Mapping from canonical name → list of accepted aliases.
    required_columns : Columns that must be present after alias resolution.

    Returns
    -------
    ExtractionResult with per-sheet DataFrames.

    Raises
    ------
    CorruptedFileError   – openpyxl / pandas cannot open the file.
    FilePermissionError  – OS permission denied.
    EmptyDatasetError    – all sheets are empty.
    """
    path = Path(filepath)
    aliases = column_aliases or {}

    try:
        xl = pd.ExcelFile(path, engine="openpyxl")
    except PermissionError as exc:
        raise FilePermissionError(str(exc), source_file=path.name, stage="Excel Read") from exc
    except Exception as exc:
        raise CorruptedFileError(
            f"Cannot open workbook: {exc}", source_file=path.name, stage="Excel Read"
        ) from exc

    result = ExtractionResult(filename=path.name, filepath=path)

    for sheet_name in xl.sheet_names:
        try:
            sheet_result = _read_sheet(
                xl, sheet_name, path.name, aliases, required_columns or []
            )
            if sheet_result is not None:
                result.sheets.append(sheet_result)
        except (MissingColumnsError, EmptyDatasetError) as exc:
            logger.warning("Sheet '%s' in '%s': %s", sheet_name, path.name, exc)
            result.failed_sheets.append(
                {"sheet": sheet_name, "reason": str(exc)}
            )
        except Exception as exc:
            logger.warning(
                "Unexpected error reading sheet '%s' in '%s': %s",
                sheet_name, path.name, exc,
            )
            result.failed_sheets.append(
                {"sheet": sheet_name, "reason": str(exc)}
            )

    if not result.sheets:
        raise EmptyDatasetError(
            f"No usable data sheets found in '{path.name}'.",
            source_file=path.name,
            stage="Excel Read",
        )

    logger.info(
        "Read '%s': %d sheet(s), %d total rows.",
        path.name, len(result.sheets), result.total_rows,
    )
    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _read_sheet(
    xl: pd.ExcelFile,
    sheet_name: str,
    filename: str,
    aliases: dict[str, list[str]],
    required_columns: list[str],
) -> Optional[SheetResult]:
    """Read a single sheet; return None if the sheet is completely empty."""
    try:
        df = pd.read_excel(xl, sheet_name=sheet_name, dtype=str)
    except Exception as exc:
        raise CorruptedFileError(
            f"Cannot parse sheet '{sheet_name}': {exc}",
            source_file=filename,
            stage="Excel Read",
        ) from exc

    # Drop fully blank rows and columns
    df = df.dropna(how="all")
    df = df.dropna(axis=1, how="all")

    if df.empty:
        return None   # silently skip empty sheets

    raw_row_count = len(df)

    # Normalise column names
    original_cols = list(df.columns)
    df.columns = [_normalise_col(str(c)) for c in df.columns]

    # Apply alias mapping
    col_map = _build_alias_map(list(df.columns), aliases)
    df = df.rename(columns=col_map)

    # Check required columns
    if required_columns:
        missing = [c for c in required_columns if c not in df.columns]
        if missing:
            raise MissingColumnsError(
                f"Sheet '{sheet_name}' is missing required columns: {missing}",
                source_file=filename,
                stage="Excel Read",
            )

    # Tag source
    df[SOURCE_FILE_COL]  = filename
    df[SOURCE_SHEET_COL] = sheet_name

    # Reset index
    df = df.reset_index(drop=True)

    return SheetResult(
        sheet_name=sheet_name,
        dataframe=df,
        raw_row_count=raw_row_count,
        extracted_row_count=len(df),
        columns_found=[_normalise_col(c) for c in original_cols],
        columns_mapped={v: k for k, v in col_map.items()},
    )


def _normalise_col(name: str) -> str:
    """lower-case, strip, replace spaces/hyphens/dots with underscores."""
    name = name.strip().lower()
    name = re.sub(r"[\s\-\.]+", "_", name)
    name = re.sub(r"[^\w]", "", name)
    name = re.sub(r"_+", "_", name).strip("_")
    return name


def _build_alias_map(
    current_cols: list[str],
    aliases: dict[str, list[str]],
) -> dict[str, str]:
    """
    Build a rename map from current column names to canonical names.

    aliases format: { canonical_name: [alias1, alias2, ...] }
    """
    # Build reverse: alias → canonical
    reverse: dict[str, str] = {}
    for canonical, alias_list in aliases.items():
        for alias in alias_list:
            reverse[_normalise_col(alias)] = canonical

    col_map: dict[str, str] = {}
    for col in current_cols:
        if col in reverse and col != reverse[col]:
            col_map[col] = reverse[col]

    return col_map
