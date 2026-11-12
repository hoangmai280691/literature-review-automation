# %%
from pathlib import Path
import pandas as pd
from IPython.display import display
import re
import unicodedata
import os

PROJECT_DIR = Path("..")

OUTPUT_DIR = Path(os.environ.get("LIT_REVIEW_OUTPUT_DIR", str(PROJECT_DIR / "output")))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
VHB_REFERENCE_OUTPUT_DIR = Path(os.environ.get("LIT_REVIEW_VHB_REFERENCE_DIR", str(PROJECT_DIR / "VHB")))
VHB_MATCHING_OUTPUT_DIR = Path(os.environ.get("LIT_REVIEW_VHB_MATCHING_DIR", str(PROJECT_DIR / "VHB_reference")))
VHB_MATCHING_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
REFERENCE_DIR = PROJECT_DIR / "reference"

MASTER_FILE = OUTPUT_DIR / "master_unique.xlsx"

# Set this after Kristiana confirms the VHB reference
VHB_FILE = REFERENCE_DIR / "vhb_2024_reference.xlsx"

ALLOWED_RATINGS = {"A+", "A", "B", "C"}

# %%
# Normalize ISSN and journal

def normalize_issn(value):
    if pd.isna(value):
        return None

    value = str(value).upper().strip()

    # Remove spaces and hyphens
    value = re.sub(r"[\s-]", "", value)

    return value if value else None


def normalize_journal(value):
    if pd.isna(value):
        return None

    value = str(value).lower().strip()
    value = unicodedata.normalize("NFKD", value)

    # Standardize ampersand
    value = value.replace("&", " and ")

    # Remove punctuation
    value = re.sub(r"[^\w\s]", " ", value)

    # Collapse whitespace
    value = re.sub(r"\s+", " ", value).strip()

    return value if value else None

# %%
# load MASTER file

master = pd.read_excel(MASTER_FILE)

required_columns = {"source", "issn"}

missing = required_columns - set(master.columns)

if missing:
    raise ValueError(
        f"Master dataset is missing required columns: {sorted(missing)}"
    )

print(f"Master records loaded: {len(master):,}")

# %%
# Prepare journal-level lookup candidates

master["normalized_issn"] = master["issn"].apply(normalize_issn)
master["normalized_journal"] = master["source"].apply(normalize_journal)


journals = (
    master[
        ["source", "issn", "normalized_journal", "normalized_issn"]
    ]
    .groupby(
        "normalized_journal",
        dropna=False
    )
    .agg(
        source=("source", "first"),

        observed_issns=(
            "issn",
            lambda x: " | ".join(
                sorted(set(x.dropna().astype(str)))
            )
        ),

        normalized_issns=(
            "normalized_issn",
            lambda x: " | ".join(
                sorted(set(x.dropna().astype(str)))
            )
        ),

        article_count=("source", "size")
    )
    .reset_index()
)

print(f"Unique source journals: {len(journals):,}")

display(
    journals.sort_values(
        "article_count",
        ascending=False
    ).head(20)
)

# %%
from pathlib import Path

print(Path.cwd())

# %%
VHB_REFERENCE_FILE = Path(__file__).resolve().parent / "vhb_reference_master.xlsx"

vhb_ref = pd.read_excel(VHB_REFERENCE_FILE)

print(f"VHB rating records: {len(vhb_ref):,}")
print(
    f"Unique VHB journals: "
    f"{vhb_ref['journal_normalized'].nunique():,}"
)

display(vhb_ref.head())

# %%
vhb_ref["normalized_issn"] = vhb_ref["issn"].apply(normalize_issn)
vhb_ref["normalized_journal"] = vhb_ref["journal"].apply(normalize_journal)

print(
    f"VHB records with ISSN: "
    f"{vhb_ref['normalized_issn'].notna().sum():,}"
)

print(
    f"VHB records without ISSN: "
    f"{vhb_ref['normalized_issn'].isna().sum():,}"
)

