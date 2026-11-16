#!/usr/bin/env bash
# Project Audible capstone: cold-start demo. No manual steps.
#
#   ./run_demo.sh          tests -> live FFIEC source check -> rebuild dashboard from saved results -> open it
#   ./run_demo.sh --full   reruns the whole 5-step pipeline from the FFIEC download first (~700 MB, slow)
#
# Needs only Python 3.10+. pandas/openpyxl are needed for --full (lender classification) and are
# installed automatically if missing.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT/project_audible_data"

PY="${PYTHON:-}"
if [ -z "$PY" ]; then
  for c in python3 python; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then
      PY="$c"; break
    fi
  done
fi
if [ -z "$PY" ]; then echo "run_demo: Python 3.10+ not found." >&2; exit 1; fi
echo "== Using $("$PY" --version)"

HAS_PANDAS=0
"$PY" -c 'import pandas, openpyxl' >/dev/null 2>&1 && HAS_PANDAS=1

if [ "${1:-}" = "--full" ]; then
  if [ "$HAS_PANDAS" = 0 ]; then
    echo "== Installing pandas + openpyxl for lender classification"
    "$PY" -m pip install --quiet pandas openpyxl || "$PY" -m pip install --quiet --user pandas openpyxl
    HAS_PANDAS=1
  fi
  echo "== Full pipeline (5 steps)"
  "$PY" download_hmda.py
  "$PY" classify_lenders_nyu.py
  "$PY" clean_mortgages.py
  "$PY" analyze_pricing.py
  BUILD_ARGS=()
else
  BUILD_ARGS=(--from-json)
fi

echo "== Unit tests"
TESTS=(test_download_hmda test_clean_mortgages test_analyze_pricing test_build_dashboard test_build_position_memo test_check_source)
[ "$HAS_PANDAS" = 1 ] && TESTS+=(test_classify_lenders_nyu)
"$PY" -m unittest "${TESTS[@]}"
[ "$HAS_PANDAS" = 0 ] && echo "   (test_classify_lenders_nyu skipped: pandas not installed; only needed for --full)"

echo "== Live source check (FFIEC)"
"$PY" check_source.py

echo "== Build dashboard"
"$PY" build_dashboard.py "${BUILD_ARGS[@]+"${BUILD_ARGS[@]}"}"

OUT="$ROOT/Submit/Project Audible Dashboard.html"
echo "== Done: $OUT"
if [ -z "${NO_OPEN:-}" ]; then
  case "$(uname -s)" in
    Darwin) open "$OUT" ;;
    Linux) command -v xdg-open >/dev/null 2>&1 && xdg-open "$OUT" >/dev/null 2>&1 || true ;;
    MINGW*|MSYS*|CYGWIN*) start "" "$OUT" ;;
  esac
fi
