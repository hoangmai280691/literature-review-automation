
from pathlib import Path
import subprocess
import sys

import streamlit as st
import pandas as pd

ROOT = Path(__file__).resolve().parent
OUTPUT_FILE = ROOT / "output" / "vhb_screening_final.xlsx"

st.set_page_config(
    page_title="Literature Review Automation",
    page_icon="📚",
    layout="wide",
)

st.title("📚 Literature Review Automation")
st.write("Deduplication → VHB Reference → Journal Matching & Filtering")

st.info("Version 1: Runs the pipeline using existing project data.")

if st.button("▶ Run Pipeline", type="primary"):
    with st.spinner("Processing literature records..."):
        result = subprocess.run(
            [sys.executable, str(ROOT / "run_pipeline.py")],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )

    if result.returncode == 0:
        st.success("All 3 pipeline steps completed!")
        st.code(result.stdout[-5000:])
    else:
        st.error("Pipeline stopped with an error.")
        st.code(result.stderr[-5000:] or result.stdout[-5000:])

st.divider()

st.subheader("Latest VHB Screening Results")

if OUTPUT_FILE.exists():
    df = pd.read_excel(OUTPUT_FILE)

    st.metric("VHB-eligible articles", f"{len(df):,}")
    st.dataframe(df.head(30), use_container_width=True)

    with open(OUTPUT_FILE, "rb") as f:
        st.download_button(
            "⬇ Download Screening Results",
            data=f.read(),
            file_name="vhb_screening_final.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
else:
    st.warning("No screening results found. Run the pipeline first.")