"""
Enrichment Agent — Stage 3 of the GradPath pipeline.

Responsibility:
    Receive validated chunks and add derived fields:
    - debt_to_earnings
    - earnings_to_debt  (NaN when debt = 0)
    - earnings_debt_difference
    - school_type label normalization
    - earnings_cohort annotation
    - debt_definition annotation

Then forward enriched chunks to the 'enriched' channel.
"""
import sys
import os

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from pipeline.agents.base_agent import BaseAgent
from pipeline.bus.message_bus import Bus, Message

EARNINGS_COHORT  = "2021–22 completers, measured 2023–24"
DEBT_DEFINITION  = "Completers — federal loans, post-program median cumulative debt"

# Normalize any legacy numeric CONTROL codes to strings (if raw data has codes)
CONTROL_MAP = {
    "1": "Public",
    "2": "Private, nonprofit",
    "3": "Private, for-profit",
}


class EnrichmentAgent(BaseAgent):
    """
    Adds derived metrics and annotations to validated chunks.
    Forwards enriched chunks to the 'enriched' channel.
    """

    def __init__(self, bus: Bus):
        super().__init__(
            name="EnrichmentAgent",
            bus=bus,
            in_channel="validated",
            out_channel="enriched",
        )

    def process(self, message: Message) -> Message | None:
        df: pd.DataFrame = message.payload.copy()
        meta = dict(message.metadata)

        # ── 1. Normalize school_type codes → readable labels ──────────────────
        if "school_type" in df.columns:
            df["school_type"] = df["school_type"].astype(str).replace(CONTROL_MAP)

        # ── 2. Debt-to-earnings ratio ─────────────────────────────────────────
        if {"median_earnings", "median_debt"}.issubset(df.columns):
            df["debt_to_earnings"] = (
                df["median_debt"] / df["median_earnings"]
            ).round(3)

            # ── 3. Earnings-to-debt (avoid infinity when debt=0) ──────────────
            df["earnings_to_debt"] = np.where(
                df["median_debt"] > 0,
                (df["median_earnings"] / df["median_debt"]).round(3),
                np.nan,
            )

            # ── 4. Earnings minus debt ────────────────────────────────────────
            df["earnings_debt_difference"] = (
                df["median_earnings"] - df["median_debt"]
            ).round(0)

        # ── 5. Annotate with source metadata ─────────────────────────────────
        df["earnings_cohort"] = EARNINGS_COHORT
        df["debt_definition"] = DEBT_DEFINITION

        meta["enriched_by"] = self.name
        meta["new_columns"] = ["debt_to_earnings", "earnings_to_debt",
                               "earnings_debt_difference", "earnings_cohort",
                               "debt_definition"]

        self.log.debug(
            "enriched chunk %s: %d rows",
            meta.get("source_file"), len(df),
        )

        return Message(source_agent=self.name, payload=df, metadata=meta)
