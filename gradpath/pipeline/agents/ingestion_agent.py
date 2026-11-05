"""
Ingestion Agent — Stage 1 of the GradPath pipeline.

Responsibility:
    Read raw CSV files in chunks and push each chunk as a Message
    onto the 'raw' channel for the Validation Agent.

Supports:
    - Single file or a list of files
    - Configurable chunk size (default 5000 rows)
    - Detects file format from extension (.csv, .parquet)
"""
import os
from typing import Sequence

import pandas as pd

from pipeline.agents.base_agent import BaseAgent
from pipeline.bus.message_bus import Bus, Message


class IngestionAgent(BaseAgent):
    """
    Reads raw source files in chunks and emits one Message per chunk.

    Configuration:
        files       — list of file paths to ingest
        chunk_size  — rows per chunk (default 5000)
        source_cols — columns to load (None = all)
    """

    def __init__(
        self,
        bus: Bus,
        files: Sequence[str],
        chunk_size: int = 5_000,
        source_cols: list[str] | None = None,
    ):
        super().__init__(
            name="IngestionAgent",
            bus=bus,
            in_channel="trigger",     # receives a start signal
            out_channel="raw",        # emits raw data chunks
        )
        self.files = list(files)
        self.chunk_size = chunk_size
        self.source_cols = source_cols

    def process(self, message: Message) -> Message | None:
        """
        On receiving the trigger, ingest all configured files.
        Each chunk is emitted directly to the bus rather than returned,
        since one trigger produces many output messages.
        Returns None (no single output per input).
        """
        total_chunks = 0
        total_rows = 0

        for filepath in self.files:
            if not os.path.exists(filepath):
                self.log.warning("file not found, skipping: %s", filepath)
                continue

            ext = os.path.splitext(filepath)[1].lower()
            self.log.info("ingesting: %s", filepath)

            try:
                chunks = self._read_in_chunks(filepath, ext)
                for chunk_idx, chunk_df in enumerate(chunks):
                    self.bus.put(
                        "raw",
                        Message(
                            source_agent=self.name,
                            payload=chunk_df,
                            metadata={
                                "source_file": os.path.basename(filepath),
                                "chunk_index": chunk_idx,
                                "rows": len(chunk_df),
                            },
                        ),
                    )
                    total_chunks += 1
                    total_rows += len(chunk_df)

            except Exception as exc:
                self.log.error("failed to read %s: %s", filepath, exc)
                self.bus.put(
                    "dead_letter",
                    Message(
                        source_agent=self.name,
                        payload=None,
                        metadata={"source_file": filepath},
                        error=str(exc),
                    ),
                )

        self.log.info(
            "ingestion complete: %d files → %d chunks, %d total rows",
            len(self.files), total_chunks, total_rows,
        )
        # No single return — all output was pushed directly above
        return None

    def _read_in_chunks(self, filepath: str, ext: str):
        """Yield DataFrame chunks from CSV or Parquet."""
        if ext == ".csv":
            for chunk in pd.read_csv(
                filepath,
                dtype=str,
                chunksize=self.chunk_size,
                usecols=self.source_cols,
                low_memory=False,
            ):
                yield chunk
        elif ext in (".parquet", ".pq"):
            df = pd.read_parquet(filepath, columns=self.source_cols)
            for start in range(0, len(df), self.chunk_size):
                yield df.iloc[start : start + self.chunk_size]
        else:
            raise ValueError(f"Unsupported file extension: {ext}")
