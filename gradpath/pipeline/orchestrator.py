"""
GradPath Multi-Agent Pipeline Orchestrator

Architecture:

    ┌─────────────────┐  raw      ┌──────────────────┐  validated  ┌──────────────────┐  enriched  ┌──────────────────┐
    │  IngestionAgent │ ────────► │ ValidationAgent  │ ──────────► │ EnrichmentAgent  │ ─────────► │  StorageAgent    │
    │                 │           │                  │             │                  │            │                  │
    │  Reads CSV/     │           │  - Suppression   │             │  - Add metrics   │            │  - Merge chunks  │
    │  Parquet files  │           │  - Schema rename │             │  - Annotate      │            │  - Deduplicate   │
    │  in chunks      │           │  - Numeric cast  │             │  - Labels        │            │  - Write Parquet │
    └─────────────────┘           │  - Filter rows   │             └──────────────────┘            │  - Filter JSON   │
                                  └──────────────────┘                                             │  - Quality CSV   │
                                          │                                                        └──────────────────┘
                                          ▼ (suppressed chunks)
                                    dead_letter channel

Run:
    python pipeline/run_pipeline.py

Or import and call programmatically:
    from pipeline.orchestrator import run_pipeline
    run_pipeline(files=["path/to/data.csv"])
"""
import logging
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pipeline.bus.message_bus import Bus, Message
from pipeline.agents.validation_agent import ValidationAgent
from pipeline.agents.enrichment_agent import EnrichmentAgent
from pipeline.agents.storage_agent import StorageAgent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("orchestrator")


def run_pipeline(
    files: list[str],
    chunk_size: int = 5_000,
    source_cols: list[str] | None = None,
    timeout: float = 300.0,
) -> dict:
    """
    Run the full 4-agent pipeline against the given source files.

    Strategy: synchronous per-chunk processing.
    The orchestrator ingests → validates → enriches → buffers each chunk in sequence,
    then calls storage.flush() once all chunks are processed.
    This avoids complex thread-coordination issues while preserving the
    agent-boundary contracts (each stage is a separate object with its own state).

    Args:
        files       — list of CSV or Parquet file paths to process
        chunk_size  — rows per ingestion chunk
        source_cols — columns to load (None = all)
        timeout     — unused in sync mode; kept for API compatibility

    Returns:
        dict with pipeline summary statistics
    """
    log.info("=" * 60)
    log.info("GradPath Multi-Agent Pipeline")
    log.info("Files: %s", [os.path.basename(f) for f in files])
    log.info("=" * 60)

    import pandas as pd

    start_time = time.time()

    # ── Instantiate agents (no threads — synchronous orchestration) ───────────
    validation = ValidationAgent(bus=Bus())
    enrichment = EnrichmentAgent(bus=Bus())
    storage    = StorageAgent(bus=Bus())

    total_raw_rows = 0
    source_file_names = []

    # ── Process each file chunk by chunk ──────────────────────────────────────
    for filepath in files:
        if not os.path.exists(filepath):
            log.warning("file not found, skipping: %s", filepath)
            continue

        ext = os.path.splitext(filepath)[1].lower()
        fname = os.path.basename(filepath)
        source_file_names.append(fname)
        log.info("Stage 1 — Ingesting: %s", filepath)

        chunks = _read_chunks(filepath, ext, chunk_size, source_cols)
        for chunk_idx, raw_df in enumerate(chunks):
            total_raw_rows += len(raw_df)
            raw_msg = Message(
                source_agent="IngestionAgent",
                payload=raw_df,
                metadata={"source_file": fname, "chunk_index": chunk_idx, "rows": len(raw_df)},
            )

            # ── Stage 2: Validation ───────────────────────────────────────────
            try:
                validated_msg = validation.process(raw_msg)
            except Exception as exc:
                log.error("validation error chunk %d: %s", chunk_idx, exc)
                validation.stats["errors"] += 1
                continue

            if validated_msg is None:
                validation.stats["dropped"] += 1
                continue
            validation.stats["processed"] += 1

            # ── Stage 3: Enrichment ───────────────────────────────────────────
            try:
                enriched_msg = enrichment.process(validated_msg)
            except Exception as exc:
                log.error("enrichment error chunk %d: %s", chunk_idx, exc)
                enrichment.stats["errors"] += 1
                continue

            if enriched_msg is None:
                enrichment.stats["dropped"] += 1
                continue
            enrichment.stats["processed"] += 1

            # ── Stage 4: Buffer in storage ────────────────────────────────────
            storage.process(enriched_msg)

        log.info("Ingestion complete: %s — %d total raw rows so far", fname, total_raw_rows)

    # ── Flush storage ──────────────────────────────────────────────────────────
    log.info("Stage 4 — Flushing storage…")
    storage.flush(raw_total=total_raw_rows, source_files=source_file_names)

    elapsed = time.time() - start_time

    summary = {
        "elapsed_seconds": round(elapsed, 2),
        "total_raw_rows": total_raw_rows,
        "validation": validation.stats,
        "enrichment": enrichment.stats,
        "storage":    storage.stats,
    }

    log.info("=" * 60)
    log.info("Pipeline complete in %.1fs", elapsed)
    log.info("  raw rows:     %d", total_raw_rows)
    log.info("  validated:    %d processed, %d dropped, %d errors",
             validation.stats["processed"], validation.stats["dropped"], validation.stats["errors"])
    log.info("  enriched:     %d processed, %d dropped, %d errors",
             enrichment.stats["processed"], enrichment.stats["dropped"], enrichment.stats["errors"])
    log.info("=" * 60)

    return summary


# ── Helpers ───────────────────────────────────────────────────────────────────

def _read_chunks(filepath: str, ext: str, chunk_size: int, source_cols):
    """Yield DataFrame chunks from CSV or Parquet."""
    import pandas as pd
    if ext == ".csv":
        for chunk in pd.read_csv(filepath, dtype=str, chunksize=chunk_size,
                                  usecols=source_cols, low_memory=False):
            yield chunk
    elif ext in (".parquet", ".pq"):
        df = pd.read_parquet(filepath, columns=source_cols)
        for start in range(0, len(df), chunk_size):
            yield df.iloc[start: start + chunk_size]
    else:
        raise ValueError(f"Unsupported extension: {ext}")


def _drain_dead_letter(bus: Bus) -> int:
    """Count and log any messages in the dead-letter channel."""
    count = 0
    ch = bus.channel("dead_letter")
    while not ch.empty():
        try:
            msg = ch.get_nowait()
            count += 1
            log.warning("dead-letter: agent=%s error=%s", msg.source_agent, msg.error or "unknown")
        except Exception:
            break
    return count
