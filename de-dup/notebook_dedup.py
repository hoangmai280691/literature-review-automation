# %%
######################## NOTEBOOK #################################

from pathlib import Path
import pandas as pd
from IPython.display import display
import re
import unicodedata

# Notebook is located in leadership-review/de-dup/
PROJECT_DIR = Path("..")

RAW_DIR = PROJECT_DIR / "data-raw"
OUTPUT_DIR = PROJECT_DIR / "output"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

print("Project directory:", PROJECT_DIR.resolve())
print("Raw directory:", RAW_DIR.resolve())
print("Output directory:", OUTPUT_DIR.resolve())

def extract_database(filepath):
    """
    Identify source database from the parent folder.

    Examples:
    data-raw/EBSCO/...   -> EBSCO
    data-raw/Emerald/... -> Emerald
    """
    return filepath.parent.name

# %%
# Reusable normalization and metadata helper functions

def normalize_doi(value):
    """
    Standardize DOI values for exact matching.
    """
    if pd.isna(value):
        return None

    value = str(value).strip().lower()

    # Remove common DOI prefixes
    value = re.sub(r"^https?://(dx\.)?doi\.org/", "", value)
    value = re.sub(r"^doi:\s*", "", value)

    value = value.strip()
    return value if value else None


def normalize_title(value):
    """
    Conservative title normalization for exact matching.
    Keeps all words; only standardizes case, Unicode,
    punctuation and whitespace.
    """
    if pd.isna(value):
        return None

    value = str(value).lower().strip()
    value = unicodedata.normalize("NFKD", value)

    # Remove punctuation
    value = re.sub(r"[^\w\s]", " ", value)

    # Collapse repeated whitespace
    value = re.sub(r"\s+", " ", value).strip()

    return value if value else None


def extract_family(filename):
    """
    Extract search family from filename.

    Examples:
    EBSCO_F3_001.csv -> F3
    Emerald_F1_01_crisis-leadership_AND_crisis-management.ris -> F1
    """
    match = re.search(r"(?:^|_)(F\d+)(?:_|\.|$)", filename, flags=re.IGNORECASE)

    if not match:
        return "UNKNOWN"

    return match.group(1).upper()


def extract_database(filepath):
    """
    Identify source database from the parent folder.

    Examples:
    data-raw/EBSCO/...  -> EBSCO
    data-raw/Emerald/... -> Emerald
    """
    return filepath.parent.name

# %%
# # Discover raw files and identify their source

# #files = sorted([
# #    file
#     for file in RAW_DIR.rglob("*")
#     if file.is_file() and file.suffix.lower() in {".csv", ".ris"}
# ])

# ============================================================
# FILE DISCOVERY — EMERALD ONLY
# ============================================================

files = sorted([
    file
    for file in RAW_DIR.rglob("*")
    if file.is_file() and file.suffix.lower() in {".csv", ".ris"}
])

if not files:
    raise FileNotFoundError(
        f"No supported raw files found under: {RAW_DIR / DATABASE}"
    )

print("Databases:", sorted({extract_database(file) for file in files}))
print("Files found:", len(files))

if not files:
    raise FileNotFoundError(
        f"No supported raw files found under: {RAW_DIR}"
    )

file_inventory = pd.DataFrame({
    "file_path": files,
    "source_file": [file.name for file in files],
    "database": [extract_database(file) for file in files],
    "file_type": [file.suffix.lower() for file in files],
    "search_family": [extract_family(file.name) for file in files],
})

print(f"Files found: {len(file_inventory)}")

print("\nFiles by database:")
print(file_inventory["database"].value_counts())

print("\nFiles by database and family:")
print(
    file_inventory
    .groupby(["database", "search_family"])
    .size()
)

# %%
# Raw readers → canonical schema

CANONICAL_COLUMNS = [
    "title",
    "publicationDate",
    "authors",
    "abstract",
    "source",
    "issn",
    "doi",
    "url",
    "database",
    "search_family",
    "source_file",
]


def read_ebsco(file):
    """
    Read one EBSCO CSV file and map it to the canonical schema.
    """
    temp = pd.read_csv(file)

    out = pd.DataFrame({
        "title": temp["title"],
        "publicationDate": temp["publicationDate"],
        "authors": temp["authors"],
        "abstract": temp["abstract"],
        "source": temp["source"],
        "issn": temp["issn"],
        "doi": temp["doi"],
        "url": temp["plink"],
    })

    out["database"] = extract_database(file)
    out["search_family"] = extract_family(file.name)
    out["source_file"] = file.name

    return out[CANONICAL_COLUMNS]


