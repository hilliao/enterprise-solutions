#!/bin/bash
#
# Purpose:
#   Generates a breaking-news ("flash insights") impact report per portfolio and news site with
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
#   - python3 with build_portfolio_prompt.py's dependencies installed
#   - GOOGLE_APPLICATION_CREDENTIALS set (required by build_portfolio_prompt.py)
#   - `ollama` CLI with the OLLAMA_MODEL model available
#   - `pandoc` (optional; HTML reports are skipped without it)
#   - report-common.sh next to this script
#
# Environment variables (all optional; defaults shown):
#   PORTFOLIO_DIR              <portfolio_reports>/test-portfolios
#   LLM_PROMPT_TEMPLATE        <portfolio_reports>/prompt_templates/flash-insights-report-template.txt
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

# Portfolio *.json input files and news-<SITE>_YYYY-MM-DD.txt files, and the folder the reports are written to.
export PORTFOLIO_DIR="${PORTFOLIO_DIR:-$PORTFOLIO_REPORTS_DIR/test-portfolios}"
# Prompt template with {{PORTFOLIO_HOLDING_DATA_JSON}} and {{FLASH_INSIGHTS}}, and the output file name prefix.
export LLM_PROMPT_TEMPLATE="${LLM_PROMPT_TEMPLATE:-$PORTFOLIO_REPORTS_DIR/prompt_templates/flash-insights-report-template.txt}"
export USE_CASE="${USE_CASE:-flash-insights}"
# Comma-separated news files; empty means every news-*_<today>.txt in PORTFOLIO_DIR.
export NEWS_FILES="${NEWS_FILES:-}"
# Stock quotes Cloud Run endpoint read by build_portfolio_prompt.py.
export STOCK_QUOTES_CLOUD_RUN_URL="${STOCK_QUOTES_CLOUD_RUN_URL:-https://us-central1-my-gcp-project.cloudfunctions.net/get-us-ticker-quotes}"
# Ollama model, and how long one report may take before `ollama run` is killed and retried once.
export OLLAMA_MODEL="${OLLAMA_MODEL:-gemma4:12b-it-qat}"
export OLLAMA_TIMEOUT_SECONDS="${OLLAMA_TIMEOUT_SECONDS:-600}"

# Prints the site name of a news file: news-<SITE>_YYYY-MM-DD.txt -> <SITE> (other names: the base name).
news_site_name() {
  local site
  site="$(basename "$1" .txt)"
  site="${site#news-}"
  echo "${site%_*}"
}

# ---------------------------------------------------------------------------
# Input checks
# ---------------------------------------------------------------------------
require_valid_ollama_timeout

# Find the news files: NEWS_FILES, or else today's news-<SITE>_YYYY-MM-DD.txt files. Unreadable files are skipped
# with a warning; the script stops if no news file is left.
today="$(date +%Y-%m-%d)"
if [ -n "$NEWS_FILES" ]; then
  IFS=',' read -r -a candidate_news_files <<< "$NEWS_FILES"
else
  shopt -s nullglob
  candidate_news_files=("$PORTFOLIO_DIR"/news-*_"$today".txt)
  shopt -u nullglob
fi
news_files=()
for news_file in "${candidate_news_files[@]}"; do
  if [ -r "$news_file" ]; then
    echo "Found news file: $news_file"
    news_files+=("$news_file")
  else
    echo "Warning: news file is missing or not readable, skipping: $news_file" >&2
  fi
done
if [ "${#news_files[@]}" -eq 0 ]; then
  echo "Error: no news files found (expected $PORTFOLIO_DIR/news-<SITE>_$today.txt or NEWS_FILES). Stopping script." >&2
  exit 1
fi

check_pandoc
find_portfolio_files

# Holds each portfolio's prompt before {{FLASH_INSIGHTS}} is replaced.
work_dir="$(mktemp -d /tmp/report-news-impact-XXXXXX)"
trap 'rm -rf "$work_dir"' EXIT

# ---------------------------------------------------------------------------
# One report per portfolio and news file
# ---------------------------------------------------------------------------
for portfolio_file in "${PORTFOLIO_FILES[@]}"; do
  print_portfolio_header "$portfolio_file"

  # Fetch the quotes once per portfolio; a failure (e.g. exit 69) stops the script via set -e.
  portfolio_name="$(basename "$portfolio_file" .json)"
  portfolio_prompt_file="$work_dir/$USE_CASE-$portfolio_name.txt"
  build_portfolio_prompt "$portfolio_file" "$portfolio_prompt_file"

  # One report per news file, so each site's news is analyzed on its own.
  for news_file in "${news_files[@]}"; do
    site="$(news_site_name "$news_file")"
    report_name="$USE_CASE-$portfolio_name-$site"
    prompt_file="$PORTFOLIO_DIR/$report_name.txt"
    report_md="$PORTFOLIO_DIR/$report_name.md"
    report_html="$PORTFOLIO_DIR/$report_name.html"
    echo "--- Generating $report_name from $news_file ---"

    # Replace {{FLASH_INSIGHTS}} with this site's news under a "### <SITE>" heading.
    # Python avoids sed's escaping issues with multi-line text.
    python3 -c 'import sys; text=open(sys.argv[1]).read(); news="### " + sys.argv[3] + "\n\n" + open(sys.argv[2]).read(); open(sys.argv[4], "w").write(text.replace("{{FLASH_INSIGHTS}}", news))' \
      "$portfolio_prompt_file" "$news_file" "$site" "$prompt_file"

    run_ollama "$prompt_file" "$report_md"
    append_prompt_to_report "$prompt_file" "$report_md"
    write_html_report "$report_md" "$report_html" \
      "Breaking News Impact Report for $portfolio_name from $site at $(date +"%Y-%m-%d %H:%M:%S %Z")"
  done
done
