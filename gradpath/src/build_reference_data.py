"""
Build the GradPath app reference datasets from already-downloaded source files.

Reads:
    data/processed/degree_roi_clean.parquet          (from prepare_data.py)
    dataset/.../Most-Recent-Cohorts-Institution.csv  (College Scorecard)
    data/processed/state_tax_reference.csv           (hand-verified, in git)

Writes:
    data/processed/school_directory.csv
    data/processed/degree_roi_latest.csv
    data/processed/data_source_registry.csv
    data/samples/student_plan_demo.csv               (synthetic)

Run from gradpath/:  python3 src/build_reference_data.py
No address, coordinate or tax value is ever inferred: missing source values stay blank.
"""
import os
import sys
from datetime import datetime, timezone

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import (  # noqa: E402
    CLEAN_PARQUET, RAW_INST_CSV, PROCESSED_DIR, SAMPLES_DIR,
    SCHOOL_DIRECTORY_CSV, DEGREE_ROI_LATEST_CSV, SOURCE_REGISTRY_CSV,
    STATE_TAX_CSV, PLAN_DEMO_CSV, SUPPRESSION_VALUES,
    SCORECARD_URL, SCORECARD_RELEASE, SCORECARD_DOWNLOADED, DATA_YEAR_LABEL,
)

CONTROL_LABELS = {"1": "Public", "2": "Private, nonprofit", "3": "Private, for-profit"}
DIRECTORY_SOURCE_YEAR = f"Most-Recent-Cohorts-Institution (release {SCORECARD_RELEASE})"


def build_school_directory(inst_path: str) -> pd.DataFrame:
    cols = ["UNITID", "INSTNM", "ADDR", "CITY", "STABBR", "ZIP", "CONTROL", "LATITUDE", "LONGITUDE",
            "TUITIONFEE_IN", "TUITIONFEE_OUT", "COSTT4_A"]
    inst = pd.read_csv(inst_path, usecols=cols, dtype=str, low_memory=False)
    inst = inst.replace(list(SUPPRESSION_VALUES), pd.NA)
    # Spec columns first; the three published-cost columns after them are used
    # only to pre-fill (editable) tuition on the My Plan page.
    out = pd.DataFrame({
        "institution_id": inst["UNITID"].str.strip(),
        "school_name": inst["INSTNM"].str.strip(),
        "address": inst["ADDR"].str.strip(),
        "city": inst["CITY"].str.strip(),
        "state": inst["STABBR"].str.strip(),
        "zip": inst["ZIP"].str.strip(),
        "school_type": inst["CONTROL"].map(CONTROL_LABELS),
        "latitude": pd.to_numeric(inst["LATITUDE"], errors="coerce"),
        "longitude": pd.to_numeric(inst["LONGITUDE"], errors="coerce"),
        "source_year": DIRECTORY_SOURCE_YEAR,
        "tuition_fees_in_state": pd.to_numeric(inst["TUITIONFEE_IN"], errors="coerce"),
        "tuition_fees_out_of_state": pd.to_numeric(inst["TUITIONFEE_OUT"], errors="coerce"),
        "cost_of_attendance_academic_year": pd.to_numeric(inst["COSTT4_A"], errors="coerce"),
    })
    return out.drop_duplicates("institution_id")


def build_degree_roi_latest(roi: pd.DataFrame, directory: pd.DataFrame) -> pd.DataFrame:
    geo = directory[["institution_id", "address", "city", "zip"]]
    out = roi.merge(geo, on="institution_id", how="left")
    out["source_year"] = DATA_YEAR_LABEL
    return out


