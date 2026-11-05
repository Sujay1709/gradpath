#!/usr/bin/env bash
# Convenience wrapper — run from the repo root: ./run_pipeline.sh
set -e
cd "$(dirname "$0")/gradpath"
python3 pipeline/run_pipeline.py "$@"
