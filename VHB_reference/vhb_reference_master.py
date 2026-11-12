# %%
from pathlib import Path
import pandas as pd
from IPython.display import display
import re
import os

# Notebook: leadership-review/VHB_reference/vhb_reference_master.ipynb
REFERENCE_DIR = Path(".")
DATA_DIR = REFERENCE_DIR / "data"
VHB_DIR = Path(os.environ.get("LIT_REVIEW_VHB_REFERENCE_DIR", "../VHB"))

PDF_PATTERN = "*.pdf"

VHB_DIR.mkdir(parents=True, exist_ok=True)

print("PDF folder:", DATA_DIR.resolve())
print("Output folder:", VHB_DIR.resolve())

# %%
pdf_files = sorted(DATA_DIR.glob(PDF_PATTERN))

if not pdf_files:
    raise FileNotFoundError(
        f"No PDF files found in {DATA_DIR.resolve()}"
    )

print(f"VHB PDF files found: {len(pdf_files)}")

for i, file in enumerate(pdf_files, start=1):
    print(f"{i:02d}. {file.name}")

# %%
import pdfplumber

sample_file = pdf_files[0]

with pdfplumber.open(sample_file) as pdf:
    print(f"File: {sample_file.name}")
    print(f"Pages: {len(pdf.pages)}")

    first_page = pdf.pages[0]
    tables = first_page.extract_tables()

    print(f"Tables detected on page 1: {len(tables)}")

    if tables:
        for row in tables[0][:10]:
            print(row)

# %%
ISSN_PATTERN = re.compile(r"(\d{4}-\d{3}[\dXx])$")


def parse_title_issn(value):
    """
    Split:
    'Academy of Management Journal 1948-0989'
    into:
    ('Academy of Management Journal', '1948-0989')
    """
    if not value:
        return None, None

    value = str(value).replace("\n", " ").strip()
    value = re.sub(r"\s+", " ", value)

    match = ISSN_PATTERN.search(value)

    if not match:
        return value, None

    issn = match.group(1).upper()
    title = value[:match.start()].strip()

    return title, issn


def parse_votes_publisher(value):
    """
    Split:
    '85 Academy of Management Link'
    into:
    (85, 'Academy of Management')
    """
    if not value:
        return None, None

    value = str(value).replace("\n", " ").strip()
    value = re.sub(r"\s+", " ", value)

    match = re.match(r"^(\d+)\s+(.*)$", value)

    if not match:
        return None, value

    votes = int(match.group(1))
    publisher = match.group(2)

    # Remove trailing 'Link'
    publisher = re.sub(r"\s+Link$", "", publisher).strip()

    return votes, publisher

# %%
def extract_area(filename):
    stem = Path(filename).stem

    match = re.search(
        r"Area_rating_(.+)$",
        stem
    )

    if not match:
        return None

    return match.group(1)

# %%
def parse_rating(value):
    """
    Examples:
        'A+'                 -> ('A+', None)
        'B'                  -> ('B', None)
        'A legal-normative'  -> ('A', 'legal-normative')
    """
    if not value:
        return None, None

    value = str(value).strip()

    match = re.match(r"^(A\+|A|B|C|D)(?:\s+(.+))?$", value)

    if not match:
        return None, None

    rating = match.group(1)
    dimension = match.group(2)

    return rating, dimension


def parse_vhb_pdf(file):
    records = []
    area = extract_area(file.name)

    with pdfplumber.open(file) as pdf:

        for page_number, page in enumerate(pdf.pages, start=1):

            tables = page.extract_tables()

            for table in tables:

                if not table:
                    continue

                current_category = None

                for row in table:

                    if not row:
                        continue

                    # Clean cells
                    row = [
                        cell.replace("\n", " ").strip()
                        if isinstance(cell, str)
                        else cell
                        for cell in row
                    ]

                    # -------------------------------------------------
                    # WI schema
                    # category | title+ISSN | rating | votes+publisher
                    # -------------------------------------------------
                    if area == "WI" and len(row) >= 4:

                        category = row[0]
                        first_col = row[1]
                        rating_raw = row[2]
                        votes_col = row[3]

                        # Category is only printed when a new section begins
                        if category:
                            current_category = category

                    # -------------------------------------------------
                    # Standard schema
                    # title+ISSN | rating | votes+publisher | ...
                    # -------------------------------------------------
                    else:

                        if len(row) < 3:
                            continue

                        first_col = row[0]
                        rating_raw = row[1]
                        votes_col = row[2]

                    # Parse rating + optional dimension
                    rating, rating_dimension = parse_rating(rating_raw)

                    if rating is None:
                        continue

                    journal, issn = parse_title_issn(first_col)
                    votes, publisher = parse_votes_publisher(votes_col)

                    records.append({
                        "journal": journal,
                        "issn": issn,
                        "rating": rating,
                        "rating_dimension": rating_dimension,
                        "votes_ge_rating_pct": votes,
                        "publisher": publisher,
                        "area": area,
                        "category": current_category if area == "WI" else None,
                        "source_file": file.name,
                        "source_page": page_number
                    })

    return records

# %%
all_records = []

for file in pdf_files:
    records = parse_vhb_pdf(file)
    all_records.extend(records)

    print(
        f"{file.name}: "
        f"{len(records):,} records extracted"
    )

vhb = pd.DataFrame(all_records)

