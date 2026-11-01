#!/bin/bash
#
# Purpose:
#   Generates a breaking-news ("flash insights") impact report per portfolio with
#   a local Ollama LLM. For every *.json portfolio file in PORTFOLIO_DIR:
#     1) Builds an LLM prompt from LLM_PROMPT_TEMPLATE via build_portfolio_prompt.py,
#        which fetches current quotes from STOCK_QUOTES_CLOUD_RUN_URL (once per portfolio).
#     2) For every news file, replaces {{FLASH_INSIGHTS}} in a copy of that prompt with a
#        "### <SITE>" section holding the news file's contents, writing
#        $PORTFOLIO_DIR/$USE_CASE-<portfolio>-<SITE>.txt.
#     3) Runs each prompt through `ollama run $OLLAMA_MODEL` (killed and retried
#        once after OLLAMA_TIMEOUT_SECONDS) and writes
#        $PORTFOLIO_DIR/$USE_CASE-<portfolio>-<SITE>.md (report + input prompt), plus
#        $PORTFOLIO_DIR/$USE_CASE-<portfolio>-<SITE>.html if pandoc is installed.
#   So 2 portfolios and 3 news files produce 6 reports, e.g. flash-insights-yang-cnbc.html.
#
#   The news files are produced by `fetch-news.sh --site <SITE>`, which writes
#   $PORTFOLIO_DIR/news-<SITE>_YYYY-MM-DD.txt (e.g. news-fundstrat_2026-11-01.txt,
#   news-cnbc_2026-11-01.txt, news-wsj_2026-11-01.txt). By default every such file
#   for today's date is used. The script exits with status 1 if none is found.
#
# Requirements:
#   - python with build_portfolio_prompt.py's dependencies installed
#   - GOOGLE_APPLICATION_CREDENTIALS set (required by build_portfolio_prompt.py)
#   - `ollama` CLI with the OLLAMA_MODEL model available
#   - `pandoc` (optional; HTML reports are skipped without it)
#
# Environment variables (all optional; defaults shown):
#   PORTFOLIO_DIR              ~/git/enterprise-solutions/googlecloud/ml-invest-advisory/portfolio_reports/test-portfolios
#   LLM_PROMPT_TEMPLATE        .../portfolio_reports/prompt_templates/flash-insights-report-template.txt
#   USE_CASE                   flash-insights (prefix of the output file names)
#   NEWS_FILES                 every $PORTFOLIO_DIR/news-*_YYYY-MM-DD.txt for today's date; set it to a
#                              comma-separated list of files to use those instead
#   STOCK_QUOTES_CLOUD_RUN_URL https://us-central1-my-gcp-project.cloudfunctions.net/get-us-ticker-quotes
#                              (sample project ID; set it to your get-us-ticker-quotes URL)
#   OLLAMA_MODEL               gemma4:12b-it-qat (any model from `ollama list`)
#   OLLAMA_TIMEOUT_SECONDS     600 (kill `ollama run` and retry once if a report takes longer)
#   DEBUG                      set to any value to trace execution (set -x)
#
# Usage:
#   ./fetch-news.sh --site fundstrat        # produce today's news files first
#   ./fetch-news.sh --site cnbc
#   ./report-news-impact.sh                 # uses every news-*_<today>.txt in PORTFOLIO_DIR
#   NEWS_FILES=$PORTFOLIO_DIR/news-fundstrat_2026-11-01.txt,$PORTFOLIO_DIR/news-wsj_2026-11-01.txt ./report-news-impact.sh
#
# Exit status:
#   1 if no news file is found; otherwise non-zero on the first
#   failing step (69 means build_portfolio_prompt.py could not reach the stock
#   quotes endpoint after its retries; 124 (or 137) means `ollama run` exceeded
#   OLLAMA_TIMEOUT_SECONDS twice (first attempt and its retry)).
#
# Callers:
#   run-market-hours.sh runs both report scripts in PORTFOLIO_SCRIPT on every
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

