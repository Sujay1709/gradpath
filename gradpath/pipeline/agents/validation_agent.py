"""
Validation Agent — Stage 2 of the GradPath pipeline.

Responsibility:
    Receive raw chunks from the Ingestion Agent, apply schema validation
    and data-quality checks, then forward clean chunks to the Enrichment Agent.

Checks performed:
    1. Normalize suppression strings (PS, PrivacySuppressed, NULL, NA, "")
    2. Rename columns to app schema
    3. Convert numeric fields safely
    4. Drop rows missing required fields
    5. Drop rows with impossible values (earnings ≤ 0, debt < 0)
    6. Attach per-chunk quality metrics to the message metadata
"""
import sys
import os

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from pipeline.agents.base_agent import BaseAgent
from pipeline.bus.message_bus import Bus, Message

# ── Schema ────────────────────────────────────────────────────────────────────

SUPPRESSION_VALUES = {"PrivacySuppressed", "PS", "NULL", "NA", ""}

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
    "EARN_MDN_HI_2YR":      "median_earnings",
    "EARN_MDN_HI_1YR":      "median_earnings_1yr",
    "DEBT_ALL_PP_ANY_MDN":  "median_debt",
    "DEBT_ALL_STGP_ANY_MDN":"median_debt_enrolled",
}

REQUIRED_COLS = ["institution_name", "cip_code", "credential_level", "median_earnings", "median_debt"]
NUMERIC_COLS  = ["median_earnings", "median_earnings_1yr", "median_debt", "median_debt_enrolled",
                 "cohort_size", "ipeds_count"]


class ValidationAgent(BaseAgent):
    """
    Validates and normalizes raw data chunks.
    Forwards clean chunks to the 'validated' channel.
    Routes invalid-chunk errors to 'dead_letter'.
    """

    def __init__(self, bus: Bus):
        super().__init__(
            name="ValidationAgent",
            bus=bus,
            in_channel="raw",
            out_channel="validated",
        )

    def process(self, message: Message) -> Message | None:
        df: pd.DataFrame = message.payload
        meta = dict(message.metadata)
        raw_count = len(df)

        # 1. Normalize suppression
        df = df.replace(list(SUPPRESSION_VALUES), np.nan)

        # 2. Rename columns (only rename columns that exist in this chunk)
        rename_map = {k: v for k, v in COLUMN_RENAME.items() if k in df.columns}
        df = df.rename(columns=rename_map)

        # 3. Convert numerics
        for col in NUMERIC_COLS:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        # 4. Drop rows missing required fields that are present
        required_present = [c for c in REQUIRED_COLS if c in df.columns]
        df = df.dropna(subset=required_present)

        # 5. Drop impossible values
        if "median_earnings" in df.columns:
            df = df[df["median_earnings"] > 0]
        if "median_debt" in df.columns:
            df = df[df["median_debt"] >= 0]

        clean_count = len(df)

        # Drop chunk entirely if nothing survived
        if clean_count == 0:
            self.log.debug("chunk fully suppressed from %s, dropping", meta.get("source_file"))
            self.stats["dropped"] += 1
            return None

        meta.update({
            "raw_rows": raw_count,
            "clean_rows": clean_count,
            "suppressed_rows": raw_count - clean_count,
            "validated_by": self.name,
        })

        self.log.debug(
            "chunk %s: %d raw → %d clean (-%d suppressed)",
            meta.get("source_file"), raw_count, clean_count, raw_count - clean_count,
        )

        return Message(source_agent=self.name, payload=df, metadata=meta)
