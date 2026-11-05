"""
Load-once data access shared by api.py and app_routes.py.
"""
import os
from functools import lru_cache

import numpy as np
import pandas as pd

from config import CLEAN_PARQUET, SCHOOL_DIRECTORY_CSV, STATE_TAX_CSV, SOURCE_REGISTRY_CSV, PROCESSED_DIR

STATE_TAX_BRACKETS_CSV = os.path.join(PROCESSED_DIR, "state_tax_brackets.csv")

_df: pd.DataFrame | None = None


def get_df() -> pd.DataFrame:
    global _df
    if _df is None:
        if not os.path.exists(CLEAN_PARQUET):
            raise RuntimeError(
                f"Processed data not found at {CLEAN_PARQUET}. "
                "Run: python src/prepare_data.py"
            )
        _df = pd.read_parquet(CLEAN_PARQUET)
        # Convert all numeric columns to plain Python floats for JSON serialization
        for col in _df.select_dtypes(include=[np.floating, np.integer]).columns:
            _df[col] = _df[col].astype(float)
    return _df


def to_records(df: pd.DataFrame) -> list:
    """Convert DataFrame to list of dicts, replacing NaN with None."""
    return [
        {k: (None if (isinstance(v, float) and np.isnan(v)) or v is pd.NA else v)
         for k, v in row.items()}
        for row in df.to_dict(orient="records")
    ]


@lru_cache(maxsize=1)
def get_directory() -> pd.DataFrame:
    """School directory keyed by institution_id; empty frame if not yet built."""
    if not os.path.exists(SCHOOL_DIRECTORY_CSV):
        return pd.DataFrame(columns=["institution_id", "school_name", "address", "city", "state", "zip",
                                     "school_type", "latitude", "longitude", "source_year"])
    return pd.read_csv(SCHOOL_DIRECTORY_CSV, dtype={"institution_id": str, "zip": str})


@lru_cache(maxsize=1)
def get_tax_reference() -> pd.DataFrame:
    if not os.path.exists(STATE_TAX_CSV):
        return pd.DataFrame()
    return pd.read_csv(STATE_TAX_CSV, dtype=str).fillna("")


@lru_cache(maxsize=1)
def get_tax_brackets() -> pd.DataFrame:
    if not os.path.exists(STATE_TAX_BRACKETS_CSV):
        return pd.DataFrame(columns=["state_code", "tax_year", "filing_status", "lower_bound", "rate_pct"])
    return pd.read_csv(STATE_TAX_BRACKETS_CSV, dtype={"state_code": str, "tax_year": str, "filing_status": str})


@lru_cache(maxsize=1)
def get_source_registry() -> pd.DataFrame:
    if not os.path.exists(SOURCE_REGISTRY_CSV):
        return pd.DataFrame()
    return pd.read_csv(SOURCE_REGISTRY_CSV, dtype=str).fillna("")


STATE_NAMES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
    "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "DC": "District of Columbia",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois",
    "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana",
    "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
    "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon",
    "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota",
    "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia",
    "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
    "PR": "Puerto Rico", "GU": "Guam", "VI": "U.S. Virgin Islands", "AS": "American Samoa",
    "MP": "Northern Mariana Islands", "FM": "Micronesia", "MH": "Marshall Islands", "PW": "Palau",
}