def read_emerald(file):
    """
    Read one Emerald RIS file and map it to the canonical schema.
    """
    records = []
    current = {}

    with open(file, "r", encoding="utf-8-sig", errors="replace") as f:
        for raw_line in f:
            line = raw_line.rstrip("\n")

            if "  - " not in line:
                continue

            tag, value = line.split("  - ", 1)
            tag = tag.strip()
            value = value.strip()

            if tag == "AU":
                current.setdefault("AU", []).append(value)

            elif tag == "ER":
                records.append(current)
                current = {}

            else:
                current[tag] = value

    rows = []

    for record in records:
        rows.append({
            "title": record.get("T1"),
            "publicationDate": record.get("Y1") or record.get("PY"),
            "authors": "; ".join(record.get("AU", [])),
            "abstract": record.get("AB"),
            "source": record.get("JO"),
            "issn": record.get("SN"),
            "doi": record.get("DO"),
            "url": record.get("UR"),
            "database": extract_database(file),
            "search_family": extract_family(file.name),
            "source_file": file.name,
        })

    return pd.DataFrame(rows, columns=CANONICAL_COLUMNS)

# %%
# Load all raw files into the canonical schema

frames = []

for file in files:

    if file.suffix.lower() == ".csv":
        temp = read_ebsco(file)

    elif file.suffix.lower() == ".ris":
        temp = read_emerald(file)

    else:
        continue

    frames.append(temp)


df = pd.concat(frames, ignore_index=True)

print(f"Files loaded: {len(files)}")
print(f"Raw records loaded: {len(df)}")

print("\nRecords by database:")
print(df["database"].value_counts())

print("\nRecords by database and search family:")
print(
    df.groupby(["database", "search_family"])
      .size()
)

# %%
# Normalize identifiers for exact matching

df["normalized_doi"] = df["doi"].apply(normalize_doi)
df["normalized_title"] = df["title"].apply(normalize_title)

print("Normalization complete.")

print(f"Records with DOI: {df['normalized_doi'].notna().sum()}")
print(f"Records without DOI: {df['normalized_doi'].isna().sum()}")
print(f"Records with title: {df['normalized_title'].notna().sum()}")
print(f"Records without title: {df['normalized_title'].isna().sum()}")

# %%
# Validate schema

required_columns = {"title", "authors", "source", "doi", "abstract", "issn"}

missing = required_columns - set(df.columns)

if missing:
    raise ValueError(f"Missing required columns: {sorted(missing)}")

# %%
# Normalize identifiers

df["normalized_doi"] = df["doi"].apply(normalize_doi)
df["normalized_title"] = df["title"].apply(normalize_title)

print("Normalization completed.")
print(f"Records with DOI: {df['normalized_doi'].notna().sum()}")
print(f"Records without DOI: {df['normalized_doi'].isna().sum()}")

# %%
# DOI appears more than once
df["doi_duplicate"] = (
    df["normalized_doi"].notna()
    & df.duplicated("normalized_doi", keep=False)
)

# Title appears more than once
df["title_duplicate"] = (
    df["normalized_title"].notna()
    & df.duplicated("normalized_title", keep=False)
)

def classify_exact_match(row):
    if row["doi_duplicate"]:
        return "DOI_MATCH"

    if row["title_duplicate"] and pd.isna(row["normalized_doi"]):
        return "TITLE_MATCH_NO_DOI"

    if row["title_duplicate"]:
        return "TITLE_MATCH_CHECK"

    return "UNIQUE_EXACT"


df["match_status"] = df.apply(classify_exact_match, axis=1)
match_summary = (
    df["match_status"]
    .value_counts()
    .rename_axis("match_status")
    .reset_index(name="records")
)

display(match_summary)

# %%
# Dataset quality summary

exact_candidate_mask = df["match_status"] != "UNIQUE_EXACT"

summary = pd.DataFrame({
    "metric": [
        "Files loaded",
        "Raw records",
        "Records with DOI",
        "Records without DOI",
        "Unique DOI values",
        "DOI-match records",
        "Title-match records",
        "Exact-match candidate records"
    ],
    "value": [
        len(files),
        len(df),
        df["normalized_doi"].notna().sum(),
        df["normalized_doi"].isna().sum(),
        df["normalized_doi"].nunique(),
        df["doi_duplicate"].sum(),
        df["title_duplicate"].sum(),
        exact_candidate_mask.sum()
    ]
})

display(summary)

