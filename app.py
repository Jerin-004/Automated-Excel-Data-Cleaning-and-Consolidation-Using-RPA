"""
app.py
======
Streamlit dashboard for the RPA Excel Automation project.

Sections
--------
1. Sidebar   — configuration panel
2. Overview  — KPI cards
3. Execution — start button + progress
4. Preview   — data preview tabs
5. Reports   — download buttons
6. Performance — charts and metrics
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

# --- ensure src/ is importable when launched as  streamlit run app.py
import sys
sys.path.insert(0, str(Path(__file__).parent))

from src.rpa_workflow import RPAWorkflow, WorkflowResult, WorkflowStatus, load_config
from src.sample_generator import generate_sample_files

# ---------------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="RPA Excel Automation",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Custom CSS
# ---------------------------------------------------------------------------

st.markdown(
    """
    <style>
    .kpi-card {
        background: #1F3864;
        border-radius: 8px;
        padding: 18px 16px;
        text-align: center;
        color: white;
    }
    .kpi-card .value { font-size: 2rem; font-weight: 700; }
    .kpi-card .label { font-size: 0.85rem; opacity: 0.85; margin-top: 4px; }
    .stage-tag { font-size: 0.8rem; padding: 2px 8px; border-radius: 4px; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Session state initialisation
# ---------------------------------------------------------------------------

def _init_state() -> None:
    defaults = {
        "workflow_result":  None,
        "is_running":       False,
        "progress":         0.0,
        "current_stage":    "",
        "config":           None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_state()

# ---------------------------------------------------------------------------
# Load / merge config
# ---------------------------------------------------------------------------

CONFIG_PATH = Path(__file__).parent / "config" / "settings.json"

@st.cache_data(show_spinner=False)
def _load_base_config() -> dict:
    try:
        return load_config(CONFIG_PATH)
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Sidebar — configuration
# ---------------------------------------------------------------------------

def _render_sidebar() -> dict:
    st.sidebar.title("⚙️ Configuration")

    base = _load_base_config()

    # Directory selection
    input_dir = st.sidebar.text_input(
        "Input Directory",
        value=base.get("input_directory", "data/input"),
        help="Path to the folder containing Excel files to process.",
    )
    output_dir = st.sidebar.text_input(
        "Output Directory",
        value=base.get("output_directory", "data/output"),
        help="Path where the master workbook will be saved.",
    )

    st.sidebar.markdown("---")
    st.sidebar.subheader("Cleaning Options")

    dup_col_default = ", ".join(base.get("duplicate_check_columns", ["record_id", "name", "email"]))
    dup_cols_raw = st.sidebar.text_input(
        "Duplicate Check Columns (comma-separated)",
        value=dup_col_default,
    )
    dup_cols = [c.strip() for c in dup_cols_raw.split(",") if c.strip()]

    req_col_default = ", ".join(base.get("required_columns", ["record_id", "name", "email", "salary"]))
    req_cols_raw = st.sidebar.text_input(
        "Required Columns (comma-separated)",
        value=req_col_default,
    )
    req_cols = [c.strip() for c in req_cols_raw.split(",") if c.strip()]

    st.sidebar.markdown("---")
    st.sidebar.subheader("Performance Assumption")
    manual_rate = st.sidebar.number_input(
        "Assumed Manual Rate (records/min)",
        min_value=1,
        max_value=10000,
        value=int(base.get("performance", {}).get("manual_records_per_minute", 100)),
        help="Used only to estimate manual processing time. Not an experimentally measured value.",
    )

    st.sidebar.markdown("---")
    st.sidebar.subheader("Sample Data")
    overwrite_samples = st.sidebar.checkbox("Overwrite existing sample files", value=False)
    if st.sidebar.button("🗂️ Generate Sample Files"):
        with st.spinner("Generating sample Excel files …"):
            try:
                paths = generate_sample_files(
                    output_dir=input_dir,
                    overwrite=overwrite_samples,
                )
                st.sidebar.success(f"Generated {len(paths)} file(s) in `{input_dir}`")
                st.cache_data.clear()
            except Exception as exc:
                st.sidebar.error(f"Error: {exc}")

    # Build merged config
    cfg = dict(base)
    cfg["input_directory"]          = input_dir
    cfg["output_directory"]         = output_dir
    cfg["duplicate_check_columns"]  = dup_cols
    cfg["required_columns"]         = req_cols
    cfg["performance"] = {"manual_records_per_minute": manual_rate}

    return cfg


# ---------------------------------------------------------------------------
# KPI card helper
# ---------------------------------------------------------------------------

def _kpi(col, value: Any, label: str) -> None:
    col.markdown(
        f'<div class="kpi-card"><div class="value">{value}</div>'
        f'<div class="label">{label}</div></div>',
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Main page
# ---------------------------------------------------------------------------

def main() -> None:
    config = _render_sidebar()

    st.title("🤖 RPA Excel Data Automation")
    st.caption(
        "Automated cleaning, validation, duplicate detection, "
        "and consolidation of multiple Excel workbooks."
    )

    # -----------------------------------------------------------------------
    # TAB layout
    # -----------------------------------------------------------------------
    tabs = st.tabs(["▶ Execution", "📊 Overview", "🔍 Data Preview", "📥 Reports", "📈 Performance"])
    tab_exec, tab_overview, tab_preview, tab_reports, tab_perf = tabs

    # ======================================================================
    # TAB: Execution
    # ======================================================================
    with tab_exec:
        st.subheader("Automation Control")

        # Discovered files preview
        input_path = Path(config["input_directory"])
        if input_path.exists():
            xlsx_files = sorted(input_path.glob("*.xlsx")) + sorted(input_path.glob("*.xlsm"))
            xlsx_files = [f for f in xlsx_files if not f.name.startswith("~$")]
            if xlsx_files:
                st.info(f"📁 **{len(xlsx_files)}** Excel file(s) found in `{input_path}`:")
                for f in xlsx_files:
                    st.markdown(f"- `{f.name}`  ({f.stat().st_size / 1024:.1f} KB)")
            else:
                st.warning(f"No Excel files found in `{input_path}`. Use **Generate Sample Files** in the sidebar.")
        else:
            st.error(f"Input directory `{input_path}` does not exist.")

        st.markdown("---")

        col_btn, col_status = st.columns([1, 3])
        start_clicked = col_btn.button(
            "▶ Start Automation",
            disabled=st.session_state["is_running"],
            type="primary",
            use_container_width=True,
        )

        if start_clicked and not st.session_state["is_running"]:
            st.session_state["is_running"]      = True
            st.session_state["workflow_result"] = None
            st.session_state["progress"]        = 0.0
            st.session_state["current_stage"]   = "Starting …"

            progress_bar = st.progress(0.0)
            stage_text   = st.empty()
            log_area     = st.empty()

            wf = RPAWorkflow(config)
            log_lines: list[str] = []

            for fraction, stage_name in wf.run_iter():
                st.session_state["progress"]      = fraction
                st.session_state["current_stage"] = stage_name
                progress_bar.progress(fraction)
                stage_text.markdown(f"**Stage:** {stage_name}")
                log_lines.append(f"✓  {stage_name}")
                log_area.text("\n".join(log_lines[-20:]))

            st.session_state["workflow_result"] = wf.result
            st.session_state["is_running"]      = False

            result: WorkflowResult = wf.result
            if result.status == WorkflowStatus.SUCCESS:
                st.success("✅ Automation completed successfully!")
            elif result.status == WorkflowStatus.PARTIAL_SUCCESS:
                st.warning("⚠️ Automation completed with some failures. Check the Reports tab.")
            else:
                st.error("❌ Automation failed. Check the Reports tab for details.")

        elif st.session_state.get("workflow_result") is not None:
            result: WorkflowResult = st.session_state["workflow_result"]
            _render_stage_results(result)

    # ======================================================================
    # TAB: Overview — KPI cards
    # ======================================================================
    with tab_overview:
        st.subheader("Run Overview")
        result: WorkflowResult | None = st.session_state.get("workflow_result")

        if result is None:
            st.info("Run the automation to see results here.")
        else:
            m = result.metrics
            # Row 1
            c1, c2, c3, c4 = st.columns(4)
            _kpi(c1, len(result.files_discovered),                     "Files Discovered")
            _kpi(c2, result.metrics.files_processed if m else "—",     "Files Processed")
            _kpi(c3, result.metrics.files_failed    if m else "—",     "Files Failed")
            _kpi(c4, result.status,                                     "Workflow Status")

            st.markdown("")
            # Row 2
            c5, c6, c7, c8 = st.columns(4)
            _kpi(c5, m.total_input_records     if m else "—",  "Total Input Records")
            _kpi(c6, m.total_cleaned_records   if m else "—",  "Cleaned Records")
            _kpi(c7, m.total_duplicate_records if m else "—",  "Duplicates Detected")
            _kpi(c8, m.total_review_records    if m else "—",  "Records for Review")

            st.markdown("")
            st.metric("Total Duration", f"{result.total_duration_s:.2f}s")

            # Per-file processing log
            if result.file_results:
                st.subheader("Per-File Processing Log")
                df_log = pd.DataFrame(result.file_results)
                st.dataframe(df_log, use_container_width=True)

    # ======================================================================
    # TAB: Data Preview
    # ======================================================================
    with tab_preview:
        result = st.session_state.get("workflow_result")
        if result is None:
            st.info("Run the automation to preview data here.")
        else:
            preview_tabs = st.tabs(["Master Data", "Exceptions", "Duplicates", "Failures"])

            with preview_tabs[0]:
                st.subheader("Master Data (first 500 rows)")
                if not result.master_df.empty:
                    # Hide internal columns
                    display_df = result.master_df[
                        [c for c in result.master_df.columns if not c.startswith("_missing_")]
                    ]
                    st.dataframe(display_df.head(500), use_container_width=True)
                    st.caption(f"Total rows: {len(result.master_df)}")
                else:
                    st.warning("No master data available.")

            with preview_tabs[1]:
                st.subheader("Exception Records")
                if not result.exceptions_df.empty:
                    st.dataframe(result.exceptions_df.head(500), use_container_width=True)
                    st.caption(f"Total exception records: {len(result.exceptions_df)}")
                else:
                    st.success("No exception records.")

            with preview_tabs[2]:
                st.subheader("Duplicate Records")
                if not result.duplicates_df.empty:
                    st.dataframe(result.duplicates_df.head(500), use_container_width=True)
                    st.caption(f"Total duplicate records: {len(result.duplicates_df)}")
                else:
                    st.success("No duplicate records detected.")

            with preview_tabs[3]:
                st.subheader("Failures & Errors")
                if result.failures:
                    st.dataframe(pd.DataFrame(result.failures), use_container_width=True)
                else:
                    st.success("No failures recorded.")

    # ======================================================================
    # TAB: Reports & Downloads
    # ======================================================================
    with tab_reports:
        result = st.session_state.get("workflow_result")
        if result is None:
            st.info("Run the automation to generate downloadable reports.")
        else:
            st.subheader("Download Reports")

            # Master workbook
            if result.output_workbook and Path(result.output_workbook).exists():
                with open(result.output_workbook, "rb") as fh:
                    st.download_button(
                        "📥 Download Master Excel Workbook",
                        data=fh.read(),
                        file_name=Path(result.output_workbook).name,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True,
                    )

            # Validation CSV
            if result.output_csv and Path(result.output_csv).exists():
                with open(result.output_csv, "rb") as fh:
                    st.download_button(
                        "📥 Download Validation Errors CSV",
                        data=fh.read(),
                        file_name=Path(result.output_csv).name,
                        mime="text/csv",
                        use_container_width=True,
                    )

            # Execution log
            if result.log_file and Path(result.log_file).exists():
                with open(result.log_file, "rb") as fh:
                    st.download_button(
                        "📥 Download Execution Log",
                        data=fh.read(),
                        file_name=Path(result.log_file).name,
                        mime="text/plain",
                        use_container_width=True,
                    )

            # Cleaning summary
            if result.cleaning_summary:
                st.subheader("Cleaning Operations Summary")
                rows = []
                for entry in result.cleaning_summary:
                    for op in entry.get("operations", []):
                        rows.append({
                            "File":       entry["source_file"],
                            "Operation":  op.get("operation", ""),
                            "Column":     op.get("column", ""),
                            "Affected":   op.get("affected", 0),
                            "Detail":     op.get("detail", ""),
                        })
                if rows:
                    st.dataframe(pd.DataFrame(rows), use_container_width=True)

    # ======================================================================
    # TAB: Performance
    # ======================================================================
    with tab_perf:
        result = st.session_state.get("workflow_result")
        if result is None:
            st.info("Run the automation to see performance metrics.")
        else:
            m = result.metrics
            if m is None:
                st.warning("Performance metrics not available.")
            else:
                st.subheader("Performance Metrics")
                st.caption(
                    "⚠️ **Note:** Manual processing times are *estimates* based on a "
                    "configurable assumed rate. They are not experimentally measured values."
                )

                display = m.to_display_dict()
                col_a, col_b = st.columns(2)
                items = list(display.items())
                half  = len(items) // 2
                for k, v in items[:half]:
                    col_a.metric(k, v)
                for k, v in items[half:]:
                    col_b.metric(k, v)

                # Bar chart: actual vs estimated manual time
                try:
                    import plotly.graph_objects as go

                    fig = go.Figure(
                        go.Bar(
                            x=["Automation (Actual)", "Manual (Estimated)"],
                            y=[m.automation_duration_s, m.estimated_manual_duration_s],
                            marker_color=["#1F3864", "#E64646"],
                            text=[
                                f"{m.automation_duration_s:.2f}s",
                                f"{m.estimated_manual_duration_s:.1f}s",
                            ],
                            textposition="outside",
                        )
                    )
                    fig.update_layout(
                        title="Processing Time: Automation vs Estimated Manual",
                        yaxis_title="Time (seconds)",
                        height=350,
                    )
                    st.plotly_chart(fig, use_container_width=True)
                except ImportError:
                    st.info("Install plotly for charts: `pip install plotly`")

                # Stage durations
                if result.stage_results:
                    st.subheader("Stage Durations")
                    stage_data = pd.DataFrame([
                        {
                            "Stage":    sr.stage_name,
                            "Status":   sr.status,
                            "Duration (s)": round(sr.duration_s, 4),
                            "Error":    sr.error,
                        }
                        for sr in result.stage_results
                    ])
                    st.dataframe(stage_data, use_container_width=True)


# ---------------------------------------------------------------------------
# Helper: render stage results table
# ---------------------------------------------------------------------------

def _render_stage_results(result: WorkflowResult) -> None:
    if not result.stage_results:
        return
    st.subheader("Stage Results")
    for sr in result.stage_results:
        icon = "✅" if sr.status == WorkflowStatus.SUCCESS else "❌"
        st.markdown(
            f"{icon} **Stage {sr.stage_number}: {sr.stage_name}** "
            f"— `{sr.duration_s:.3f}s`"
            + (f"  \n  ⚠️ {sr.error}" if sr.error else "")
        )


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    main()
