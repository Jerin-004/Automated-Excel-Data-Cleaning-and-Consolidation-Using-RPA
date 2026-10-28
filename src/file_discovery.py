"""
file_discovery.py
=================
Discovers Excel workbooks in a configured input directory.

Responsibilities
----------------
* Recursively (or non-recursively) scan a directory for .xlsx / .xlsm files.
* Ignore temp files that start with "~$".
* Ignore files in the configured output directory to avoid feedback loops.
* Return structured FileInfo objects with discovery status.
* Handle missing/empty directories gracefully.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from src.exception_handler import EmptyDirectoryError, FileDiscoveryError

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".xlsx", ".xlsm"}
TEMP_FILE_PREFIXES   = ("~$",)


class DiscoveryStatus(str, Enum):
    DISCOVERED = "DISCOVERED"
    SKIPPED    = "SKIPPED"      # temp file or output file
    UNREADABLE = "UNREADABLE"   # permission or OS error


@dataclass
class FileInfo:
    path: Path
    filename: str
    size_bytes: int
    status: DiscoveryStatus
    skip_reason: str = ""

    @property
    def is_processable(self) -> bool:
        return self.status == DiscoveryStatus.DISCOVERED


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def discover_files(
    input_dir: str | Path,
    output_dir: str | Path | None = None,
    recursive: bool = False,
) -> list[FileInfo]:
    """
    Scan *input_dir* for Excel files.

    Parameters
    ----------
    input_dir  : Directory to scan.
    output_dir : Optional path to exclude (prevents re-processing output files).
    recursive  : If True, descend into sub-directories.

    Returns
    -------
    List of FileInfo objects (both processable and skipped).

    Raises
    ------
    FileDiscoveryError  – directory does not exist.
    EmptyDirectoryError – directory exists but contains no matching files.
    """
    input_path  = Path(input_dir).resolve()
    output_path = Path(output_dir).resolve() if output_dir else None

    if not input_path.exists():
        raise FileDiscoveryError(
            f"Input directory not found: {input_path}",
            stage="File Discovery",
        )
    if not input_path.is_dir():
        raise FileDiscoveryError(
            f"Input path is not a directory: {input_path}",
            stage="File Discovery",
        )

    glob_pattern = "**/*" if recursive else "*"
    candidates = list(input_path.glob(glob_pattern))

    results: list[FileInfo] = []

    for candidate in candidates:
        if not candidate.is_file():
            continue
        if candidate.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue

        # --- Exclude temp files
        if candidate.name.startswith(TEMP_FILE_PREFIXES):
            results.append(_skipped(candidate, "Temporary Excel lock file"))
            continue

        # --- Exclude files inside the output directory
        if output_path and _is_under(candidate, output_path):
            results.append(_skipped(candidate, "File is inside the output directory"))
            continue

        # --- Check readability
        try:
            size = candidate.stat().st_size
        except OSError as exc:
            logger.warning("Cannot stat %s: %s", candidate, exc)
            results.append(
                FileInfo(
                    path=candidate,
                    filename=candidate.name,
                    size_bytes=0,
                    status=DiscoveryStatus.UNREADABLE,
                    skip_reason=str(exc),
                )
            )
            continue

        results.append(
            FileInfo(
                path=candidate,
                filename=candidate.name,
                size_bytes=size,
                status=DiscoveryStatus.DISCOVERED,
            )
        )
        logger.info("Discovered: %s  (%d bytes)", candidate.name, size)

    processable = [f for f in results if f.is_processable]
    logger.info(
        "Discovery complete — %d file(s) found, %d processable.",
        len(results),
        len(processable),
    )

    if not processable:
        skipped_count = len([f for f in results if f.status == DiscoveryStatus.SKIPPED])
        unreadable_count = len([f for f in results if f.status == DiscoveryStatus.UNREADABLE])
        raise EmptyDirectoryError(
            f"No processable Excel files found in {input_path}. "
            f"({skipped_count} skipped, {unreadable_count} unreadable)",
            stage="File Discovery",
        )

    return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _skipped(path: Path, reason: str) -> FileInfo:
    return FileInfo(
        path=path,
        filename=path.name,
        size_bytes=0,
        status=DiscoveryStatus.SKIPPED,
        skip_reason=reason,
    )


def _is_under(child: Path, parent: Path) -> bool:
    """Return True if *child* is inside *parent*."""
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False
