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

# Folder of build_portfolio_prompt.py, the prompt templates and the test portfolios (the parent of ollama_report_pipeline/).
PORTFOLIO_REPORTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_PORTFOLIO_PROMPT_PY="$PORTFOLIO_REPORTS_DIR/build_portfolio_prompt.py"
# Applied to every HTML report. pandoc includes it after its own light-theme CSS, so these rules override it. The
# dark theme follows the viewer's browser/OS setting (prefers-color-scheme) on screen; printing stays black on white.
# It also styles the notice under the title (pandoc's subtitle, see REPORT_NOTICE), the "On this page" jump menu
# (pandoc's --toc, nav#TOC) and the collapsed Sources appendix of append_prompt_to_report (details.sources), and it
# recolors pandoc's text, links, rules, tables and any syntax-highlighted code.
HTML_REPORT_STYLE='<style>
body { max-width: 80%; margin: 0 auto; } p, li, td, th { line-height: 1.5; }
p.subtitle { font-size: 0.95em; font-style: normal; color: #57606a; }
nav#TOC { border: 1px solid #d0d7de; border-radius: 6px; padding: 4px 16px 8px; margin: 16px 0 24px; }
nav#TOC h2#toc-title { font-size: 1em; margin: 8px 0 4px; }
nav#TOC a { color: #1a5fb4; }
nav#TOC ul { margin: 2px 0; padding-left: 20px; } nav#TOC ul ul { padding-left: 0; } nav#TOC li { line-height: 1.6; }
details.sources { border-top: 1px solid #d0d7de; margin-top: 40px; padding-top: 12px; }
details.sources > summary { cursor: pointer; font-size: 1.3em; font-weight: 600; color: #9a3412; }
details.sources pre { white-space: pre-wrap; overflow-wrap: anywhere; font-size: 0.85em; }
@media print { details.sources { display: none; } }
@media screen and (prefers-color-scheme: dark) {
  html { color-scheme: dark; color: #e4e7ec; background-color: #1c2027; }
  a, a:visited, nav#TOC a { color: #7fb0ff; }
  blockquote { color: #9aa4b2; border-left-color: #3a404b; }
  hr { background-color: #3a404b; }
  table, thead, tbody, tr, th, td { border-color: #3a404b; }
  p.subtitle { color: #9aa4b2; }
  nav#TOC, details.sources { border-color: #3a404b; }
  details.sources > summary { color: #e8916f; }
  pre, code { background-color: #262b33; }
  pre > code.sourceCode > span > a:first-child::before { color: #6a737d; }
  pre.numberSource { border-left-color: #3a404b; }
  code span.dt { color: #f0a37e; }
  code span.st, code span.ch, code span.sc, code span.vs { color: #9ecbff; }
  code span.dv, code span.fl, code span.bn { color: #7ee2b8; }
  code span.fu, code span.va { color: #c3b5ff; }
  code span.kw, code span.cf, code span.ot { color: #ff9a8f; }
  code span.co, code span.an, code span.cv, code span.in, code span.wa { color: #8b949e; }
  code span.op { color: #b0b7c3; }
  code span.cn, code span.do { color: #ffa3a3; }
  code span.at { color: #b5d36a; }
  code span.pp { color: #e0b060; }
  code span.bu, code span.im { color: #7ee08e; }
  code span.ss { color: #e8a0c8; }
  code span.al, code span.er { color: #ff6b6b; }
}
</style>'

# Shown under every HTML report's title (pandoc's subtitle), so readers know who wrote it and how far to trust it.
report_notice() {
  echo "AI-generated analysis by the ${OLLAMA_MODEL} model. Not investment advice. Check figures against the Sources at the end."
}

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

# Runs PROMPT_FILE through ollama, printing the output and writing it to OUTPUT_FILE. --verbose prints the run's stats
# (total duration, prompt eval and eval token counts and tokens/s) to stderr, so they show on the terminal but not
# in OUTPUT_FILE. Kills ollama if it runs longer
# than OLLAMA_TIMEOUT_SECONDS (e.g. the model is stuck repeating itself) and retries once, overwriting OUTPUT_FILE.
# If the retry also times out, returns timeout's exit code (124, or 137 if ollama ignored SIGTERM for 10 seconds).
# Other failures are returned immediately without a retry. Exit codes are handled explicitly because set -e doesn't
# apply inside a function called as part of a && list.
run_ollama() {
  local prompt_file="$1" output_file="$2" exit_code attempt
  for attempt in 1 2; do
    exit_code=0
    timeout --foreground --kill-after=10s "${OLLAMA_TIMEOUT_SECONDS}s" ollama run --nowordwrap --hidethinking --verbose "$OLLAMA_MODEL" < "$prompt_file" \
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

# Appends PROMPT_FILE to REPORT_MD as the report's Sources appendix, so readers can check what the model saw: a
# <details> block, collapsed by default, headed "Input Prompt for LLM", with the prompt verbatim in a code block. It
# stays verbatim because the prompt quotes the template's own Markdown headings, which would otherwise show up as
# report sections and in the jump menu. The code fence is one tilde longer than any tilde run in the prompt, so the
# prompt can't end the block early. Printing a report leaves the appendix out (see HTML_REPORT_STYLE).
append_prompt_to_report() {
  local prompt_file="$1" report_md="$2" longest fence
  longest="$(grep -o '~\+' "$prompt_file" | awk '{ if (length($0) > max) max = length($0) } END { print max + 0 }')"
  fence="$(printf '~%.0s' $(seq 1 $(( longest >= 3 ? longest + 1 : 4 ))))"
  {
    echo
    echo '<details class="sources" id="sources">'
    echo '<summary>Sources: Input Prompt for LLM</summary>'
    echo
    echo 'The exact holdings data, news and instructions the model was given for this report.'
    echo
    echo "$fence text"
    cat "$prompt_file"
    echo
    echo "$fence"
    echo
    echo '</details>'
  } >> "$report_md"
}

# Converts REPORT_MD to the standalone HTML page REPORT_HTML titled TITLE, if pandoc is installed (see check_pandoc).
# Then, if REPORT_UPLOAD_COMMAND is set (run-market-hours.sh sets it to upload-report.sh), runs it with REPORT_HTML so
# the report is uploaded as soon as it exists. A failed upload only prints a warning: the report is regenerated on
# the next run, and the remaining reports shouldn't be lost over one failed upload.
write_html_report() {
  local report_md="$1" report_html="$2" title="$3"
  if [ "$HAVE_PANDOC" != true ]; then
    return 0
  fi
  echo -e "\n--- Generating HTML report using pandoc at $report_html ---"
  # --toc adds the "On this page" jump menu of the report's own headings; the Sources appendix has none (see
  # append_prompt_to_report). The notice goes in as pandoc's subtitle, right under the title.
  pandoc -s -f gfm -t html5 -o "$report_html" "$report_md" \
    --metadata title="$title" --metadata subtitle="$(report_notice)" \
    --toc --toc-depth=2 --metadata toc-title="On this page" \
    --include-in-header <(echo "$HTML_REPORT_STYLE")
  if [ -n "${REPORT_UPLOAD_COMMAND:-}" ] && ! "$REPORT_UPLOAD_COMMAND" "$report_html"; then
    echo "WARNING: uploading $report_html failed (see above); continuing." >&2
  fi
}
