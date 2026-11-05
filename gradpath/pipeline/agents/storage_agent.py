"""
Storage Agent — Stage 4 (final) of the GradPath pipeline.

Responsibility:
    Collect all enriched chunks, deduplicate, and write final outputs:
    - data/processed/degree_roi_clean.parquet   (full cleaned dataset)
    - data/processed/filter_options.json        (unique values for UI filters)
    - data/processed/data_quality_summary.csv   (pipeline run statistics)

Also updates a pipeline run log at:
    pipeline/logs/pipeline_run.log
"""
import csv
import datetime
import json
import os
import sys
import threading

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from pipeline.agents.base_agent import BaseAgent
from pipeline.bus.message_bus import Bus, Message

BASE_DIR = os.path.join(os.path.dirname(__file__), "..", "..")
PROCESSED_DIR   = os.path.join(BASE_DIR, "data", "processed")
CLEAN_PARQUET   = os.path.join(PROCESSED_DIR, "degree_roi_clean.parquet")
FILTER_JSON     = os.path.join(PROCESSED_DIR, "filter_options.json")
QUALITY_CSV     = os.path.join(PROCESSED_DIR, "data_quality_summary.csv")
PIPELINE_LOG    = os.path.join(BASE_DIR, "pipeline", "logs", "pipeline_run.log")


class StorageAgent(BaseAgent):
    """
    Collects all enriched chunks into a single DataFrame, deduplicates,
    and writes the processed outputs when the end-of-stream sentinel arrives.
    """

    def __init__(self, bus: Bus):
        super().__init__(
            name="StorageAgent",
            bus=bus,
            in_channel="enriched",
            out_channel="done",       # final channel (used for monitoring)
        )
        self._chunks: list[pd.DataFrame] = []
        self._chunk_meta: list[dict] = []
        self._lock = threading.Lock()

    def process(self, message: Message) -> Message | None:
        with self._lock:
            self._chunks.append(message.payload)
            self._chunk_meta.append(message.metadata)

        self.log.debug(
            "buffered chunk %d from %s (%d rows)",
            len(self._chunks), message.metadata.get("source_file"), len(message.payload),
        )
        # Don't write until we receive the sentinel; return None (no per-chunk output)
        return None

    def flush(self, raw_total: int, source_files: list[str]):
        """
        Called by the orchestrator after the end-of-stream sentinel passes through.
        Merges all buffered chunks, deduplicates, and writes outputs.
        """
        self.log.info("flushing %d chunks to storage…", len(self._chunks))

        if not self._chunks:
            self.log.warning("no data to write — pipeline produced zero clean records")
            return

        os.makedirs(PROCESSED_DIR, exist_ok=True)
        os.makedirs(os.path.dirname(PIPELINE_LOG), exist_ok=True)

        # Merge and deduplicate
        df = pd.concat(self._chunks, ignore_index=True)
        before_dedup = len(df)
        df = df.drop_duplicates()
        after_dedup = len(df)

        self.log.info(
            "merged: %d rows, dedup removed %d → %d final rows",
            before_dedup, before_dedup - after_dedup, after_dedup,
        )

        # ── Write parquet ──────────────────────────────────────────────────────
        df.to_parquet(CLEAN_PARQUET, index=False)
        self.log.info("wrote: %s", CLEAN_PARQUET)

        # ── Write filter options ──────────────────────────────────────────────
        filter_opts = self._build_filter_options(df)
        with open(FILTER_JSON, "w") as f:
            json.dump(filter_opts, f, indent=2)
        self.log.info("wrote: %s", FILTER_JSON)

        # ── Write quality summary ─────────────────────────────────────────────
        quality = self._build_quality_summary(df, raw_total, source_files)
        quality.to_csv(QUALITY_CSV, index=False)
        self.log.info("wrote: %s", QUALITY_CSV)

        # ── Append to pipeline log ────────────────────────────────────────────
        self._append_run_log(df, raw_total, source_files)

        # Signal completion
        self.bus.put(
            "done",
            Message(
                source_agent=self.name,
                payload={"rows_written": after_dedup, "output": CLEAN_PARQUET},
                metadata={"completed_at": datetime.datetime.now().isoformat()},
            ),
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _build_filter_options(self, df: pd.DataFrame) -> dict:
        def sorted_unique(col):
            return sorted(df[col].dropna().unique().tolist()) if col in df.columns else []

        opts: dict = {
            "states": sorted_unique("state"),
            "school_types": sorted_unique("school_type"),
            "credential_levels": sorted_unique("credential_level"),
            "cip_titles": sorted_unique("cip_title"),
            "institutions": sorted_unique("institution_name"),
        }
        if "median_earnings" in df.columns:
            opts["earnings_range"] = {
                "min": int(df["median_earnings"].min()),
                "max": int(df["median_earnings"].max()),
            }
        if "median_debt" in df.columns:
            opts["debt_range"] = {
                "min": int(df["median_debt"].min()),
                "max": int(df["median_debt"].max()),
            }
        return opts

    def _build_quality_summary(
        self, df: pd.DataFrame, raw_total: int, source_files: list[str]
    ) -> pd.DataFrame:
        return pd.DataFrame([{
            "run_timestamp": datetime.datetime.now().isoformat(),
            "source_files": "; ".join(source_files),
            "raw_row_count": raw_total,
            "clean_row_count": len(df),
            "rows_removed": raw_total - len(df),
            "pct_retained": round(len(df) / max(raw_total, 1) * 100, 2),
            "unique_institutions": df["institution_name"].nunique() if "institution_name" in df.columns else None,
            "unique_cip_codes": df["cip_code"].nunique() if "cip_code" in df.columns else None,
            "unique_states": df["state"].nunique() if "state" in df.columns else None,
            "median_earnings_min": int(df["median_earnings"].min()) if "median_earnings" in df.columns else None,
            "median_earnings_max": int(df["median_earnings"].max()) if "median_earnings" in df.columns else None,
            "median_earnings_median": int(df["median_earnings"].median()) if "median_earnings" in df.columns else None,
            "median_debt_min": int(df["median_debt"].min()) if "median_debt" in df.columns else None,
            "median_debt_max": int(df["median_debt"].max()) if "median_debt" in df.columns else None,
            "median_debt_median": int(df["median_debt"].median()) if "median_debt" in df.columns else None,
        }])

    def _append_run_log(self, df: pd.DataFrame, raw_total: int, source_files: list[str]):
        fieldnames = [
            "run_timestamp", "source_files", "raw_rows", "clean_rows",
            "institutions", "cip_codes", "states",
        ]
        row = {
            "run_timestamp": datetime.datetime.now().isoformat(),
            "source_files": "; ".join(source_files),
            "raw_rows": raw_total,
            "clean_rows": len(df),
            "institutions": df["institution_name"].nunique() if "institution_name" in df.columns else 0,
            "cip_codes": df["cip_code"].nunique() if "cip_code" in df.columns else 0,
            "states": df["state"].nunique() if "state" in df.columns else 0,
        }
        write_header = not os.path.exists(PIPELINE_LOG)
        with open(PIPELINE_LOG, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if write_header:
                writer.writeheader()
            writer.writerow(row)
        self.log.info("appended run to: %s", PIPELINE_LOG)