export PORTFOLIO_DIR="${PORTFOLIO_DIR:-$HOME/git/enterprise-solutions/googlecloud/ml-invest-advisory/portfolio_reports/test-portfolios}"
export LLM_PROMPT_TEMPLATE="${LLM_PROMPT_TEMPLATE:-$HOME/git/enterprise-solutions/googlecloud/ml-invest-advisory/portfolio_reports/prompt_templates/flash-insights-report-template.txt}"
export USE_CASE="${USE_CASE:-flash-insights}"

# News files are named news-<SITE>_YYYY-MM-DD.txt (e.g. news-wsj_2026-11-01.txt), one per site written by
# `fetch-news.sh --site <SITE>`. NEWS_FILES (comma-separated) replaces the default of all of today's files.
# Unreadable files are skipped with a warning; the script stops if no news file is left.
NEWS_DATE="$(date +%Y-%m-%d)"
if [ -n "${NEWS_FILES:-}" ]; then
  IFS=',' read -r -a NEWS_FILE_CANDIDATES <<< "$NEWS_FILES"
else
  shopt -s nullglob
  NEWS_FILE_CANDIDATES=("$PORTFOLIO_DIR"/news-*_"$NEWS_DATE".txt)
  shopt -u nullglob
fi
FOUND_NEWS_FILES=()
for news_file in "${NEWS_FILE_CANDIDATES[@]}"; do
  if [ -r "$news_file" ]; then
    echo "Found news file: $news_file"
    FOUND_NEWS_FILES+=("$news_file")
  else
    echo "Warning: news file is missing or not readable, skipping: $news_file" >&2
  fi
done
if [ "${#FOUND_NEWS_FILES[@]}" -eq 0 ]; then
  echo "Error: no news files found (expected $PORTFOLIO_DIR/news-<SITE>_$NEWS_DATE.txt or NEWS_FILES). Stopping script." >&2
  exit 1
fi

# Holds each portfolio's prompt before {{FLASH_INSIGHTS}} is replaced.
WORK_DIR="$(mktemp -d /tmp/report-news-impact-XXXXXX)"
trap 'rm -rf "$WORK_DIR"' EXIT

export STOCK_QUOTES_CLOUD_RUN_URL="${STOCK_QUOTES_CLOUD_RUN_URL:-https://us-central1-my-gcp-project.cloudfunctions.net/get-us-ticker-quotes}"
export OLLAMA_MODEL="${OLLAMA_MODEL:-gemma4:12b-it-qat}"
export OLLAMA_TIMEOUT_SECONDS="${OLLAMA_TIMEOUT_SECONDS:-600}"

if ! [[ "$OLLAMA_TIMEOUT_SECONDS" =~ ^[1-9][0-9]*$ ]]; then
  echo "ERROR: OLLAMA_TIMEOUT_SECONDS must be a positive integer number of seconds, got: $OLLAMA_TIMEOUT_SECONDS" >&2
  exit 1
fi

# Prints the site name of a news file: news-<SITE>_YYYY-MM-DD.txt -> <SITE> (other names: the base name).
news_site_name() {
  local site
  site="$(basename "$1" .txt)"
  site="${site#news-}"
  echo "${site%_*}"
}

