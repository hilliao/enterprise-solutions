#!/bin/bash
#
# Purpose:
#   Generates the daily portfolio analysis report with a local Ollama LLM. For
#   every *.json portfolio file in PORTFOLIO_DIR:
#     1) Builds an LLM prompt from LLM_PROMPT_TEMPLATE via build_portfolio_prompt.py,
#        which fetches current quotes from STOCK_QUOTES_CLOUD_RUN_URL.
#     2) Replaces {{MARKET_COMMENTARY}} in the prompt with MARKET_COMMENTARY_FILE
#        (an empty string if that file is missing).
#     3) Runs the prompt through `ollama run $OLLAMA_MODEL` (killed and retried
#        once after OLLAMA_TIMEOUT_SECONDS) and writes
#        $PORTFOLIO_DIR/$USE_CASE-<portfolio>.md (report + input prompt), plus
#        $PORTFOLIO_DIR/$USE_CASE-<portfolio>.html if pandoc is installed.
#
# Requirements:
#   - python3 with build_portfolio_prompt.py's dependencies installed
#   - GOOGLE_APPLICATION_CREDENTIALS set (required by build_portfolio_prompt.py)
#   - `ollama` CLI with the OLLAMA_MODEL model available
#   - `pandoc` (optional; HTML reports are skipped without it)
#   - report-common.sh next to this script
#
# Environment variables (all optional; defaults shown):
#   PORTFOLIO_DIR              <portfolio_reports>/test-portfolios
#   LLM_PROMPT_TEMPLATE        <portfolio_reports>/prompt_templates/daily_report_prompt_template.txt
#   USE_CASE                   daily-report (prefix of the output file names)
#   MARKET_COMMENTARY_FILE     $PORTFOLIO_DIR/market-commentary_YYYY-MM-DD.txt (today's date)
#   STOCK_QUOTES_CLOUD_RUN_URL https://us-central1-my-gcp-project.cloudfunctions.net/get-us-ticker-quotes
#                              (sample project ID; set it to your get-us-ticker-quotes URL)
#   OLLAMA_MODEL               gemma4:12b-it-qat (any model from `ollama list`)
#   OLLAMA_TIMEOUT_SECONDS     600 (kill `ollama run` and retry once if a report takes longer)
#   DEBUG                      set to any value to trace execution (set -x)
#
# Usage:
#   ./report-daily.sh
#   PORTFOLIO_DIR=~/workspace/portfolios ./report-daily.sh
#
# Exit status:
#   Non-zero on the first failing step. 69 means build_portfolio_prompt.py could not
#   reach the stock quotes endpoint after its retries; 124 (or 137) means `ollama run`
#   exceeded OLLAMA_TIMEOUT_SECONDS twice (first attempt and its retry).
#
# Callers:
#   run-market-hours.sh runs both report scripts in REPORT_COMMAND on every
#   loop iteration during the 08:00-18:00 ET window,
#   then uploads $PORTFOLIO_DIR/*.html to GCS:
#
#     report-daily.sh && (report-news-impact.sh || true)
#
#   The daily report is required (a failure aborts the loop); the flash-insights
#   report is optional (its failure, e.g. a missing news file, is ignored).

set -e # exit the script when execution hits any error
set -o pipefail # ensure exit code of pipe is the rightmost non-zero exit code
[[ -n "${DEBUG:-}" ]] && set -x # print the executing lines if DEBUG is set

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/report-common.sh"

# ---------------------------------------------------------------------------
# Settings (environment variables, see the header for their defaults)
# ---------------------------------------------------------------------------

# Portfolio *.json input files, and the folder the reports are written to.
export PORTFOLIO_DIR="${PORTFOLIO_DIR:-$PORTFOLIO_REPORTS_DIR/test-portfolios}"
# Prompt template with {{PORTFOLIO_HOLDING_DATA_JSON}} and {{MARKET_COMMENTARY}}, and the output file name prefix.
export LLM_PROMPT_TEMPLATE="${LLM_PROMPT_TEMPLATE:-$PORTFOLIO_REPORTS_DIR/prompt_templates/daily_report_prompt_template.txt}"
export USE_CASE="${USE_CASE:-daily-report}"
# Today's market commentary, e.g. market-commentary_2026-05-03.txt; the section is left empty without it.
export MARKET_COMMENTARY_FILE="${MARKET_COMMENTARY_FILE:-$PORTFOLIO_DIR/market-commentary_$(date +%Y-%m-%d).txt}"
# Stock quotes Cloud Run endpoint read by build_portfolio_prompt.py.
export STOCK_QUOTES_CLOUD_RUN_URL="${STOCK_QUOTES_CLOUD_RUN_URL:-https://us-central1-my-gcp-project.cloudfunctions.net/get-us-ticker-quotes}"
# Ollama model, and how long one report may take before `ollama run` is killed and retried once.
export OLLAMA_MODEL="${OLLAMA_MODEL:-gemma4:12b-it-qat}"
export OLLAMA_TIMEOUT_SECONDS="${OLLAMA_TIMEOUT_SECONDS:-600}"

# ---------------------------------------------------------------------------
# Input checks
# ---------------------------------------------------------------------------
require_valid_ollama_timeout
if [ -r "$MARKET_COMMENTARY_FILE" ]; then
  echo "Market commentary file is readable at: $MARKET_COMMENTARY_FILE"
else
  echo "Warning: Market commentary file is missing or not readable at: $MARKET_COMMENTARY_FILE. Section will be omitted."
fi
check_pandoc
find_portfolio_files

# ---------------------------------------------------------------------------
# One report per portfolio
# ---------------------------------------------------------------------------
for portfolio_file in "${PORTFOLIO_FILES[@]}"; do
  print_portfolio_header "$portfolio_file"

  portfolio_name="$(basename "$portfolio_file" .json)"
  report_name="$USE_CASE-$portfolio_name"
  prompt_file="$PORTFOLIO_DIR/$report_name.txt"
  report_md="$PORTFOLIO_DIR/$report_name.md"
  report_html="$PORTFOLIO_DIR/$report_name.html"

  # set -e stops the script if any of these steps fails.
  build_portfolio_prompt "$portfolio_file" "$prompt_file"

  # Replace {{MARKET_COMMENTARY}} with the commentary file's contents, or an empty string if it's missing.
  # Python avoids sed's escaping issues with multi-line text.
  python3 -c 'import sys
text = open(sys.argv[1]).read()
try:
    commentary = open(sys.argv[2]).read()
except Exception:
    commentary = ""
open(sys.argv[1], "w").write(text.replace("{{MARKET_COMMENTARY}}", commentary))' "$prompt_file" "$MARKET_COMMENTARY_FILE"

  run_ollama "$prompt_file" "$report_md"
  append_prompt_to_report "$prompt_file" "$report_md"
  write_html_report "$report_md" "$report_html" \
    "1 day Portfolio Analysis Report for $portfolio_name at $(date +"%Y-%m-%d %H:%M:%S %Z")"
done