# %%
def combine_unique(series):
    """
    Combine unique non-empty values while preserving provenance.
    Example: F1, F3, F1 -> F1 | F3
    """
    values = (
        series
        .dropna()
        .astype(str)
        .str.strip()
    )

    values = [v for v in values if v]

    return " | ".join(sorted(set(values))) if values else None


# Records WITH DOI:
# same normalized DOI = same article -> consolidate
with_doi = df[df["normalized_doi"].notna()].copy()

# Records WITHOUT DOI:
# keep untouched for now
without_doi = df[df["normalized_doi"].isna()].copy()


# Columns whose provenance should be aggregated
provenance_cols = [
    "database",
    "search_family",
    "source_file",
    "accessionNumber"
]


def consolidate_doi_group(group):
    # Start with one canonical record
    record = group.iloc[0].copy()

    # Aggregate provenance from every occurrence
    for col in provenance_cols:
        if col in group.columns:
            record[col] = combine_unique(group[col])

    # Number of raw occurrences represented by this master record
    record["record_occurrences"] = len(group)

    return record


doi_master = (
    with_doi
    .groupby("normalized_doi", group_keys=False, sort=False)
    .apply(consolidate_doi_group, include_groups=False)
    .reset_index(drop=True)
)


# No-DOI records are NOT automatically consolidated
without_doi["record_occurrences"] = 1


master = pd.concat(
    [doi_master, without_doi],
    ignore_index=True
)

print("Raw records:", len(df))
print("Master records after DOI consolidation:", len(master))
print("Records removed through DOI consolidation:", len(df) - len(master))

# %%
# Ensure no record lost during consolidation
represented_records = master["record_occurrences"].sum()

print("Raw records:", len(df))
print("Records represented in master:", represented_records)

assert represented_records == len(df), \
    "QC failed: some raw records were lost during consolidation."

print("Consolidation QC passed.")

# %%


# %%
# ============================================================
# EXPORT MASTER UNIQUE DATASET
# ============================================================

MASTER_FILE = OUTPUT_DIR / "master_unique.xlsx"

master.to_excel(
    MASTER_FILE,
    index=False
)

print(f"Master dataset exported to: {MASTER_FILE.resolve()}")
print(f"Records exported: {len(master):,}")

# %%
# ============================================================
# CROSS-DATABASE NON-DOI / TITLE DUPLICATE AUDIT
# ============================================================

ebsco = df[df["database"].eq("EBSCO")].copy()
emerald = df[df["database"].eq("Emerald")].copy()

# Match EBSCO and Emerald by normalized title
title_candidates = ebsco.merge(
    emerald,
    on="normalized_title",
    how="inner",
    suffixes=("_ebsco", "_emerald")
)

# Ignore missing normalized titles
title_candidates = title_candidates[
    title_candidates["normalized_title"].notna()
].copy()


# ------------------------------------------------------------
# Classify title matches by DOI availability
# ------------------------------------------------------------

def classify_title_candidate(row):

    doi_e = row["normalized_doi_ebsco"]
    doi_m = row["normalized_doi_emerald"]

    # Both have DOI
    if pd.notna(doi_e) and pd.notna(doi_m):

        if doi_e == doi_m:
            return "DOI_CONFIRMED"

        return "SAME_TITLE_DIFFERENT_DOI_CHECK"

    # One database has DOI, the other does not
    if pd.notna(doi_e) or pd.notna(doi_m):
        return "TITLE_MATCH_ONE_DOI_MISSING"

    # Neither has DOI
    return "TITLE_MATCH_BOTH_NO_DOI"


title_candidates["match_type"] = title_candidates.apply(
    classify_title_candidate,
    axis=1
)


# ------------------------------------------------------------
# Summary
# ------------------------------------------------------------

summary = (
    title_candidates["match_type"]
    .value_counts()
    .rename_axis("match_type")
    .reset_index(name="candidate_pairs")
)

display(summary)


# ------------------------------------------------------------
# Non-DOI candidates requiring verification
# ------------------------------------------------------------

non_doi_candidates = title_candidates[
    title_candidates["match_type"].isin([
        "TITLE_MATCH_ONE_DOI_MISSING",
        "TITLE_MATCH_BOTH_NO_DOI"
    ])
].copy()

display(
    non_doi_candidates[
        [
            "normalized_title",
            "title_ebsco",
            "title_emerald",
            "normalized_doi_ebsco",
            "normalized_doi_emerald",
            "source_ebsco",
            "source_emerald",
            "match_type"
        ]
    ]
)


