#!/bin/bash
#
# Purpose:
#   Generates the daily portfolio analysis report with a local Ollama LLM. For
#   every *.json portfolio file in PORTFOLIO_DIR:
#     1) Builds an LLM prompt from LLM_PROMPT_TEMPLATE via generate-llm-prompt.py,
#        which fetches current quotes from STOCK_QUOTES_CLOUD_RUN_URL.
#     2) Replaces {{MARKET_COMMENTARY}} in the prompt with MARKET_COMMENTARY_FILE
#        (an empty string if that file is missing).
#     3) Runs the prompt through `ollama run gemma3:12b` and writes
#        $PORTFOLIO_DIR/$USE_CASE-<portfolio>.md (report + input prompt), plus
#        $PORTFOLIO_DIR/$USE_CASE-<portfolio>.html if pandoc is installed.
#
# Requirements:
#   - python with generate-llm-prompt.py's dependencies installed
#   - GOOGLE_APPLICATION_CREDENTIALS set (required by generate-llm-prompt.py)
#   - `ollama` CLI with the gemma3:12b model available
#   - `pandoc` (optional; HTML reports are skipped without it)
#
# Environment variables (all optional; defaults shown):
#   PORTFOLIO_DIR              ~/git/enterprise-solutions/googlecloud/ml-invest-advisory/local_llm/test-portfolios
#   LLM_PROMPT_TEMPLATE        .../local_llm/prompt_templates/daily_report_prompt_template.txt
#   USE_CASE                   daily-report (prefix of the output file names)
#   MARKET_COMMENTARY_FILE     $PORTFOLIO_DIR/market-commentary_YYYY-MM-DD.txt (today's date)
#   STOCK_QUOTES_CLOUD_RUN_URL https://us-central1-hil-financial-services.cloudfunctions.net/get_us_stock_quotes
#   DEBUG                      set to any value to trace execution (set -x)
#
# Usage:
#   ./gen-daily-portfolio-reports.sh
#   PORTFOLIO_DIR=~/workspace/portfolios ./gen-daily-portfolio-reports.sh
#
# Exit status:
#   Non-zero on the first failing step. 69 means generate-llm-prompt.py could not
#   reach the stock quotes endpoint after its retries.
#
# Callers:
#   gen-investment-report-realtime-nonstop.sh (and its machine-specific copy
#   ryzen7-7700x_gen-investment-report-realtime.sh) runs both report scripts in
#   PORTFOLIO_SCRIPT on every loop iteration during the 08:00-18:00 ET window,
#   then uploads $PORTFOLIO_DIR/*.html to GCS:
#
#     gen-daily-portfolio-reports.sh && (gen-flash-insights-portfolio-reports.sh || true)
#
#   The daily report is required (a failure aborts the loop); the flash-insights
#   report is optional (its failure, e.g. a missing news file, is ignored).

set -e # exit the script when execution hits any error
set -o pipefail # ensure exit code of pipe is the rightmost non-zero exit code
[[ -n "${DEBUG:-}" ]] && set -x # print the executing lines if DEBUG is set

export PORTFOLIO_DIR="${PORTFOLIO_DIR:-$HOME/git/enterprise-solutions/googlecloud/ml-invest-advisory/local_llm/test-portfolios}"
export LLM_PROMPT_TEMPLATE="${LLM_PROMPT_TEMPLATE:-$HOME/git/enterprise-solutions/googlecloud/ml-invest-advisory/local_llm/prompt_templates/daily_report_prompt_template.txt}"
export USE_CASE="${USE_CASE:-daily-report}"

# Expecting a date-based filename format: market-commentary_YYYY-MM-DD.txt (e.g., market-commentary_2026-05-03.txt)
# If this file is missing, the market commentary section in the LLM prompt will be omitted.
export MARKET_COMMENTARY_FILE="${MARKET_COMMENTARY_FILE:-$PORTFOLIO_DIR/market-commentary_$(date +%Y-%m-%d).txt}"
if [ -r "$MARKET_COMMENTARY_FILE" ]; then
  echo "Market commentary file is readable at: $MARKET_COMMENTARY_FILE"
