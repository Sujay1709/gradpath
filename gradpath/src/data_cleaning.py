"""
Data cleaning functions for the GradPath pipeline.
Each function is pure: takes a DataFrame, returns a cleaned DataFrame.
"""
import pandas as pd
import numpy as np
from typing import Set

from config import SUPPRESSION_VALUES, COLUMN_RENAME


def load_raw(fos_path: str, inst_path: str) -> pd.DataFrame:
    """Load raw CSVs and join state from institution file."""
    from config import FOS_COLS, INST_COLS

    print(f"  Loading Field of Study data from:\n    {fos_path}")
    fos = pd.read_csv(fos_path, usecols=FOS_COLS, dtype=str, low_memory=False)
    print(f"  Raw rows: {len(fos):,}")

    print(f"  Loading institution data from:\n    {inst_path}")
    inst = pd.read_csv(inst_path, usecols=INST_COLS, dtype=str, low_memory=False)

    # Join state via UNITID
    df = fos.merge(inst, on="UNITID", how="left")
    print(f"  Rows after join: {len(df):,}")
    return df


def normalize_suppression(df: pd.DataFrame, suppress_vals: Set[str] = SUPPRESSION_VALUES) -> pd.DataFrame:
    """Replace all privacy-suppression strings and blanks with NaN."""
    return df.replace(list(suppress_vals), np.nan)


def to_numeric_safe(df: pd.DataFrame, cols: list) -> pd.DataFrame:
    """Coerce specified columns to float; non-parseable values become NaN."""
    for col in cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def apply_schema(df: pd.DataFrame) -> pd.DataFrame:
    """Rename raw columns to app-level names."""
    return df.rename(columns=COLUMN_RENAME)


def filter_required(df: pd.DataFrame) -> pd.DataFrame:
    """Drop rows missing any field essential for the dashboard."""
    required = ["institution_name", "cip_code", "credential_level", "median_earnings", "median_debt"]
    before = len(df)
    df = df.dropna(subset=required)
    print(f"  Dropped {before - len(df):,} rows missing required fields → {len(df):,} remain")
    return df


def filter_impossible(df: pd.DataFrame) -> pd.DataFrame:
    """Remove records with impossible numeric values."""
    before = len(df)
    # Earnings must be positive
    df = df[df["median_earnings"] > 0]
    # Debt must be non-negative (zero is valid — full scholarship)
    df = df[df["median_debt"] >= 0]
    print(f"  Dropped {before - len(df):,} rows with impossible values → {len(df):,} remain")
    return df


def deduplicate(df: pd.DataFrame) -> pd.DataFrame:
    """Remove exact duplicate rows."""
    before = len(df)
    df = df.drop_duplicates()
    print(f"  Dropped {before - len(df):,} exact duplicates → {len(df):,} remain")
    return df
