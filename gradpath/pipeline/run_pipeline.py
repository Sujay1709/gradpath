"""
Entry point for the GradPath multi-agent pipeline.

Usage:
    python pipeline/run_pipeline.py
    python pipeline/run_pipeline.py --chunk-size 10000
    python pipeline/run_pipeline.py --files path/to/fos.csv path/to/inst.csv
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pipeline.orchestrator import run_pipeline

BASE_DIR = os.path.join(os.path.dirname(__file__), "..")
DATASET_DIR = os.path.join(BASE_DIR, "..", "dataset", "College_Scorecard_Raw_Data_11022026")

DEFAULT_FILES = [
    os.path.join(DATASET_DIR, "Most-Recent-Cohorts-Field-of-Study.csv"),
]


def main():
    parser = argparse.ArgumentParser(description="GradPath multi-agent data pipeline")
    parser.add_argument(
        "--files", nargs="+",
        default=DEFAULT_FILES,
        help="Source CSV/Parquet file paths (default: Most-Recent-Cohorts-Field-of-Study.csv)"
    )
    parser.add_argument(
        "--chunk-size", type=int, default=5_000,
        help="Rows per ingestion chunk (default: 5000)"
    )
    parser.add_argument(
        "--timeout", type=float, default=300.0,
        help="Pipeline timeout in seconds (default: 300)"
    )
    args = parser.parse_args()

    for f in args.files:
        if not os.path.exists(f):
            print(f"ERROR: file not found: {f}")
            sys.exit(1)

    summary = run_pipeline(
        files=args.files,
        chunk_size=args.chunk_size,
        timeout=args.timeout,
    )

    print("\nPipeline summary:")
    for k, v in summary.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
