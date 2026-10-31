# Literature Review Automation

A Python-based automation tool for streamlining academic literature review workflows, with a simple Streamlit interface.

## What It Does

- **Deduplication:** Cleans and consolidates academic records from multiple databases.
- **Journal Matching:** Standardizes journal information and matches records against VHB journal ratings.
- **Quality Screening:** Applies journal-quality criteria and exports structured Excel results.
- **Manual Review Support:** Flags uncertain matches for further validation.

## Tech Stack

Python · Pandas · Streamlit · pdfplumber · RapidFuzz

## Workflow

**Database Exports → Deduplication → Journal Matching → Quality Screening → Excel Output**

## Run Locally

```bash
python3 -m streamlit run app.py
```

The current MVP uses locally configured input files and reference data. Research datasets are not included in this repository.

## Status

**MVP v1 — Functional local prototype**

Built to demonstrate data-quality validation, research workflow automation, and reproducible screening processes.