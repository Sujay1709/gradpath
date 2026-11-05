"""
Central configuration: all paths and column constants.
Change RAW_FOS_CSV to point to a different year's file if needed.
"""
import os

# ── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASET_DIR = os.path.join(BASE_DIR, "..", "dataset", "College_Scorecard_Raw_Data_11022026")

RAW_FOS_CSV = os.path.join(DATASET_DIR, "Most-Recent-Cohorts-Field-of-Study.csv")
RAW_INST_CSV = os.path.join(DATASET_DIR, "Most-Recent-Cohorts-Institution.csv")

PROCESSED_DIR = os.path.join(BASE_DIR, "data", "processed")
CLEAN_PARQUET = os.path.join(PROCESSED_DIR, "degree_roi_clean.parquet")
FILTER_JSON = os.path.join(PROCESSED_DIR, "filter_options.json")
QUALITY_CSV = os.path.join(PROCESSED_DIR, "data_quality_summary.csv")

# ── GradPath app reference datasets (built by src/build_reference_data.py) ──
DEGREE_ROI_LATEST_CSV = os.path.join(PROCESSED_DIR, "degree_roi_latest.csv")
SCHOOL_DIRECTORY_CSV = os.path.join(PROCESSED_DIR, "school_directory.csv")
SOURCE_REGISTRY_CSV = os.path.join(PROCESSED_DIR, "data_source_registry.csv")
# Hand-verified, versioned in git — not generated.
STATE_TAX_CSV = os.path.join(PROCESSED_DIR, "state_tax_reference.csv")
SAMPLES_DIR = os.path.join(BASE_DIR, "data", "samples")
PLAN_DEMO_CSV = os.path.join(SAMPLES_DIR, "student_plan_demo.csv")
STATIC_DIR = os.path.join(BASE_DIR, "static")

SCORECARD_URL = "https://collegescorecard.ed.gov/data/"
SCORECARD_RELEASE = "2026-10-05"     # data.yaml `version` of the downloaded release
SCORECARD_DOWNLOADED = "2026-11-02"  # from the raw folder name _11022026
DATA_YEAR_LABEL = "2021–22 completers (earnings measured 2023–24)"

# ── Source columns (Field of Study CSV) ──────────────────────────────────────
FOS_COLS = [
    "UNITID", "INSTNM", "CONTROL",
    "CIPCODE", "CIPDESC", "CREDLEV", "CREDDESC",
    "IPEDSCOUNT1",
    "EARN_COUNT_WNE_HI_2YR", "EARN_MDN_HI_2YR",
    "EARN_MDN_HI_1YR",
    "DEBT_ALL_PP_ANY_MDN",    # post-program, any loan — primary debt measure
    "DEBT_ALL_STGP_ANY_MDN",  # still-enrolled subgroup (supplemental)
]

# Institution file columns to join
INST_COLS = ["UNITID", "STABBR"]

# ── Suppression strings ───────────────────────────────────────────────────────
SUPPRESSION_VALUES = {"PrivacySuppressed", "PS", "NULL", "NA", ""}

# ── Column rename map: raw → app names ───────────────────────────────────────
COLUMN_RENAME = {
    "UNITID":               "institution_id",
    "INSTNM":               "institution_name",
    "STABBR":               "state",
    "CONTROL":              "school_type",
    "CIPCODE":              "cip_code",
    "CIPDESC":              "cip_title",
    "CREDLEV":              "credential_level_code",
    "CREDDESC":             "credential_level",
    "IPEDSCOUNT1":          "ipeds_count",
    "EARN_COUNT_WNE_HI_2YR":"cohort_size",
    "EARN_MDN_HI_2YR":      "median_earnings",       # PRIMARY: 2yr post-completion
    "EARN_MDN_HI_1YR":      "median_earnings_1yr",
    "DEBT_ALL_PP_ANY_MDN":  "median_debt",           # PRIMARY: post-program any loan
    "DEBT_ALL_STGP_ANY_MDN":"median_debt_enrolled",
}

# Earnings source year (derived from filename — most-recent cohort)
EARNINGS_COHORT = "2021–22 completers, measured 2023–24"
DEBT_DEFINITION = "Completers who received federal loans — post-program median cumulative debt"
DATA_SOURCE_FILE = "Most-Recent-Cohorts-Field-of-Study.csv (College Scorecard, Nov 2026 release)"