# Runs PROMPT_FILE through ollama, printing the output and writing it to OUTPUT_FILE. Kills ollama if it runs longer
# than OLLAMA_TIMEOUT_SECONDS (e.g. the model is stuck repeating itself) and retries once, overwriting OUTPUT_FILE.
# If the retry also times out, returns timeout's exit code (124, or 137 if ollama ignored SIGTERM for 10 seconds).
# Other failures are returned immediately without a retry. Exit codes are handled explicitly because set -e doesn't
# apply inside a function called as part of a && list.
run_ollama() {
  local prompt_file="$1" output_file="$2" exit_code attempt
  for attempt in 1 2; do
    exit_code=0
    timeout --foreground --kill-after=10s "${OLLAMA_TIMEOUT_SECONDS}s" ollama run --nowordwrap --hidethinking "$OLLAMA_MODEL" < "$prompt_file" \
      | tee "$output_file" || exit_code=$?
    if [ "$exit_code" -ne 124 ] && [ "$exit_code" -ne 137 ]; then
      return "$exit_code"
    fi
    if [ "$attempt" -eq 1 ]; then
      echo -e "\nWARNING: ollama run did not finish within ${OLLAMA_TIMEOUT_SECONDS}s for $prompt_file; retrying once at $(date)" >&2
    fi
  done
  echo "ERROR: ollama run did not finish within ${OLLAMA_TIMEOUT_SECONDS}s for $prompt_file after a retry; aborting at $(date)" >&2
  return "$exit_code"
}


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
  # Fetch the quotes once per portfolio; a failure (e.g. exit 69) stops the script via set -e.
  BASE_PROMPT_FILE="$WORK_DIR/$USE_CASE-${PORTFOLIO_NAME}.txt"
  export GET_QUOTES_CMD="python $HOME/git/enterprise-solutions/googlecloud/ml-invest-advisory/portfolio_reports/build_portfolio_prompt.py \
    --portfolio_file=$file \
    --llm_prompt_template=$LLM_PROMPT_TEMPLATE \
    --output_prompt=$BASE_PROMPT_FILE"
  $GET_QUOTES_CMD

  # One report per news file, so each site's news is analyzed on its own.
  for news_file in "${FOUND_NEWS_FILES[@]}"; do
    SITE="$(news_site_name "$news_file")"
    REPORT_NAME="$USE_CASE-${PORTFOLIO_NAME}-${SITE}"
    OUTPUT_PROMPT_FILE="$PORTFOLIO_DIR/$REPORT_NAME.txt"
    MD_OUTPUT_FILE="$PORTFOLIO_DIR/$REPORT_NAME.md"
    echo "--- Generating $REPORT_NAME from $news_file ---"

    # Replace the {{FLASH_INSIGHTS}} placeholder keyword with this site's news, using python for multi-line string
    # replacement to avoid sed escaping issues.
    python3 -c 'import sys; text=open(sys.argv[1]).read(); news="### " + sys.argv[3] + "\n\n" + open(sys.argv[2]).read(); open(sys.argv[4], "w").write(text.replace("{{FLASH_INSIGHTS}}", news))' \
      "$BASE_PROMPT_FILE" "$news_file" "$SITE" "$OUTPUT_PROMPT_FILE"
    run_ollama "$OUTPUT_PROMPT_FILE" "$MD_OUTPUT_FILE"

    # Append the prompt to the markdown file
    echo -e "\n# <span style=\"color: brown;\">Input Prompt for LLM</span>" >> "$MD_OUTPUT_FILE"
    cat "$OUTPUT_PROMPT_FILE" >> "$MD_OUTPUT_FILE"

    # Convert markdown to HTML if pandoc is available
    if [ "$PANDOC_EXISTS" = true ]; then
      HTML5_OUTPUT_FILE="${PORTFOLIO_DIR}/$REPORT_NAME.html"
      echo -e "\n--- Generating HTML report using pandoc at $HTML5_OUTPUT_FILE ---"
      DATETIME_NOW="Breaking News Impact Report for $PORTFOLIO_NAME from $SITE at $(date +"%Y-%m-%d %H:%M:%S %Z")"
      pandoc -s -f gfm -t html5 -o "$HTML5_OUTPUT_FILE" "$MD_OUTPUT_FILE" \
      --metadata title="$DATETIME_NOW" --include-in-header <(echo '<style>body { max-width: 80%; margin: 0 auto; } p, li, td, th { line-height: 1.5; }</style>')
    fi
  done
done
