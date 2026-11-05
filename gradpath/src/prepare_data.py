"""
GradPath data preparation pipeline.

Run once before starting the API:
    python src/prepare_data.py

Outputs (all in data/processed/):
    degree_roi_clean.parquet   — cleaned dataset for the API
    filter_options.json        — unique values for sidebar filters
    data_quality_summary.csv   — cleaning statistics
"""
import os
import sys
import json
import datetime

# Allow imports from src/ when run directly
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd

from config import (
    RAW_FOS_CSV, RAW_INST_CSV,
    PROCESSED_DIR, CLEAN_PARQUET, FILTER_JSON, QUALITY_CSV,
    DATA_SOURCE_FILE, EARNINGS_COHORT, DEBT_DEFINITION,
)
from data_cleaning import (
    load_raw, normalize_suppression, to_numeric_safe,
    apply_schema, filter_required, filter_impossible, deduplicate,
)
from metrics import add_metrics


NUMERIC_COLS = [
    "median_earnings", "median_earnings_1yr",
    "median_debt", "median_debt_enrolled",
    "cohort_size", "ipeds_count",
]


def build_filter_options(df: pd.DataFrame) -> dict:
    """Collect unique sorted values for all filterable fields."""
    def sorted_unique(col):
        return sorted(df[col].dropna().unique().tolist())

    options = {
        "states": sorted_unique("state"),
        "school_types": sorted_unique("school_type"),
        "credential_levels": sorted_unique("credential_level"),
        "cip_titles": sorted_unique("cip_title"),
        "institutions": sorted_unique("institution_name"),
        "earnings_range": {
            "min": int(df["median_earnings"].min()),
            "max": int(df["median_earnings"].max()),
        },
        "debt_range": {
            "min": int(df["median_debt"].min()),
            "max": int(df["median_debt"].max()),
        },
    }
    if "cohort_size" in df.columns:
        options["cohort_size_range"] = {
            "min": int(df["cohort_size"].dropna().min()) if df["cohort_size"].notna().any() else 0,
            "max": int(df["cohort_size"].dropna().max()) if df["cohort_size"].notna().any() else 0,
        }
    return options


def build_quality_summary(raw_count: int, df: pd.DataFrame, source_file: str) -> pd.DataFrame:
    """Build a one-row quality summary for audit / display."""
    suppressed_removed = raw_count - len(df)  # rough upper bound
    summary = {
        "source_file": source_file,
        "processed_at": datetime.datetime.utcnow().isoformat(),
        "earnings_cohort": EARNINGS_COHORT,
        "debt_definition": DEBT_DEFINITION,
        "raw_row_count": raw_count,
        "clean_row_count": len(df),
        "rows_removed": raw_count - len(df),
        "unique_institutions": df["institution_name"].nunique(),
        "unique_programs_cip": df["cip_code"].nunique(),
        "unique_states": df["state"].nunique(),
        "median_earnings_min": int(df["median_earnings"].min()),
        "median_earnings_max": int(df["median_earnings"].max()),
        "median_earnings_overall_median": int(df["median_earnings"].median()),
        "median_debt_min": int(df["median_debt"].min()),
        "median_debt_max": int(df["median_debt"].max()),
        "median_debt_overall_median": int(df["median_debt"].median()),
    }
    return pd.DataFrame([summary])


def main():
    os.makedirs(PROCESSED_DIR, exist_ok=True)

    print("=" * 60)
    print("GradPath — Data Preparation Pipeline")
    print("=" * 60)

    # 1. Load
    df = load_raw(RAW_FOS_CSV, RAW_INST_CSV)
    raw_count = len(df)

    # 2. Normalize suppression
    df = normalize_suppression(df)

    # 3. Rename to app schema
    df = apply_schema(df)

    # 4. Convert numeric columns
    df = to_numeric_safe(df, NUMERIC_COLS)

    # 5. Filter required fields
    df = filter_required(df)

    # 6. Remove impossible values
    df = filter_impossible(df)

    # 7. Deduplicate
    df = deduplicate(df)

    # 8. Add derived metrics
    df = add_metrics(df)

    # 9. Annotate with metadata
    df["earnings_cohort"] = EARNINGS_COHORT
    df["debt_definition"] = DEBT_DEFINITION

    # 10. Write outputs
    print(f"\n  Writing cleaned data → {CLEAN_PARQUET}")
    df.to_parquet(CLEAN_PARQUET, index=False)

    print(f"  Writing filter options → {FILTER_JSON}")
    opts = build_filter_options(df)
    with open(FILTER_JSON, "w") as f:
        json.dump(opts, f, indent=2)

    print(f"  Writing quality summary → {QUALITY_CSV}")
    build_quality_summary(raw_count, df, DATA_SOURCE_FILE).to_csv(QUALITY_CSV, index=False)

    print("\n" + "=" * 60)
    print(f"  Done. {len(df):,} clean records across "
          f"{df['institution_name'].nunique():,} institutions "
          f"and {df['cip_code'].nunique():,} CIP codes.")
    print("=" * 60)


if __name__ == "__main__":
    main()