# %%
RATING_ORDER = {
    "A+": 4,
    "A": 3,
    "B": 2,
    "C": 1,
    "D": 0
}


def summarize_vhb(group):
    ratings = sorted(
        group["rating"].dropna().unique(),
        key=lambda x: RATING_ORDER.get(x, -1),
        reverse=True
    )

    areas = sorted(
        group["area"].dropna().astype(str).unique()
    )

    return pd.Series({
        "vhb_ratings": " | ".join(ratings),
        "vhb_best_rating": ratings[0] if ratings else None,
        "vhb_areas": " | ".join(areas),
        "vhb_rating_records": len(group)
    })


vhb_by_issn = (
    vhb_ref[
        vhb_ref["normalized_issn"].notna()
    ]
    .groupby("normalized_issn")
    .apply(summarize_vhb, include_groups=False)
    .reset_index()
)

print(
    f"Unique VHB ISSNs available for matching: "
    f"{len(vhb_by_issn):,}"
)

display(vhb_by_issn.head(10))

# %%
# Stage 1 — Exact ISSN linkage at journal level

journal_issn_long = (
    master[
        ["normalized_journal", "normalized_issn"]
    ]
    .dropna(subset=["normalized_journal", "normalized_issn"])
    .drop_duplicates()
)

issn_matches = journal_issn_long.merge(
    vhb_by_issn,
    on="normalized_issn",
    how="left",
    validate="many_to_one"
)

# Keep only successful ISSN matches
issn_matches = issn_matches[
    issn_matches["vhb_best_rating"].notna()
].copy()

print("=== EXACT ISSN LINKAGE ===")
print(f"Unique source journals       : {len(journals):,}")
print(
    f"Journals with ≥1 ISSN match  : "
    f"{issn_matches['normalized_journal'].nunique():,}"
)

display(issn_matches.head(20))

# %%
# Build one summarized VHB record per normalized journal title

# Rebuild VHB title lookup while preserving original journal title

vhb_by_title = (
    vhb_ref[vhb_ref["normalized_journal"].notna()]
    .groupby("normalized_journal")
    .apply(summarize_vhb, include_groups=False)
    .reset_index()
)

# Add original VHB journal title for readability
vhb_original_titles = (
    vhb_ref[
        ["normalized_journal", "journal"]
    ]
    .drop_duplicates("normalized_journal")
)

vhb_by_title = vhb_by_title.merge(
    vhb_original_titles,
    on="normalized_journal",
    how="left",
    validate="one_to_one"
)

# %%
# Stage 2 — Exact normalized journal-title linkage

# Start from journal-level table
journals_match = journals.copy()

# Mark journals already supported by exact ISSN
issn_matched_journals = set(
    issn_matches["normalized_journal"]
)

journals_match["issn_exact_match"] = (
    journals_match["normalized_journal"]
    .isin(issn_matched_journals)
)

# Exact journal-name lookup against VHB
journals_match = journals_match.merge(
    vhb_by_title,
    on="normalized_journal",
    how="left",
    validate="one_to_one"
)

journals_match["title_exact_match"] = (
    journals_match["vhb_best_rating"].notna()
)

print("=== JOURNAL LINKAGE STATUS ===")
print(f"Unique source journals      : {len(journals_match):,}")
print(
    f"Exact ISSN evidence         : "
    f"{journals_match['issn_exact_match'].sum():,}"
)
print(
    f"Exact journal-title match   : "
    f"{journals_match['title_exact_match'].sum():,}"
)
print(
    f"Still unresolved by title   : "
    f"{(~journals_match['title_exact_match']).sum():,}"
)

# %%
# Stage 2B — Practical matching for the 77 unresolved journals
# Rules:
# - ignore capitalization
# - ignore leading "The"
# - ignore a trailing acronym when it represents the journal title (e.g. JEMI)

ACRONYM_STOPWORDS = {"the", "of", "and", "for", "in", "on", "a", "an"}

