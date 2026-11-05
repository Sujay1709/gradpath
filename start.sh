#!/usr/bin/env bash
# start.sh — Start the GradPath API and Grafana dashboard server
#
# Usage (from IBM_BOB/ root):
#   chmod +x start.sh
#   ./start.sh
#
# First-time setup:
#   pip3 install -r gradpath/requirements.txt --break-system-packages
#   cd gradpath && python3 src/prepare_data.py        # build Scorecard dataset
#   cd gradpath && python3 src/tax_classifier.py      # train AI model

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
GRADPATH="$SCRIPT_DIR/gradpath"
API_LOG="$GRADPATH/api.log"
GRAFANA_LOG="$GRADPATH/grafana.log"

echo "============================================================"
echo "  GradPath — Starting services"
echo "============================================================"

# ── 1. Ensure processed data exists ──────────────────────────────
if [ ! -f "$GRADPATH/data/processed/degree_roi_clean.parquet" ]; then
  echo "  [!] Processed data not found. Running data pipeline..."
  cd "$GRADPATH" && python3 src/prepare_data.py
fi

# ── 1b. Ensure GradPath app reference datasets exist ──────────────
if [ ! -f "$GRADPATH/data/processed/school_directory.csv" ]; then
  echo "  [!] School directory not found. Building reference datasets..."
  cd "$GRADPATH" && python3 src/build_reference_data.py
fi

# ── 2. Ensure AI model exists ─────────────────────────────────────
if [ ! -f "$GRADPATH/data/processed/tax_classifier.pkl" ]; then
  echo "  [!] Tax classifier not found. Training AI model (takes ~10s)..."
  cd "$GRADPATH" && python3 src/tax_classifier.py
fi

# ── 3. Start FastAPI backend ──────────────────────────────────────
echo ""
echo "  [1/2] Starting FastAPI backend on http://localhost:8000 ..."
python3 -m uvicorn api:app \
  --app-dir "$GRADPATH/src" \
  --host 0.0.0.0 --port 8000 --log-level warning \
  > "$API_LOG" 2>&1 &
API_PID=$!
echo "        PID: $API_PID  |  Log: $API_LOG"

for i in {1..15}; do
  if curl -s http://localhost:8000/ > /dev/null 2>&1; then
    echo "        API ready ✓"
    break
  fi
  sleep 1
done

# ── 4. Start Grafana ──────────────────────────────────────────────
echo ""
echo "  [2/2] Starting Grafana on http://localhost:3000 ..."
grafana server \
  --homepath /opt/homebrew/opt/grafana/share/grafana \
  --config /opt/homebrew/etc/grafana/grafana.ini \
  cfg:default.paths.logs=/opt/homebrew/var/log/grafana \
  cfg:default.paths.data=/opt/homebrew/var/lib/grafana \
  cfg:default.paths.plugins=/opt/homebrew/var/lib/grafana/plugins \
  cfg:auth.anonymous.enabled=true \
  cfg:auth.anonymous.org_role=Viewer \
  cfg:users.default_theme=light \
  cfg:security.allow_embedding=true \
  cfg:dashboards.default_home_dashboard_path="$GRADPATH/grafana/dashboards/main/gradpath-start.json" \
  > "$GRAFANA_LOG" 2>&1 &
GRAFANA_PID=$!
echo "        PID: $GRAFANA_PID  |  Log: $GRAFANA_LOG"

for i in {1..20}; do
  if curl -s http://localhost:3000/api/health > /dev/null 2>&1; then
    echo "        Grafana ready ✓"
    break
  fi
  sleep 2
done

echo ""
echo "============================================================"
echo "  GradPath is running!"
echo ""
echo "  GradPath app:          http://localhost:8000   (students start here)"
echo "  Grafana (admin):       http://localhost:3000"
echo "  Classic dashboards:    http://localhost:3000/d/gradpath-main  ·  /d/gradpath-tax"
echo "  API docs:              http://localhost:8000/docs"
echo ""
echo "  Visitors are read-only viewers; admins can still sign in at http://localhost:3000/login"
echo "  Ctrl+C to stop both services"
echo "============================================================"

trap "echo ''; echo '  Stopping services...'; kill $API_PID $GRAFANA_PID 2>/dev/null; exit 0" INT TERM
wait
