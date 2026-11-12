from pathlib import Path
from io import BytesIO
import os
import subprocess
import sys
import tempfile
import time

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
OUTPUT_FILE = ROOT / "output" / "vhb_screening_final.xlsx"
RESULT_NAME = "vhb_screening_final.xlsx"
MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

st.set_page_config(page_title="Literature Review Automation", page_icon="📚", layout="wide")

if "result_bytes" not in st.session_state:
    st.session_state.result_bytes = None
if "result_source" not in st.session_state:
    st.session_state.result_source = None
if "result_count" not in st.session_state:
    st.session_state.result_count = None
if "result_message" not in st.session_state:
    st.session_state.result_message = None


def clear_results():
    st.session_state.result_bytes = None
    st.session_state.result_source = None
    st.session_state.result_count = None    
    st.session_state.result_message = None


st.title("📚 Literature Review Automation")
st.write("Deduplication → VHB Reference → Journal Matching & Filtering")
st.info("Version 1: Runs the pipeline using existing project data or uploaded files.")

st.subheader("Choose Data Source")
data_source = st.radio(
    "Choose data source",
    ["Existing Data", "Uploaded Files"],
    horizontal=True,
    on_change=clear_results,
)

uploaded_files = []
if data_source == "Uploaded Files":
    st.subheader("Upload Research Data")
    uploaded_files = st.file_uploader(
        "Select EBSCO CSV or Emerald RIS files",
        type=["csv", "ris"],
        accept_multiple_files=True,
        on_change=clear_results,
    )
    if uploaded_files:
        st.success(f"{len(uploaded_files)} file(s) selected.")
        for file in uploaded_files:
            st.write(f"📄 {file.name}")

if st.button("▶ Run Pipeline", type="primary"):
    clear_results()
    if data_source == "Uploaded Files" and not uploaded_files:
        st.warning("Please upload at least one CSV or RIS file.")
    else:
        with st.spinner("Processing literature records..."):
            # Keep temporary input, intermediate workbooks, and final output isolated.
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                env = os.environ.copy()
                expected_file = OUTPUT_FILE

                if data_source == "Uploaded Files":
                    raw_dir = temp_path / "data-raw"
                    output_dir = temp_path / "output"
                    vhb_reference_dir = temp_path / "VHB"
                    matching_dir = temp_path / "VHB_reference"
                    for directory in (raw_dir, output_dir, vhb_reference_dir, matching_dir):
                        directory.mkdir(parents=True, exist_ok=True)

                    for file in uploaded_files:
                        filename = Path(file.name).name
                        database_dir = raw_dir / ("EBSCO" if Path(filename).suffix.lower() == ".csv" else "Emerald")
                        database_dir.mkdir(parents=True, exist_ok=True)
                        (database_dir / filename).write_bytes(file.getvalue())

                    env["LIT_REVIEW_RAW_DIR"] = str(raw_dir)
                    env["LIT_REVIEW_OUTPUT_DIR"] = str(output_dir)
                    env["LIT_REVIEW_VHB_REFERENCE_DIR"] = str(vhb_reference_dir)
                    env["LIT_REVIEW_VHB_MATCHING_DIR"] = str(matching_dir)
                    expected_file = output_dir / RESULT_NAME
                else:
                    # Prevent an inherited upload configuration from affecting Existing Data.
                    for key in (
                        "LIT_REVIEW_RAW_DIR", "LIT_REVIEW_OUTPUT_DIR",
                        "LIT_REVIEW_VHB_REFERENCE_DIR", "LIT_REVIEW_VHB_MATCHING_DIR",
                    ):
                        env.pop(key, None)

                started_ns = time.time_ns()
                result = subprocess.run(
                    [sys.executable, str(ROOT / "run_pipeline.py")],
                    cwd=ROOT,
                    env=env,
                    capture_output=True,
                    text=True,
                )

                if result.returncode != 0:
                    st.error("Pipeline stopped with an error.")
                    st.code((result.stderr or "")[-5000:] or (result.stdout or "")[-5000:])
                elif not expected_file.is_file():
                    st.error(f"Pipeline finished but the expected output was not found: {expected_file}")
                    st.code((result.stdout or "")[-3000:])
                elif expected_file.stat().st_mtime_ns < started_ns:
                    st.error("The output file was not updated during this run. Previous results were not shown.")
                    st.code((result.stdout or "")[-3000:])
                else:
                    try:
                        data = expected_file.read_bytes()
                        df = pd.read_excel(BytesIO(data))
                        if df.empty:
                            st.warning("Pipeline completed, but no VHB-eligible articles were found.")
                        else:
                            st.session_state.result_bytes = data
                            st.session_state.result_source = data_source
                            st.session_state.result_count = len(df)
                            st.session_state.result_message = (
                                "Uploaded files processed successfully!"
                                if data_source == "Uploaded Files"
                                else "Existing data pipeline completed!"
                            )
                    except Exception as exc:
                        st.error(f"The output Excel file could not be read: {exc}")

if st.session_state.result_bytes is not None:
    st.divider()
    st.subheader(f"VHB Screening Results — {st.session_state.result_source}")
    st.success(st.session_state.result_message)
    st.metric("VHB-eligible articles", f"{st.session_state.result_count:,}")
    df = pd.read_excel(BytesIO(st.session_state.result_bytes))
    st.dataframe(df.head(30), use_container_width=True)
    st.download_button(
        "⬇ Download Screening Results",
        data=st.session_state.result_bytes,
        file_name=("vhb_screening_uploaded.xlsx" if st.session_state.result_source == "Uploaded Files" else RESULT_NAME),
        mime=MIME_XLSX,)