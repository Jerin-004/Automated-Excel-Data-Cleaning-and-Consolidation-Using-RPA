"""
test_consolidator.py
====================
Tests for src/data_consolidator.py
"""

import pandas as pd
import pytest

from src.data_consolidator import consolidate


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def df_a():
    return pd.DataFrame({
        "record_id": ["EMP001", "EMP002"],
        "name":      ["Alice", "Bob"],
        "salary":    [50000, 60000],
    })


@pytest.fixture
def df_b():
    return pd.DataFrame({
        "record_id":  ["EMP003", "EMP004"],
        "name":       ["Carol", "Dave"],
        "salary":     [70000, 80000],
        "department": ["Finance", "HR"],   # extra column
    })


# ---------------------------------------------------------------------------
# 10. Workbook consolidation
# ---------------------------------------------------------------------------

class TestConsolidation:
    def test_combined_row_count(self, df_a, df_b):
        result = consolidate([("file_a.xlsx", df_a), ("file_b.xlsx", df_b)])
        assert result.total_records == len(df_a) + len(df_b)

    def test_column_union(self, df_a, df_b):
        result = consolidate([("file_a.xlsx", df_a), ("file_b.xlsx", df_b)])
        assert "department" in result.master_df.columns
        assert "record_id"  in result.master_df.columns

    def test_source_counts_tracked(self, df_a, df_b):
        result = consolidate([("file_a.xlsx", df_a), ("file_b.xlsx", df_b)])
        assert result.source_counts["file_a.xlsx"] == 2
        assert result.source_counts["file_b.xlsx"] == 2

    def test_empty_sources_returns_empty(self):
        result = consolidate([])
        assert result.master_df.empty
        assert result.total_records == 0

    def test_single_source(self, df_a):
        result = consolidate([("only.xlsx", df_a)])
        assert result.total_records == len(df_a)

    def test_all_empty_dataframes(self):
        result = consolidate([
            ("a.xlsx", pd.DataFrame()),
            ("b.xlsx", pd.DataFrame()),
        ])
        assert result.total_records == 0
        assert len(result.warnings) > 0
