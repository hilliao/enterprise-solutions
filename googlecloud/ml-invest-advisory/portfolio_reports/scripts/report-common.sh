#!/bin/bash
#
# Purpose:
#   Helper functions shared by report-daily.sh and report-news-impact.sh. Each report script sets
#   its settings (PORTFOLIO_DIR, LLM_PROMPT_TEMPLATE, OLLAMA_MODEL, OLLAMA_TIMEOUT_SECONDS, ...) and
#   then sources this file:
#
#     source "$SCRIPT_DIR/report-common.sh"
#
#   Not meant to be run on its own.

# Folder of build_portfolio_prompt.py, the prompt templates and the test portfolios (the parent of scripts/).
PORTFOLIO_REPORTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_PORTFOLIO_PROMPT_PY="$PORTFOLIO_REPORTS_DIR/build_portfolio_prompt.py"
# Applied to every HTML report.
HTML_REPORT_STYLE='<style>body { max-width: 80%; margin: 0 auto; } p, li, td, th { line-height: 1.5; }</style>'

# Exits if OLLAMA_TIMEOUT_SECONDS isn't a positive integer.
require_valid_ollama_timeout() {
  if ! [[ "$OLLAMA_TIMEOUT_SECONDS" =~ ^[1-9][0-9]*$ ]]; then
    echo "ERROR: OLLAMA_TIMEOUT_SECONDS must be a positive integer number of seconds, got: $OLLAMA_TIMEOUT_SECONDS" >&2
    exit 1
  fi
}

# Sets HAVE_PANDOC to true or false; without pandoc only the Markdown reports are written.
check_pandoc() {
  if command -v pandoc &> /dev/null; then
    HAVE_PANDOC=true
  else
    echo "Warning: pandoc is not installed. HTML reports will not be generated."
    HAVE_PANDOC=false
  fi
}

# Sets PORTFOLIO_FILES to the *.json portfolio files in PORTFOLIO_DIR.
find_portfolio_files() {
  mapfile -t PORTFOLIO_FILES < <(find "$PORTFOLIO_DIR" -maxdepth 1 -type f -name "*.json")
}

# Prints the portfolio file name and its first lines, as a header for the portfolio's output.
print_portfolio_header() {
  local portfolio_file="$1"
  echo "Found portfolio file: $portfolio_file. Showing top 6 lines:"
  head -n 6 "$portfolio_file"
  echo ""
}

# Writes PROMPT_FILE from LLM_PROMPT_TEMPLATE with PORTFOLIO_FILE's holdings and their current quotes.
# Returns build_portfolio_prompt.py's exit code (69 if the stock quotes endpoint is still failing after its retries).
build_portfolio_prompt() {
  local portfolio_file="$1" prompt_file="$2"
  python3 "$BUILD_PORTFOLIO_PROMPT_PY" \
    --portfolio_file="$portfolio_file" \
    --llm_prompt_template="$LLM_PROMPT_TEMPLATE" \
    --output_prompt="$prompt_file"
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

# Appends PROMPT_FILE to REPORT_MD under an "Input Prompt for LLM" heading, so the report shows what the model saw.
append_prompt_to_report() {
  local prompt_file="$1" report_md="$2"
  echo -e "\n# <span style=\"color: brown;\">Input Prompt for LLM</span>" >> "$report_md"
  cat "$prompt_file" >> "$report_md"
}

# Converts REPORT_MD to the standalone HTML page REPORT_HTML titled TITLE, if pandoc is installed (see check_pandoc).
write_html_report() {
  local report_md="$1" report_html="$2" title="$3"
  if [ "$HAVE_PANDOC" != true ]; then
    return 0
  fi
  echo -e "\n--- Generating HTML report using pandoc at $report_html ---"
  pandoc -s -f gfm -t html5 -o "$report_html" "$report_md" \
    --metadata title="$title" --include-in-header <(echo "$HTML_REPORT_STYLE")
}
