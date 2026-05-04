#!/usr/bin/env bash
# bootstrap.sh — One-shot setup for Saber's Job Search System (macOS / Linux / WSL).
#
# Usage:
#   cd /path/to/deep-research-report
#   bash bootstrap.sh
#
# Optional env:
#   SKIP_INSTALL=1     # skip pip install
#   SKIP_VERIFY=1      # skip verify.py at the end
#   SET_API_KEY=1      # prompt for ANTHROPIC_API_KEY and append to ~/.bashrc

set -euo pipefail
cd "$(dirname "$0")"

echo
echo "=========================================================="
echo "  Saber's Job Search System — Bootstrap"
echo "=========================================================="
echo

# 1. Python
echo "[1/5] Checking Python..."
if ! command -v python3 >/dev/null 2>&1 && ! command -v python >/dev/null 2>&1; then
    echo "  ERROR: Python is not on PATH. Install Python 3.9+ and re-run." >&2
    exit 1
fi
PY=$(command -v python3 || command -v python)
echo "  $($PY --version)"
PY_MINOR=$($PY -c "import sys; print(sys.version_info.minor)")
if [ "$PY_MINOR" -lt 9 ]; then
    echo "  WARNING: Python 3.9+ recommended."
fi

# 2. pip install
if [ "${SKIP_INSTALL:-0}" != "1" ]; then
    echo
    echo "[2/5] Installing dependencies from requirements.txt..."
    $PY -m pip install --upgrade pip --quiet
    $PY -m pip install -r requirements.txt --quiet
    echo "  Dependencies installed."
else
    echo
    echo "[2/5] Skipping pip install (SKIP_INSTALL=1)"
fi

# 3. API key
echo
echo "[3/5] ANTHROPIC_API_KEY..."
if [ "${SET_API_KEY:-0}" = "1" ]; then
    read -r -s -p "  Paste ANTHROPIC_API_KEY (hidden): " KEY
    echo
    SHELLRC="${HOME}/.bashrc"
    [ -f "${HOME}/.zshrc" ] && SHELLRC="${HOME}/.zshrc"
    echo "export ANTHROPIC_API_KEY=\"$KEY\"" >> "$SHELLRC"
    export ANTHROPIC_API_KEY="$KEY"
    echo "  Appended to $SHELLRC and exported in current shell."
else
    if [ -n "${ANTHROPIC_API_KEY:-}" ]; then
        echo "  Already set in current shell (length ${#ANTHROPIC_API_KEY})."
    else
        echo "  NOT SET. Without this, fit_scorer.py and jd_tailor.py (non-dry-run) will fail."
        echo "  Fix: SET_API_KEY=1 bash bootstrap.sh  OR  export ANTHROPIC_API_KEY=sk-ant-..."
    fi
fi

# 4. Directories
echo
echo "[4/5] Directory scaffolding..."
mkdir -p automation/outputs/jd_cache automation/outputs/fit_cache
echo "  automation/outputs/, jd_cache/, fit_cache/ ready."

# 5. Verify
if [ "${SKIP_VERIFY:-0}" != "1" ]; then
    echo
    echo "[5/5] Running verify.py ..."
    $PY verify.py
else
    echo
    echo "[5/5] Skipping verify.py (SKIP_VERIFY=1)"
fi

echo
echo "=========================================================="
echo "  BOOTSTRAP COMPLETE"
echo "=========================================================="
echo
echo "Next steps:"
echo "  1. Open dashboard:   streamlit run ui/app.py"
echo "  2. Weekly scan:      python automation/jd_scraper.py --expansion"
echo "  3. Score:            python automation/fit_scorer.py --scan scan_YYYYMMDD.json"
echo "  4. Promote:          python automation/auto_promote.py --commit --min-score 7 --expire-stale"
echo "  5. Weekly report:    python automation/weekly_report.py"