print()
print(f"PDF files processed: {len(pdf_files)}")
print(f"Total VHB rating records: {len(vhb):,}")

# %%
print("Columns:")
print(vhb.columns.tolist())

print("\nRatings:")
print(vhb["rating"].value_counts(dropna=False))

print("\nRecords by area:")
print(
    vhb["area"]
    .value_counts()
    .sort_index()
)

print("\nMissing ISSN:")
print(vhb["issn"].isna().sum())

display(vhb.head(20))

# %%
import unicodedata


def normalize_issn(value):
    if pd.isna(value):
        return None

    value = str(value).upper().strip()
    value = re.sub(r"[^0-9X]", "", value)

    if len(value) != 8:
        return None

    return f"{value[:4]}-{value[4:]}"


def normalize_journal(value):
    if pd.isna(value):
        return None

    value = str(value).lower().strip()

    # Normalize Unicode
    value = unicodedata.normalize("NFKD", value)

    # Remove punctuation
    value = re.sub(r"[^\w\s]", " ", value)

    # Collapse whitespace
    value = re.sub(r"\s+", " ", value).strip()

    return value if value else None


vhb_ref = vhb.copy()

vhb_ref["issn_normalized"] = vhb_ref["issn"].apply(normalize_issn)
vhb_ref["journal_normalized"] = vhb_ref["journal"].apply(normalize_journal)

print(f"Reference records: {len(vhb_ref):,}")

# %%
vhb_ref["issn_missing"] = vhb_ref["issn_normalized"].isna()

print(
    f"Records with ISSN: "
    f"{(~vhb_ref['issn_missing']).sum():,}"
)

print(
    f"Records without ISSN: "
    f"{vhb_ref['issn_missing'].sum():,}"
)

# %%
duplicate_mask = vhb_ref.duplicated(
    subset=[
        "journal_normalized",
        "issn_normalized",
        "rating",
        "area"
    ],
    keep=False
)

exact_duplicates = (
    vhb_ref.loc[duplicate_mask]
    .sort_values(
        ["journal_normalized", "area", "rating"]
    )
)

print(
    f"Records involved in exact duplicates: "
    f"{len(exact_duplicates):,}"
)

display(exact_duplicates.head(20))

# %%
journal_area_summary = (
    vhb_ref
    .groupby("journal_normalized", dropna=False)
    .agg(
        areas=("area", "nunique"),
        ratings=("rating", lambda x: " | ".join(sorted(set(x)))),
        records=("rating", "size")
    )
    .reset_index()
)

multi_area = (
    journal_area_summary[
        journal_area_summary["areas"] > 1
    ]
    .sort_values(
        ["areas", "journal_normalized"],
        ascending=[False, True]
    )
)

print(
    f"Unique normalized journals: "
    f"{vhb_ref['journal_normalized'].nunique():,}"
)

print(
    f"Journals appearing in >1 area: "
    f"{len(multi_area):,}"
)

display(multi_area.head(20))

# %%
print("=== VHB REFERENCE MASTER QC ===")

print(f"PDF files processed       : {vhb_ref['source_file'].nunique()}")
print(f"Rating records            : {len(vhb_ref):,}")
print(f"Unique journals           : {vhb_ref['journal_normalized'].nunique():,}")
print(f"Missing normalized journal: {vhb_ref['journal_normalized'].isna().sum():,}")
print(f"Missing normalized ISSN   : {vhb_ref['issn_normalized'].isna().sum():,}")

print("\nRatings:")
print(vhb_ref["rating"].value_counts().sort_index())

print("\nAreas:")
print(vhb_ref["area"].value_counts().sort_index())

# %%
parsed_files = set(vhb_ref["source_file"].unique())
all_files = {file.name for file in pdf_files}

missing_files = sorted(all_files - parsed_files)

print(f"PDF files supplied : {len(all_files)}")
print(f"PDF files parsed   : {len(parsed_files)}")
print(f"PDF files missing  : {len(missing_files)}")

for file in missing_files:
    print("-", file)

# %%
for filename in missing_files:
    file = DATA_DIR / filename

    print("\n" + "=" * 80)
    print(filename)

    with pdfplumber.open(file) as pdf:
        print(f"Pages: {len(pdf.pages)}")

        for page_number, page in enumerate(pdf.pages[:2], start=1):
            tables = page.extract_tables()

            print(
                f"\nPage {page_number} - "
                f"tables detected: {len(tables)}"
            )

            for table_number, table in enumerate(tables, start=1):
                print(f"Table {table_number}")

                for row in table[:8]:
                    print(row)

# %%
# Final column order
export_columns = [
    "journal",
    "journal_normalized",
    "issn",
    "issn_normalized",
    "rating",
    "rating_dimension",
    "votes_ge_rating_pct",
    "publisher",
    "area",
    "category",
    "source_file",
    "source_page"
]

vhb_export = (
    vhb_ref[export_columns]
    .sort_values(
        ["journal_normalized", "area", "rating"],
        na_position="last"
    )
    .reset_index(drop=True)
)

output_file = VHB_DIR / "vhb_reference_master.xlsx"

vhb_export.to_excel(
    output_file,
    index=False
)

print("=== EXPORT COMPLETE ===")
print(f"File    : {output_file.resolve()}")
print(f"Records : {len(vhb_export):,}")
print(f"Journals: {vhb_export['journal_normalized'].nunique():,}")