def practical_key(value):
    if pd.isna(value):
        return None

    value = str(value).strip().casefold()
    value = value.replace("&", " and ")
    value = re.sub(r"[^\w\s]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()

    # Ignore leading "The"
    value = re.sub(r"^the\s+", "", value)

    # Ignore trailing acronym if it represents the journal title
    words = value.split()

    if len(words) >= 2:
        suffix = words[-1]

        content_words = [
            word for word in words[:-1]
            if word not in ACRONYM_STOPWORDS
        ]

        acronym = "".join(word[0] for word in content_words)

        if suffix == acronym:
            value = " ".join(words[:-1])

    return value


# Select journals not matched by ISSN or exact title
still_unmatched_df = journals_match[
    ~(
        journals_match["issn_exact_match"]
        | journals_match["title_exact_match"]
    )
].copy()

# Create matching keys
unmatched_2b = still_unmatched_df[
    [
        "source",
        "observed_issns",
        "article_count",
        "normalized_journal"
    ]
].copy()

unmatched_2b["practical_key"] = unmatched_2b["source"].apply(practical_key)

vhb_2b = vhb_ref.copy()
vhb_2b["practical_key"] = vhb_2b["journal"].apply(practical_key)


# Summarize VHB by practical journal key
vhb_2b_lookup = (
    vhb_2b[vhb_2b["practical_key"].notna()]
    .groupby("practical_key")
    .apply(summarize_vhb, include_groups=False)
    .reset_index()
)


# Match only the previously unresolved journals
stage2b_matches = unmatched_2b.merge(
    vhb_2b_lookup,
    on="practical_key",
    how="left",
    validate="many_to_one"
)

stage2b_matches["stage2b_match"] = (
    stage2b_matches["vhb_best_rating"].notna()
)


# Remaining journals go to fuzzy/manual review
still_unmatched_2b = (
    stage2b_matches[
        ~stage2b_matches["stage2b_match"]
    ]
    .copy()
    .reset_index(drop=True)
)


print("=== STAGE 2B — PRACTICAL MATCHING ===")
print(f"Starting unresolved : {len(still_unmatched_df):,}")
print(f"Additional matches  : {stage2b_matches['stage2b_match'].sum():,}")
print(f"Still unresolved    : {len(still_unmatched_2b):,}")

# %%
# ============================================================
# FINAL JOURNAL MATCHING + EXPORT
# ============================================================

from rapidfuzz import process, fuzz


# ------------------------------------------------------------
# 1. Automatic matches
# ------------------------------------------------------------

# Exact ISSN and/or exact normalized journal-title matches
exact_matched_df = journals_match[
    journals_match["issn_exact_match"]
    | journals_match["title_exact_match"]
].copy()


def get_match_method(row):
    if row["issn_exact_match"] and row["title_exact_match"]:
        return "exact_issn_and_title"
    elif row["issn_exact_match"]:
        return "exact_issn"
    else:
        return "exact_journal_title"


exact_matched_df["match_method"] = exact_matched_df.apply(
    get_match_method,
    axis=1
)


# Practical title matches from Stage 2B
practical_matched_df = stage2b_matches[
    stage2b_matches["stage2b_match"]
].copy()

practical_matched_df["match_method"] = "practical_title_match"


# Combine all automatic matches
matched_df = (
    pd.concat(
        [exact_matched_df, practical_matched_df],
        ignore_index=True
    )
    .drop_duplicates(subset=["normalized_journal"])
    .sort_values("source")
    .reset_index(drop=True)
)


# ------------------------------------------------------------
# 2. Remaining journals → fuzzy candidates
#    Stored only for optional manual review later
# ------------------------------------------------------------

matched_names = set(
    matched_df["normalized_journal"].dropna()
)

remaining_df = journals_match[
    ~journals_match["normalized_journal"].isin(matched_names)
][
    [
        "source",
        "observed_issns",
        "article_count",
        "normalized_journal"
    ]
].copy()


vhb_title_choices = (
    vhb_by_title["normalized_journal"]
    .dropna()
    .unique()
    .tolist()
)


def find_best_vhb_candidate(journal_name):
    result = process.extractOne(
        journal_name,
        vhb_title_choices,
        scorer=fuzz.ratio
    )

    if result is None:
        return pd.Series([None, None])

    candidate, score, _ = result

    return pd.Series([
        candidate,
        round(score, 1)
    ])


remaining_df[
    ["candidate_vhb_title", "similarity_score"]
] = remaining_df["normalized_journal"].apply(
    find_best_vhb_candidate
)


manual_review_df = remaining_df.merge(
    vhb_by_title,
    left_on="candidate_vhb_title",
    right_on="normalized_journal",
    how="left",
    validate="many_to_one",
    suffixes=("_source", "_vhb")
)


manual_review_df = manual_review_df[
    [
        "source",
        "observed_issns",
        "article_count",
        "normalized_journal_source",
        "candidate_vhb_title",
        "similarity_score",
        "vhb_best_rating",
        "vhb_ratings",
        "vhb_areas"
    ]
].rename(
    columns={
        "normalized_journal_source": "normalized_journal"
    }
).sort_values(
    "similarity_score",
    ascending=False
).reset_index(drop=True)


manual_review_df["manual_decision"] = ""
manual_review_df["manual_note"] = ""


# ------------------------------------------------------------
# 3. Summary
# ------------------------------------------------------------

summary_df = pd.DataFrame({
    "metric": [
        "Unique source journals",
        "Automatically matched",
        "Manual review deferred"
    ],
    "count": [
        len(journals_match),
        len(matched_df),
        len(manual_review_df)
    ]
})

print(summary_df.to_string(index=False))
print(
    "\nTotal accounted for:",
    len(matched_df) + len(manual_review_df)
)


# ------------------------------------------------------------
# 4. Export journal-matching workbook
# ------------------------------------------------------------

output_path = VHB_MATCHING_OUTPUT_DIR / "vhb_journal_matching_master.xlsx"

with pd.ExcelWriter(output_path, engine="openpyxl") as writer:

    summary_df.to_excel(
        writer,
        sheet_name="Summary",
        index=False
    )

    matched_df.to_excel(
        writer,
        sheet_name="Matched",
        index=False
    )

    manual_review_df.to_excel(
        writer,
        sheet_name="Manual_Review",
        index=False
    )


print(f"\nSaved: {output_path}")

# %%
# ============================================================
# ARTICLE-LEVEL VHB FILTER + EXPORT
# ============================================================

# Add normalized journal name to article master
master["normalized_journal"] = master["source"].apply(
    normalize_journal
)


# Keep journal-level VHB information needed for mapping
journal_vhb = matched_df[
    [
        "normalized_journal",
        "vhb_best_rating",
        "vhb_ratings",
        "vhb_areas",
        "match_method"
    ]
].drop_duplicates(
    subset=["normalized_journal"]
)


# Map VHB results back to all unique articles
articles_vhb = master.merge(
    journal_vhb,
    on="normalized_journal",
    how="left",
    validate="many_to_one"
)


# Label articles without an automatic VHB match
articles_vhb["vhb_best_rating"] = (
    articles_vhb["vhb_best_rating"]
    .fillna("NOT_LINKED")
)


# Keep only eligible VHB ratings
screening_df = articles_vhb[
    articles_vhb["vhb_best_rating"].isin(
        ["A+", "A", "B", "C"]
    )
].copy()


# ============================================================
# Summary
# ============================================================

print("Unique articles          :", len(articles_vhb))
print(
    "Articles linked to VHB   :",
    (articles_vhb["vhb_best_rating"] != "NOT_LINKED").sum()
)
print(
    "Articles with A+/A/B/C   :",
    len(screening_df)
)
print(
    "Articles excluded by VHB :",
    len(articles_vhb) - len(screening_df)
)


# ============================================================
# Export screening dataset
# ============================================================

output_path = OUTPUT_DIR / "master_vhb_screening.xlsx"

screening_df.to_excel(
    output_path,
    index=False
)

print("\nArticles exported:", len(screening_df))
print("Saved:", output_path)

# %%
# ============================================================
# CHECK VHB RESULTS BY DATABASE
# ============================================================

database_summary = (
    articles_vhb
    .groupby("database")
    .agg(
        unique_articles=("title", "size"),
        vhb_linked=(
            "vhb_best_rating",
            lambda x: (x != "NOT_LINKED").sum()
        ),
        vhb_eligible=(
            "vhb_best_rating",
            lambda x: x.isin(["A+", "A", "B", "C"]).sum()
        )
    )
)

print(database_summary)

# %%
# ============================================================
# APPLY MANUAL JOURNAL MATCHES
# ============================================================

# Load completed manual review
manual_review = pd.read_excel(
    VHB_MATCHING_OUTPUT_DIR / "vhb_journal_matching_master.xlsx",
    sheet_name="Manual_Review"
)

# Keep confirmed manual matches
manual_matches = manual_review[
    manual_review["manual_decision"]
    .fillna("")
    .str.strip()
    .str.upper()
    .eq("MATCH")
].copy()

manual_matches["match_method"] = "manual_match"


# Combine automatic + manual journal matches
final_matched_df = (
    pd.concat(
        [matched_df, manual_matches],
        ignore_index=True
    )
    .drop_duplicates(subset=["normalized_journal"])
    .reset_index(drop=True)
)


# Map final journal matches back to articles
journal_vhb_final = final_matched_df[
    [
        "normalized_journal",
        "vhb_best_rating",
        "vhb_ratings",
        "vhb_areas",
        "match_method"
    ]
].drop_duplicates(
    subset=["normalized_journal"]
)

articles_vhb_final = (
    master
    .drop(
        columns=[
            "vhb_best_rating",
            "vhb_ratings",
            "vhb_areas",
            "match_method"
        ],
        errors="ignore"
    )
    .merge(
        journal_vhb_final,
        on="normalized_journal",
        how="left",
        validate="many_to_one"
    )
)

articles_vhb_final["vhb_best_rating"] = (
    articles_vhb_final["vhb_best_rating"]
    .fillna("NOT_LINKED")
)


# ============================================================
# COMPARE BEFORE vs AFTER MANUAL REVIEW
# ============================================================

eligible_ratings = ["A+", "A", "B", "C"]

eligible_before = (
    articles_vhb["vhb_best_rating"]
    .isin(eligible_ratings)
    .sum()
)

eligible_after = (
    articles_vhb_final["vhb_best_rating"]
    .isin(eligible_ratings)
    .sum()
)

print("Manual journals matched   :", len(manual_matches))
print("Eligible before manual    :", eligible_before)
print("Eligible after manual     :", eligible_after)
print("Eligible articles rescued :", eligible_after - eligible_before)

# %%
review_path = VHB_MATCHING_OUTPUT_DIR / "vhb_journal_matching_master.xlsx"

manual_review = pd.read_excel(
    review_path,
    sheet_name="Manual_Review"
)

print(manual_review["manual_decision"].value_counts(dropna=False))

# %%
# ============================================================
# FINAL SCREENING DATASET
# ============================================================

eligible_ratings = ["A+", "A", "B", "C"]

screening_final = articles_vhb_final[
    articles_vhb_final["vhb_best_rating"].isin(eligible_ratings)
].copy()


# ============================================================
# FINAL SUMMARY
# ============================================================

print("Unique articles             :", len(articles_vhb_final))
print("Automatic eligible          :", eligible_before)
print("Manual journals matched     :", len(manual_matches))
print("Eligible articles rescued   :", eligible_after - eligible_before)
print("Final VHB-eligible articles :", len(screening_final))


# ============================================================
# EXPORT
# ============================================================

output_path = OUTPUT_DIR / "vhb_screening_final.xlsx"

screening_final.to_excel(
    output_path,
    index=False
)

print("\nArticles exported           :", len(screening_final))
print("Saved                       :", output_path)