else
  echo "Warning: Market commentary file is missing or not readable at: $MARKET_COMMENTARY_FILE. Section will be omitted."
fi
export STOCK_QUOTES_CLOUD_RUN_URL="${STOCK_QUOTES_CLOUD_RUN_URL:-https://us-central1-hil-financial-services.cloudfunctions.net/get_us_stock_quotes}"

# Check for dependencies at the start, outside the loop
if ! command -v pandoc &> /dev/null; then
  echo "Warning: pandoc is not installed. HTML reports will not be generated."
  PANDOC_EXISTS=false
else
  PANDOC_EXISTS=true
fi

PORTFOLIO_FILES=$(find "$PORTFOLIO_DIR" -maxdepth 1 -type f -name "*.json")

# Loop through each portfolio file and print its name and first x lines
for file in $PORTFOLIO_FILES; do
  echo "Found portfolio file: $file. Showing top 6 lines:"
  head -n 6 "$file"
  echo "" # Add a blank line for readability

  PORTFOLIO_NAME=$(basename "$file" .json)
  OUTPUT_PROMPT_FILE="$PORTFOLIO_DIR/$USE_CASE-${PORTFOLIO_NAME}.txt"
  export GET_QUOTES_CMD="python $HOME/git/enterprise-solutions/googlecloud/ml-invest-advisory/local_llm/generate-llm-prompt.py \
    --portfolio_file=$file \
    --llm_prompt_template=$LLM_PROMPT_TEMPLATE \
    --output_prompt=$OUTPUT_PROMPT_FILE"

  MD_OUTPUT_FILE="${PORTFOLIO_DIR}/$USE_CASE-${PORTFOLIO_NAME}.md"

  # Execute GET_QUOTES_CMD. set -e will cause the script to exit if this fails.
  $GET_QUOTES_CMD

  # The following Python command replaces the {{MARKET_COMMENTARY}} placeholder with the content of the commentary file.
  # If the file is missing or inaccessible, an empty string is used instead.
  python3 -c 'import sys
text = open(sys.argv[1]).read()
try:
    commentary = open(sys.argv[2]).read()
except Exception:
    commentary = ""
open(sys.argv[1], "w").write(text.replace("{{MARKET_COMMENTARY}}", commentary))' "$OUTPUT_PROMPT_FILE" "$MARKET_COMMENTARY_FILE"

  # Execute ollama run and tee. set -e and set -o pipefail will cause the script to exit if this fails.
  ollama run --nowordwrap gemma3:12b < "$OUTPUT_PROMPT_FILE" \
    | tee "$MD_OUTPUT_FILE"

  # Append the prompt to the markdown file
  echo -e "\n# <span style=\"color: brown;\">Input Prompt for LLM</span>" >> "$MD_OUTPUT_FILE"
  cat "$OUTPUT_PROMPT_FILE" >> "$MD_OUTPUT_FILE"

  # Convert markdown to HTML if pandoc is available
  if [ "$PANDOC_EXISTS" = true ]; then
    HTML5_OUTPUT_FILE="${PORTFOLIO_DIR}/$USE_CASE-${PORTFOLIO_NAME}.html"
    echo -e "\n--- Generating HTML report using pandoc at $HTML5_OUTPUT_FILE ---"
    DATETIME_NOW="1 day Portfolio Analysis Report for $PORTFOLIO_NAME at $(date +"%Y-%m-%d %H:%M:%S %Z")"
    pandoc -s -f gfm -t html5 -o "$HTML5_OUTPUT_FILE" "$MD_OUTPUT_FILE" \
    --metadata title="$DATETIME_NOW" --include-in-header <(echo '<style>body { max-width: 80%; margin: 0 auto; } p, li, td, th { line-height: 1.5; }</style>')
  fi
done