def build_source_registry(processed_at: str) -> pd.DataFrame:
    rows = [
        {
            "dataset_name": "College Scorecard — Field of Study (Most-Recent-Cohorts-Field-of-Study.csv)",
            "source_organization": "U.S. Department of Education",
            "source_url": SCORECARD_URL,
            "source_year": DATA_YEAR_LABEL,
            "downloaded_at": SCORECARD_DOWNLOADED,
            "processed_at": processed_at,
            "important_limitations": (
                "Covers federal-aid recipients only; small cohorts are privacy-suppressed "
                "(~96% of rows removed); earnings are 2 years after completion; "
                "median debt is federal loan debt, not cost of attendance."
            ),
        },
        {
            "dataset_name": "College Scorecard — Institution (Most-Recent-Cohorts-Institution.csv)",
            "source_organization": "U.S. Department of Education",
            "source_url": SCORECARD_URL,
            "source_year": f"Release {SCORECARD_RELEASE}",
            "downloaded_at": SCORECARD_DOWNLOADED,
            "processed_at": processed_at,
            "important_limitations": (
                "Used only for address, city, state, ZIP, control and coordinates. "
                "~7.5% of institutions do not report a street address or coordinates; "
                "those fields are left blank."
            ),
        },
    ]
    if os.path.exists(STATE_TAX_CSV):
        tax = pd.read_csv(STATE_TAX_CSV, dtype=str)
        for _, t in tax.iterrows():
            rows.append({
                "dataset_name": f"State tax reference — {t['state_name']} ({t['state_code']})",
                "source_organization": "State revenue department (official site)",
                "source_url": t["official_source_url"],
                "source_year": f"Tax year {t['tax_year']}",
                "downloaded_at": t["last_verified"],
                "processed_at": processed_at,
                "important_limitations": "Educational summary of verified fields only; not tax advice.",
            })
    return pd.DataFrame(rows)


def build_plan_demo() -> pd.DataFrame:
    """Three fictional students. Values are invented for demonstration only."""
    base = {"is_synthetic": True, "note": "DEMONSTRATION DATA — fictional student, not a real person"}
    personas = [
        dict(persona="Demo A — in-state public, bachelor's", in_state=True, start_year=2027, grad_year=2031,
             current_savings=4000, annual_savings_contribution=1500, annual_grants=6000,
             existing_loan_balance=0, annual_borrowing=5500, loan_interest_rate_pct=6.52,
             annual_tuition=11000, annual_living=13000, expected_work_state="TX",
             salary_conservative=42000, salary_expected=55000, salary_aspirational=72000),
        dict(persona="Demo B — private nonprofit, bachelor's", in_state=False, start_year=2027, grad_year=2031,
             current_savings=12000, annual_savings_contribution=2000, annual_grants=22000,
             existing_loan_balance=0, annual_borrowing=7500, loan_interest_rate_pct=6.52,
             annual_tuition=48000, annual_living=16000, expected_work_state="NY",
             salary_conservative=48000, salary_expected=62000, salary_aspirational=85000),
        dict(persona="Demo C — community college, associate's", in_state=True, start_year=2026, grad_year=2028,
             current_savings=1500, annual_savings_contribution=1200, annual_grants=4000,
             existing_loan_balance=2000, annual_borrowing=2500, loan_interest_rate_pct=6.52,
             annual_tuition=4200, annual_living=11000, expected_work_state="FL",
             salary_conservative=32000, salary_expected=40000, salary_aspirational=50000),
    ]
    return pd.DataFrame([{**base, **p} for p in personas])


def main():
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    os.makedirs(SAMPLES_DIR, exist_ok=True)
    processed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    directory = build_school_directory(RAW_INST_CSV)
    directory.to_csv(SCHOOL_DIRECTORY_CSV, index=False)
    print(f"school_directory.csv: {len(directory):,} institutions, "
          f"{directory['address'].isna().sum():,} without a reported street address")

    roi = pd.read_parquet(CLEAN_PARQUET)
    latest = build_degree_roi_latest(roi, directory)
    latest.to_csv(DEGREE_ROI_LATEST_CSV, index=False)
    print(f"degree_roi_latest.csv: {len(latest):,} programs, "
          f"{latest['city'].isna().sum():,} without a directory match")

    build_source_registry(processed_at).to_csv(SOURCE_REGISTRY_CSV, index=False)
    print("data_source_registry.csv written")

    build_plan_demo().to_csv(PLAN_DEMO_CSV, index=False)
    print("student_plan_demo.csv written (synthetic)")


if __name__ == "__main__":
    main()
