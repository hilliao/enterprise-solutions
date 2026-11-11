#!/bin/bash
#
# Purpose:
#   News aggregator that fetches page(s) from news sites using headless
#   Chrome, converts the DOM dump to text, and generates an AI summary with
#   Ollama. Supports both a built-in site registry (wsj, cnbc, fundstrat) and
#   arbitrary ad-hoc URLs (e.g. a specific Bloomberg article page).
#
#   --site fundstrat fetches the fundstratdirect.com Flash Insights page and extracts its posts, with their dates
#   and authors, with extract_fundstrat_posts.py.
#
#   --aggregate (experimental) fetches the front pages in AGGREGATE_URLS (Bloomberg, Financial Times, Yahoo Finance,
#   MarketWatch, Investing.com and Barron's by default), keeps their headlines and teasers, and summarizes them
#   together in one Ollama run into PORTFOLIO_DIR/news-global-headlines_YYYY-MM-DD.txt. A page that fails to load (e.g. a
#   captcha page) is left out of the summary; the run fails only if no page loads.
#
#   Every summary starts with a "Fetched at ... from <URL>; summarized at ..." line in Eastern time.
#
#   Every --site run mirrors its summary to PORTFOLIO_DIR/news-<SITE>_YYYY-MM-DD.txt (e.g.
#   news-wsj_2026-11-01.txt), which report-news-impact.sh reads, and to the same path on
#   REMOTE_HOST. It then deletes that site's older news-<SITE>_*.txt files in PORTFOLIO_DIR, locally and on
#   REMOTE_HOST. --aggregate does the same with news-global-headlines_YYYY-MM-DD.txt. --url runs only write to OUTPUT_DIR.
#
# Requirements:
#   - google-chrome installed and on PATH
#   - `html2text` CLI installed via: sudo apt install html2text
#   - `ollama` CLI installed and accessible
#   - `pandoc` (optional, for markdown -> plain text conversion of the summary)
#   - For --site fundstrat: python3 (standard library only) and a Chrome profile at PROFILE_DIR logged in to
#     fundstratdirect.com
#     (see "One-time setup" below)
#
# Usage (at least one of --site, --url or --aggregate is required):
#   ./fetch-news.sh --site wsj                        # Fetch & summarize WSJ into PORTFOLIO_DIR/news-wsj_YYYY-MM-DD.txt
#   ./fetch-news.sh --site cnbc                       # Fetch & summarize CNBC into PORTFOLIO_DIR/news-cnbc_YYYY-MM-DD.txt
#   ./fetch-news.sh --site fundstrat                  # Fetch & summarize Fundstrat Flash Insights into
#                                                      # PORTFOLIO_DIR/news-fundstrat_YYYY-MM-DD.txt
#   ./fetch-news.sh --site cnbc,fundstrat             # Fetch & summarize several sites, one after another
#   ./fetch-news.sh --site wsj,cnbc,fundstrat         # (comma-separated keys from wsj, cnbc, fundstrat)
#   ./fetch-news.sh --aggregate                       # Fetch the AGGREGATE_URLS front pages & summarize them together
#                                                      # into PORTFOLIO_DIR/news-global-headlines_YYYY-MM-DD.txt
#   ./fetch-news.sh --site wsj,cnbc --aggregate       # Fetch & summarize WSJ, then CNBC, then the aggregate
#   ./fetch-news.sh --url <URL> --name <label>        # Fetch & summarize an arbitrary URL
#   ./fetch-news.sh --url <URL> --name <label> --lines 400
#                                                      # Use first 400 lines of extracted text as the Ollama prompt input (default 600;
#                                                      # --aggregate splits the lines evenly across the pages that load)
#   ./fetch-news.sh --site wsj --profile-dir <DIR>    # Use a different Chrome profile directory
#   ./fetch-news.sh --site wsj --output-dir <DIR>     # Write output files to DIR instead of ~/Documents/news-aggregate
#   ./fetch-news.sh --site wsj --remote-host <USER@HOST>
#                                                      # Copy news-wsj_YYYY-MM-DD.txt to another host ("" skips the copy)
#   ./fetch-news.sh --site wsj --poll [MINUTES]       # Poll WSJ, sleeping MINUTES (default 30) after each cycle
#   ./fetch-news.sh --site cnbc --poll [MINUTES]      # Poll CNBC
#   ./fetch-news.sh --site fundstrat --poll [MINUTES] # Poll Fundstrat
#   ./fetch-news.sh --site wsj,cnbc,fundstrat --poll [MINUTES]
#                                                      # Poll all three sites, one after another in each cycle
#   ./fetch-news.sh --url <URL> --name <label> --poll [MINUTES]
#                                                      # Poll an arbitrary URL
#                                                      # --poll only fetches from 08:00 to 18:00 ET on trading days
#                                                      # (POLL_START_ET-POLL_END_ET) and sleeps outside that window
#   ./fetch-news.sh --list                            # List available site keys
#   ./fetch-news.sh -h|--help                         # Show help
#
# Examples:
#   ./fetch-news.sh --url "https://www.bloomberg.com/markets" --name bloomberg-markets
#   ./fetch-news.sh --url "https://www.bloomberg.com/news/articles/xxxx" --name bbg-article --lines 500
#   ./fetch-news.sh --site wsj --poll                 # Poll WSJ every 30 minutes (after each cycle ends)
#   ./fetch-news.sh --site cnbc --poll 15             # Poll CNBC every 15 minutes (after each cycle ends)
#   ./fetch-news.sh --site fundstrat --poll 15        # Poll Flash Insights every 15 minutes during market hours
#   ./fetch-news.sh --site cnbc,fundstrat --poll      # Poll CNBC, then Fundstrat, every 30 minutes
#   ./fetch-news.sh --site cnbc --aggregate --poll    # Poll CNBC, then the aggregate, every 30 minutes
#   AGGREGATE_URLS="https://www.bloomberg.com/markets,https://www.ft.com/markets" ./fetch-news.sh --aggregate
#                                                      # Aggregate only Bloomberg and FT
#
# Environment variables (all optional; defaults shown):
#   PROFILE_DIR             ~/workspace/chrome-flashinsights-profile (overridden by --profile-dir)
#   OUTPUT_DIR              ~/Documents/news-aggregate (overridden by --output-dir)
#   PORTFOLIO_DIR           ~/workspace/portfolios (where --site writes news-<SITE>_YYYY-MM-DD.txt)
#   REMOTE_HOST             hil@hil-fr-dc.freeddns.org (overridden by --remote-host; empty skips the copy)
#   REMOTE_PORT             23 (ssh port for the scp to and cleanup on REMOTE_HOST)
#   AGGREGATE_URLS          https://www.bloomberg.com/markets,https://www.ft.com/markets,https://finance.yahoo.com/,
#                           https://www.marketwatch.com/,https://www.investing.com/news/,https://www.barrons.com/
#                           (comma-separated front pages that --aggregate summarizes together)
#   OLLAMA_HOST             localhost:11434 (the Ollama server on this machine)
#   OLLAMA_MODEL            gemma4:12b-it-qat (all sites and --url)
#   OLLAMA_THINK            false (passed as --think=$OLLAMA_THINK; thinking tokens can overflow the
#                           server's context (OLLAMA_CONTEXT_LENGTH) and truncate the summary)
#
# ---------------------------------------------------------------------------
# One-time setup: authenticate the Chrome profile used by --site fundstrat
# ---------------------------------------------------------------------------
#   This script never logs in itself — it reuses cookies from a Chrome
#   profile you authenticate manually, one time, before running it headless.
#
#   1. Create the profile directory and launch a normal (non-headless)
#      Chrome window pointed at that profile and the target URL:
#
#        mkdir -p ~/workspace/chrome-flashinsights-profile
#        google-chrome --user-data-dir="$HOME/workspace/chrome-flashinsights-profile" \
#          "https://fundstratdirect.com/members/"
#
#   2. In that window, log in manually with your fundstratdirect.com
#      credentials. Confirm the members page loads correctly, then close Chrome
#      completely. The profile directory now holds the session cookie(s)
#      that headless Chrome will reuse on every run of this script.
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ---------------------------------------------------------------------------
# Settings (environment variables, see the header for their defaults)
# ---------------------------------------------------------------------------

# --- Folders ---
# Chrome profile logged in to fundstratdirect.com; every site is fetched with it.
PROFILE_DIR="${PROFILE_DIR:-$HOME/workspace/chrome-flashinsights-profile}"
# Every run writes <name>.txt (page text), <name>-summary.md and <name>-summary.txt here.
OUTPUT_DIR="${OUTPUT_DIR:-$HOME/Documents/news-aggregate}"
# --site runs also write news-<SITE>_YYYY-MM-DD.txt here for report-news-impact.sh.
PORTFOLIO_DIR="${PORTFOLIO_DIR:-$HOME/workspace/portfolios}"

# --- Copy of the news files to the host that runs the reports (an empty REMOTE_HOST skips it) ---
REMOTE_HOST="${REMOTE_HOST-hil@hil-fr-dc.freeddns.org}"
REMOTE_PORT="${REMOTE_PORT:-23}"

# --- Ollama server and model that write the summaries ---
export OLLAMA_HOST="${OLLAMA_HOST:-localhost:11434}"
# gemma3:4b fits the 6 GB A380 and is ~6x faster, but it invented stock moves (e.g. REGN +109%) in
# CNBC summaries; gemma4:12b-it-qat takes ~4-7 minutes per page, well inside DEFAULT_POLL_MINUTES.
OLLAMA_MODEL="${OLLAMA_MODEL:-gemma4:12b-it-qat}"
OLLAMA_THINK="${OLLAMA_THINK:-false}"
OLLAMA_MAX_ATTEMPTS=3

# --- Defaults of --lines and --poll ---
# Measured 12-19 tokens per line on WSJ|CNBC|Flash Insights pages, so 600 lines stays under ~11.5k
# tokens and fits the 16384-token context (OLLAMA_CONTEXT_LENGTH of the Ollama server) with room for the summary.
DEFAULT_PROMPT_LINES=600
# WSJ serves a captcha after a few fetches in quick succession, so poll conservatively by default.
DEFAULT_POLL_MINUTES=30

# --- Headless Chrome ---
# Milliseconds of page time (scripts, timers) Chrome waits before dumping the DOM.
CHROME_VIRTUAL_TIME_BUDGET_MS=15000
# --virtual-time-budget does not bound wall-clock time, and headless Chrome has hung on cnbc.com for
# over 10 minutes, which would stall --poll forever; kill it after this many seconds.
CHROME_TIMEOUT_SECONDS=120
# Some sites answer "403 Forbidden" when the user agent says HeadlessChrome, so present
# the installed Chrome version as a regular desktop browser.
CHROME_USER_AGENT="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/$(google-chrome --version | sed -E 's/[^0-9]*([0-9]+).*/\1/').0.0.0 Safari/537.36"

# --- Built-in sites (--site <key>[,<key>...]) ---
# Keys in the order they're listed in messages.
SITE_KEYS=(wsj cnbc fundstrat)
declare -A SITE_URLS=(
  [wsj]="https://www.wsj.com/finance"
  [cnbc]="https://www.cnbc.com/"
  [fundstrat]="https://fundstratdirect.com/members/flashinsights/"
)
# html2text renders <h1> as "****** ... ******" and <h2> as "***** ... *****"; the first one marks the end of the
# site navigation menus (the "Markets & Finance" <h1> on wsj.com/finance, the lead headline <h2> on cnbc.com),
# which would otherwise fill the Ollama prompt. The wsj.com home page can't use this: its first line is an <h1>.
CONTENT_START_PATTERN='^\*{5,6} '

# --- Aggregate of several front pages (--aggregate, experimental) ---
# CNBC and WSJ are left out: --site cnbc and --site wsj already summarize them. Reuters
# (https://www.reuters.com/markets/) and The Economist (https://www.economist.com/finance-and-economics) are left out
# too: both answer headless Chrome with a DataDome captcha page instead of the news page.
AGGREGATE_URLS="${AGGREGATE_URLS:-https://www.bloomberg.com/markets,https://www.ft.com/markets,https://finance.yahoo.com/,https://www.marketwatch.com/,https://www.investing.com/news/,https://www.barrons.com/}"
# Name of the output files: global-headlines.txt, global-headlines-summary.{md,txt} and news-global-headlines_YYYY-MM-DD.txt.
AGGREGATE_NAME="global-headlines"
# Front-page lines with fewer words are navigation links, section titles, tickers, bylines and buttons, not news.
AGGREGATE_MIN_WORDS=5
# Lines matching this (case-insensitive) awk regex are cookie banners and page chrome, not news.
AGGREGATE_BOILERPLATE_PATTERN="cookie|consent|privacy|confidentialit|all rights reserved|skip to"

# --- Fundstrat ---
# Text rendered by fundstratdirect.com instead of member content when the session is not authenticated.
FUNDSTRAT_PAYWALL_MARKER="You need a Fundstrat Direct subscription"
FUNDSTRAT_LOGIN_URL="https://fundstratdirect.com/members/"

# --- Polling window (--poll), America/New_York ---
# --poll only fetches on trading days from POLL_START_ET to POLL_END_ET: 1.5 hours before the 09:30 ET NYSE open
# until 2 hours after the 16:00 ET close, to catch pre-market and after-hours news. Same window as
# run-market-hours.sh (WINDOW_START_HOUR_ET-WINDOW_END_HOUR_ET), which turns the news into reports.
POLL_START_ET="08:00"
POLL_END_ET="18:00"
# NYSE/NASDAQ full-day market holidays; polling is skipped on these dates.
# Keep in sync with HOLIDAYS in run-market-hours.sh.
HOLIDAYS=(
  "2026-01-01" "2026-01-19" "2026-02-16" "2026-04-03" "2026-05-25" "2026-06-19" "2026-07-03" "2026-09-07" "2026-11-26" "2026-12-25"
  "2027-01-01" "2027-01-18" "2027-02-15" "2027-03-26" "2027-05-31" "2027-06-18" "2027-07-05" "2027-09-06" "2027-11-25" "2027-12-24"
  "2028-01-17" "2028-02-21" "2028-04-14" "2028-05-29" "2028-06-19" "2028-07-04" "2028-09-04" "2028-11-23" "2028-12-25"
)

# --- Ollama prompts ---
# The whole prompt goes through stdin as "<head> <article>text</article> <tail>"; ollama would
# otherwise place stdin before a prompt argument.
NEWS_PROMPT_HEAD="You are a financial analyst writing for a portfolio manager and certified financial planner. The news page content is between the <article> tags below."
NEWS_PROMPT_TAIL="Task: Summarize the news page above. Highlight the top headlines, key macro/market-moving stories, and any notable stock, sector, or economic developments. Prioritize the most prominent and most recent items.
Use only facts stated in the page; never invent numbers.
Format: Markdown headings and bullet points. Be concise."
AGGREGATE_PROMPT_HEAD="You are a financial analyst writing for a portfolio manager and certified financial planner. The headlines and teasers from the front pages of several financial news sites are between the <article> tags below, each site inside <source> tags that name it."
AGGREGATE_PROMPT_TAIL="Task: Summarize the news across all the sites above into one briefing. Highlight the top headlines, key macro/market-moving stories, and any notable stock, sector, or economic developments. Merge a story reported by several sites into one item and name its sources in parentheses, e.g. (Bloomberg, FT). Prioritize the stories covered by the most sites and the most recent items.
Use only facts stated in the pages; never invent numbers.
Format: Markdown headings and bullet points. Be concise."
FUNDSTRAT_PROMPT_HEAD="You are a financial analyst writing for portfolio managers and certified financial planners. The FlashInsights posts are between the <article> tags below."
FUNDSTRAT_PROMPT_TAIL="Task:
1. Summarize the posts above, prioritizing the posts with the most recent date and time.
2. Highlight the key macro and technical insights.
3. Give a risk assessment for each stock and ETF mentioned.
Use only facts and price levels stated in the posts; never invent numbers.
Format: Markdown headings and bullet points. Be concise."

trap 'echo "ERROR: interrupted." >&2; exit 130' INT
trap 'echo "ERROR: terminated." >&2; exit 143' TERM

# ---------------------------------------------------------------------------
# Polling window
# ---------------------------------------------------------------------------

# Returns 0 if the given YYYY-MM-DD date is in HOLIDAYS.
is_market_holiday() {
  local candidate_date="$1" holiday
  for holiday in "${HOLIDAYS[@]}"; do
    if [[ "$candidate_date" == "$holiday" ]]; then
      return 0
    fi
  done
  return 1
}

# Returns 0 if now is inside the polling window: Mon-Fri from POLL_START_ET (08:00) until POLL_END_ET (18:00)
# America/New_York, excluding HOLIDAYS.
is_poll_window() {
  local weekday hour minute now_minutes start_minutes end_minutes
  if is_market_holiday "$(TZ="America/New_York" date +%Y-%m-%d)"; then
    return 1
  fi
  weekday="$(TZ="America/New_York" date +%u)" # 1=Mon, ..., 7=Sun
  hour="$(TZ="America/New_York" date +%-H)"    # 0..23 (no leading zero)
  minute="$(TZ="America/New_York" date +%-M)"  # 0..59 (no leading zero)
  now_minutes=$((hour * 60 + minute))
  start_minutes=$((10#${POLL_START_ET%:*} * 60 + 10#${POLL_START_ET#*:}))
  end_minutes=$((10#${POLL_END_ET%:*} * 60 + 10#${POLL_END_ET#*:}))

  [[ "$weekday" -le 5 && "$now_minutes" -ge "$start_minutes" && "$now_minutes" -lt "$end_minutes" ]]
}

# Prints the epoch seconds of the next polling window start after now: POLL_START_ET on the next Mon-Fri that isn't
# in HOLIDAYS (today, if now is before POLL_START_ET on a trading day).
next_poll_window_start() {
  local today day_offset candidate_date start_epoch now_epoch
  today="$(TZ="America/New_York" date +%Y-%m-%d)"
  now_epoch="$(date +%s)"
  for day_offset in {0..14}; do
    candidate_date="$(TZ="America/New_York" date -d "$today +$day_offset day" +%Y-%m-%d)"
    if [[ "$(TZ="America/New_York" date -d "$candidate_date" +%u)" -gt 5 ]] || is_market_holiday "$candidate_date"; then
      continue
    fi
    start_epoch="$(TZ="America/New_York" date -d "$candidate_date $POLL_START_ET" +%s)"
    if [[ "$start_epoch" -gt "$now_epoch" ]]; then
      echo "$start_epoch"
      return 0
    fi
  done
  return 1
}

# Sleeps until the next polling window starts, with a live countdown on a single line.
sleep_until_poll_window() {
  local resume_epoch remaining_seconds resume_at line columns
  resume_epoch="$(next_poll_window_start)"
  resume_at="$(TZ="America/New_York" date -d "@$resume_epoch" '+%Y-%m-%d %H:%M:%S %Z')"
  # 1-second sleeps against the wall clock, so a suspended machine still resumes on time.
  while remaining_seconds=$((resume_epoch - $(date +%s))); [[ "$remaining_seconds" -gt 0 ]]; do
    printf -v line "US stock market trading closed. Script resumes in %d h %d m %d s at %s" \
      $((remaining_seconds / 3600)) $((remaining_seconds % 3600 / 60)) $((remaining_seconds % 60)) \
      "$resume_at"
    # Cut the line to the terminal width: a wrapped line can't be overwritten with \r.
    columns="$(tput cols 2>/dev/null || echo 80)"
    printf "\r\033[K%s" "${line:0:columns - 1}"
    sleep 1
  done
  printf "\n"
}

# ---------------------------------------------------------------------------
# Fetch, extract, summarize and publish one page
# ---------------------------------------------------------------------------

# Writes URL's DOM, after its scripts ran, to HTML_FILE with headless Chrome.
fetch_page_html() {
  local url="$1" html_file="$2"
  if ! timeout --kill-after=10 "$CHROME_TIMEOUT_SECONDS" google-chrome \
    --headless=new \
    --disable-gpu \
    --user-data-dir="$PROFILE_DIR" \
    --user-agent="$CHROME_USER_AGENT" \
    --virtual-time-budget="$CHROME_VIRTUAL_TIME_BUDGET_MS" \
    --dump-dom \
    "$url" 2>/dev/null > "$html_file"; then
    echo "ERROR: google-chrome failed or exceeded ${CHROME_TIMEOUT_SECONDS}s for $url." >&2
    return 1
  fi
  if [[ ! -s "$html_file" ]]; then
    echo "ERROR: DOM dump for $url is empty." >&2
    return 1
  fi
}

# Fails if the DOM dump is a captcha, paywall, or HTTP error page instead of the requested content.
check_page() {
  local html_file="$1" url="$2"
  # WSJ answers repeated requests with a DataDome captcha page instead of the news page.
  # Bloomberg answers repeated requests with an "unusual activity ... not a robot" checkbox page instead.
  if grep -q -e 'captcha-delivery' -e 'unusual activity from your computer network' "$html_file"; then
    echo "ERROR: $url returned a bot-detection captcha page; try again later." >&2
    return 1
  fi
  if grep -q "$FUNDSTRAT_PAYWALL_MARKER" "$html_file"; then
    echo "ERROR: $url returned the subscription paywall — Chrome profile session expired." >&2
    echo "  Re-authenticate: run the command below, log in, confirm the members page loads, then close Chrome completely:" >&2
    echo "    google-chrome --user-data-dir=\"$PROFILE_DIR\" \"$FUNDSTRAT_LOGIN_URL\"" >&2
    return 1
  fi
  # The web server answers with a bare error page (e.g. "403 Forbidden" from nginx) when it refuses the request.
  local error_title
  error_title="$(grep -oiE '<title>[45][0-9]{2} [^<]*' "$html_file" | head -n 1 | sed 's/^<title>//I' || true)"
  if [[ -n "$error_title" ]]; then
    echo "ERROR: $url returned HTTP error page '$error_title' — the site refused the headless Chrome request." >&2
    return 1
  fi
}

# Converts HTML_FILE to text in TEXT_FILE; for fundstrat, keeps only the Flash Insights posts.
extract_page_text() {
  local name="$1" html_file="$2" text_file="$3" status=0
  if [[ "$name" == "fundstrat" ]]; then
    # Parse the posts out of the DOM (div.sub-insight-card elements) instead of the html2text output, whose markers
    # around the posts are artifacts: a mis-decoded ⚡ and Alpine.js attributes html2text fails to parse.
    python3 "$SCRIPT_DIR/extract_fundstrat_posts.py" "$html_file" > "$text_file" || status=$?
    case "$status" in
      0) ;;
      3)
        echo "ERROR: $FUNDSTRAT_LOGIN_URL session expired — the Chrome profile is not signed in." >&2
        echo "  Re-authenticate: run the command below, log in, confirm the members page loads, then close Chrome completely:" >&2
        echo "    google-chrome --user-data-dir=\"$PROFILE_DIR\" \"$FUNDSTRAT_LOGIN_URL\"" >&2
        return 1
        ;;
      *)
        echo "ERROR: no Flash Insights posts extracted from the fundstrat page (exit $status) — the page layout may have changed." >&2
        return 1
        ;;
    esac
  else
    html2text "$html_file" > "$text_file"
  fi

  if [[ ! -s "$text_file" ]]; then
    echo "ERROR: html2text produced empty output for $name." >&2
    return 1
  fi
  echo "OK: wrote $(wc -l < "$text_file") lines to $text_file"
}

# Prints the line number where TEXT_FILE's content starts after the site navigation (1 for fundstrat,
# whose text holds only the posts, and when no CONTENT_START_PATTERN heading is found).
find_content_start_line() {
  local name="$1" text_file="$2" start_line
  if [[ "$name" == "fundstrat" ]]; then
    echo 1
    return
  fi
  start_line="$(grep -n -m 1 -E "$CONTENT_START_PATTERN" "$text_file" | cut -d: -f1 || true)"
  if [[ -z "$start_line" ]]; then
    echo "WARNING: no '*****' or '******' heading found in $text_file; sending text from line 1 to Ollama." >&2
    start_line=1
  fi
  echo "$start_line"
}

# Summarizes LINE_COUNT lines of TEXT_FILE from START_LINE into SUMMARY_MD with OLLAMA_MODEL, retrying up to
# OLLAMA_MAX_ATTEMPTS times on a failure, an empty summary, or a summary containing CJK characters. --verbose prints
# each run's stats (total duration, token counts, tokens/s) to stderr, i.e. the terminal, not SUMMARY_MD.
summarize_with_ollama() {
  local name="$1" text_file="$2" start_line="$3" line_count="$4" summary_md="$5"
  local prompt_head="$NEWS_PROMPT_HEAD" prompt_tail="$NEWS_PROMPT_TAIL" attempt
  if [[ "$name" == "fundstrat" ]]; then
    prompt_head="$FUNDSTRAT_PROMPT_HEAD"
    prompt_tail="$FUNDSTRAT_PROMPT_TAIL"
  elif [[ "$name" == "$AGGREGATE_NAME" ]]; then
    prompt_head="$AGGREGATE_PROMPT_HEAD"
    prompt_tail="$AGGREGATE_PROMPT_TAIL"
  fi

  echo "Generating summary for $name with $OLLAMA_MODEL on $OLLAMA_HOST (using $line_count lines from line $start_line)..."
  for ((attempt = 1; attempt <= OLLAMA_MAX_ATTEMPTS; attempt++)); do
    if [[ "$attempt" -gt 1 ]]; then
      sleep 2
      echo "Retrying Ollama generation for $name (attempt $attempt of $OLLAMA_MAX_ATTEMPTS)..."
    fi

    if ! ollama run --nowordwrap --verbose --think="$OLLAMA_THINK" "$OLLAMA_MODEL" \
      < <(printf '%s\n<article>\n' "$prompt_head"
          tail -n "+$start_line" "$text_file" | head -n "$line_count"
          printf '</article>\n\n%s\n' "$prompt_tail") \
      > "$summary_md" || [[ ! -s "$summary_md" ]]; then
      echo "ERROR: Ollama summary generation failed for $name." >&2
      continue
    fi
    # Some models (e.g. qwen2.5) drift into Chinese; reject output containing CJK characters/punctuation and retry.
    if LC_ALL=C.UTF-8 grep -qP '[\x{3000}-\x{303F}\x{3400}-\x{9FFF}\x{F900}-\x{FAFF}\x{FF00}-\x{FFEF}]' "$summary_md"; then
      echo "ERROR: Ollama summary for $name contains CJK characters." >&2
      continue
    fi
    echo "OK: wrote summary markdown to $summary_md"
    return 0
  done
  echo "ERROR: Ollama summary generation failed for $name after $OLLAMA_MAX_ATTEMPTS attempts." >&2
  return 1
}

# Converts SUMMARY_MD to plain text in SUMMARY_TXT with pandoc, or copies it as-is without pandoc.
convert_summary_to_text() {
  local summary_md="$1" summary_txt="$2"
  if command -v pandoc >/dev/null 2>&1; then
    pandoc "$summary_md" -f markdown -t plain -o "$summary_txt" --wrap=none
    echo "OK: wrote summary text to $summary_txt"
  else
    cp "$summary_md" "$summary_txt"
    echo "WARNING: pandoc not found; copied markdown as-is to $summary_txt" >&2
  fi
}

# Prepends a line with the page's fetch time and the summary's completion time (America/New_York) to SUMMARY_TXT,
# so readers and the news impact reports can tell how recent the news is.
add_timestamp_line() {
  local summary_txt="$1" url="$2" fetched_at="$3" summarized_at
  summarized_at="$(TZ="America/New_York" date '+%Y-%m-%d %H:%M:%S %Z')"
  { printf 'Fetched at %s from %s; summarized at %s.\n\n' "$fetched_at" "$url" "$summarized_at"
    cat "$summary_txt"; } > "$summary_txt.tmp"
  mv "$summary_txt.tmp" "$summary_txt"
}

# Deletes the site's news-<name>_YYYY-MM-DD.txt files in PORTFOLIO_DIR other than CURRENT_FILE, printing each one.
delete_old_news_files() {
  local name="$1" current_file="$2" old_file
  for old_file in "$PORTFOLIO_DIR/news-${name}_"[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].txt; do
    # An unmatched glob stays literal, so skip names that don't exist.
    [[ -f "$old_file" && "$old_file" != "$current_file" ]] || continue
    rm -f "$old_file"
    echo "OK: deleted old news file $old_file"
  done
}

# Lists PORTFOLIO_DIR on REMOTE_HOST and deletes the site's news-<name>_YYYY-MM-DD.txt files there other than
# CURRENT_FILE, printing each one. Returns 1 if the listing or the deletion fails.
delete_old_remote_news_files() {
  local name="$1" current_file="$2" remote_listing file_name
  local -a old_files=()
  if ! remote_listing="$(ssh -p "$REMOTE_PORT" "$REMOTE_HOST" "ls -1 -- $(printf '%q' "$PORTFOLIO_DIR")")"; then
    echo "WARNING: could not list $PORTFOLIO_DIR on $REMOTE_HOST; skipped deleting old news files there." >&2
    return 1
  fi
  while IFS= read -r file_name; do
    if [[ "$file_name" =~ ^news-${name}_[0-9]{4}-[0-9]{2}-[0-9]{2}\.txt$ && "$file_name" != "${current_file##*/}" ]]; then
      old_files+=("$PORTFOLIO_DIR/$file_name")
    fi
  done <<< "$remote_listing"
  [[ ${#old_files[@]} -gt 0 ]] || return 0

  if ! ssh -p "$REMOTE_PORT" "$REMOTE_HOST" "rm -f -- $(printf '%q ' "${old_files[@]}")"; then
    echo "WARNING: could not delete old news files on $REMOTE_HOST: ${old_files[*]}" >&2
    return 1
  fi
  for file_name in "${old_files[@]}"; do
    echo "OK: deleted old news file $file_name on $REMOTE_HOST"
  done
}

# Copies a site's summary to PORTFOLIO_DIR/news-<name>_YYYY-MM-DD.txt, which report-news-impact.sh
# reads, and to the same path on REMOTE_HOST, then deletes the site's older news files in both places.
publish_news_file() {
  local name="$1" summary_txt="$2" news_file
  news_file="$PORTFOLIO_DIR/news-${name}_$(date +%Y-%m-%d).txt"

  mkdir -p "$PORTFOLIO_DIR"
  cp "$summary_txt" "$news_file"
  echo "OK: wrote news file $news_file"
  delete_old_news_files "$name" "$news_file"

  if [[ -z "$REMOTE_HOST" ]]; then
    echo "INFO: REMOTE_HOST is empty; skipped copying $news_file to a remote host."
    return 0
  fi
  if ! scp -P "$REMOTE_PORT" "$news_file" "$REMOTE_HOST:$PORTFOLIO_DIR/"; then
    echo "ERROR: scp of $news_file to $REMOTE_HOST failed." >&2
    return 1
  fi
  echo "OK: copied news file $news_file to $REMOTE_HOST"
  # The news file is already delivered, so a failed cleanup only warns.
  delete_old_remote_news_files "$name" "$news_file" || true
}

# Fetches URL, extracts its text, summarizes PROMPT_LINES lines of it with Ollama, and for --site runs publishes
# the summary as a news file.
fetch_and_summarize() {
  local name="$1" url="$2" prompt_lines="$3"
  local text_file="$OUTPUT_DIR/${name}.txt"
  local summary_md="$OUTPUT_DIR/${name}-summary.md"
  local summary_txt="$OUTPUT_DIR/${name}-summary.txt"
  local html_file start_line fetched_at

  html_file="$(mktemp "/tmp/news-${name}-XXXXXX.html")"
  # A RETURN trap outlives the function, so reset it once it has run; otherwise it fires on every
  # later function return with $html_file unset, which `set -u` turns into an error.
  trap 'rm -f "$html_file"; trap - RETURN' RETURN

  fetched_at="$(TZ="America/New_York" date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "[$fetched_at] Fetching $name ($url)..."
  fetch_page_html "$url" "$html_file" || return 1
  check_page "$html_file" "$url" || return 1
  extract_page_text "$name" "$html_file" "$text_file" || return 1
  start_line="$(find_content_start_line "$name" "$text_file")"
  summarize_with_ollama "$name" "$text_file" "$start_line" "$prompt_lines" "$summary_md" || return 1
  convert_summary_to_text "$summary_md" "$summary_txt"
  add_timestamp_line "$summary_txt" "$url" "$fetched_at"

  # Only registered sites feed the portfolio reports; ad-hoc --url pages stay in OUTPUT_DIR.
  if [[ -n "${SITE_URLS[$name]+x}" ]]; then
    publish_news_file "$name" "$summary_txt" || return 1
  fi
}

# ---------------------------------------------------------------------------
# Aggregate of several front pages (--aggregate)
# ---------------------------------------------------------------------------

# Prints a short site label for a front-page URL: its second-level domain (https://finance.yahoo.com/ -> yahoo).
derive_label_from_url() {
  local url="$1"
  echo "$url" | sed -E 's#^[a-zA-Z]+://##; s#[/:?].*##' | awk -F. '{ print (NF > 1 ? $(NF - 1) : $1) }'
}

# Converts a front page's HTML_FILE to its headlines and teasers in TEXT_FILE, one per line: html2text marks link text
# with underscores, which become spaces again; list markers and lines shorter than AGGREGATE_MIN_WORDS words
# (navigation, tickers, buttons), cookie banners and repeated lines are dropped.
extract_aggregate_text() {
  local label="$1" html_file="$2" text_file="$3"
  # -width keeps each headline on one line; -utf8 decodes the UTF-8 pages instead of treating them as ISO-8859-1.
  html2text -utf8 -nobs -width 400 "$html_file" | \
    sed -E 's/_/ /g; s/^[[:space:]]*([o*#+-]|[0-9]+\.)[[:space:]]+//; s/^[[:space:]]+//; s/[[:space:]]+$//; s/^\[(.*)\]$/\1/' | \
    awk -v min_words="$AGGREGATE_MIN_WORDS" -v boilerplate="$AGGREGATE_BOILERPLATE_PATTERN" \
      'NF >= min_words && tolower($0) !~ boilerplate && !seen[$0]++' \
    > "$text_file"
  if [[ ! -s "$text_file" ]]; then
    echo "ERROR: no headlines of $AGGREGATE_MIN_WORDS or more words found on the $label page." >&2
    return 1
  fi
  echo "OK: wrote $(wc -l < "$text_file") headline lines to $text_file"
}

# Fetches every AGGREGATE_URLS page, keeps PROMPT_LINES / <number of pages that loaded> headline lines of each in
# OUTPUT_DIR/global-headlines.txt, summarizes them together with Ollama, and publishes the summary as
# news-global-headlines_YYYY-MM-DD.txt. A page that fails (e.g. a captcha page) is left out; returns 1 if every page failed.
aggregate_news() {
  local prompt_lines="$1"
  local text_file="$OUTPUT_DIR/${AGGREGATE_NAME}.txt"
  local summary_md="$OUTPUT_DIR/${AGGREGATE_NAME}-summary.md"
  local summary_txt="$OUTPUT_DIR/${AGGREGATE_NAME}-summary.txt"
  local html_file i label url site_text_file fetched_at first_fetched_at="" fetched_urls="" lines_per_site
  local -a fetched_labels=() fetched_url_list=() failed_labels=()

  html_file="$(mktemp "/tmp/news-${AGGREGATE_NAME}-XXXXXX.html")"
  # See fetch_and_summarize for why the RETURN trap resets itself.
  trap 'rm -f "$html_file"; trap - RETURN' RETURN

  for i in "${!AGGREGATE_LABELS[@]}"; do
    label="${AGGREGATE_LABELS[$i]}"
    url="${AGGREGATE_URL_LIST[$i]}"
    site_text_file="$OUTPUT_DIR/${AGGREGATE_NAME}-${label}.txt"
    fetched_at="$(TZ="America/New_York" date '+%Y-%m-%d %H:%M:%S %Z')"
    echo "[$fetched_at] Fetching $label ($url) for the $AGGREGATE_NAME..."
    if ! fetch_page_html "$url" "$html_file" || ! check_page "$html_file" "$url" ||
      ! extract_aggregate_text "$label" "$html_file" "$site_text_file"; then
      echo "WARNING: left $label out of the $AGGREGATE_NAME." >&2
      failed_labels+=("$label")
      continue
    fi
    # The summary is as old as its oldest page.
    [[ -n "$first_fetched_at" ]] || first_fetched_at="$fetched_at"
    fetched_labels+=("$label")
    fetched_url_list+=("$url")
    fetched_urls+="${fetched_urls:+, }$url"
  done

  if [[ ${#fetched_labels[@]} -eq 0 ]]; then
    echo "ERROR: every $AGGREGATE_NAME page failed (${failed_labels[*]}); no summary written." >&2
    return 1
  fi
  # Split the prompt lines across the pages that loaded, so a failed page leaves its share to the others.
  lines_per_site=$((prompt_lines / ${#fetched_labels[@]}))
  : > "$text_file"
  for i in "${!fetched_labels[@]}"; do
    { printf '<source name="%s" url="%s">\n' "${fetched_labels[$i]}" "${fetched_url_list[$i]}"
      head -n "$lines_per_site" "$OUTPUT_DIR/${AGGREGATE_NAME}-${fetched_labels[$i]}.txt"
      printf '</source>\n'; } >> "$text_file"
  done
  echo "OK: wrote $(wc -l < "$text_file") lines from ${fetched_labels[*]} to $text_file"
  summarize_with_ollama "$AGGREGATE_NAME" "$text_file" 1 "$(wc -l < "$text_file")" "$summary_md" || return 1
  convert_summary_to_text "$summary_md" "$summary_txt"
  add_timestamp_line "$summary_txt" "$fetched_urls" "$first_fetched_at"
  publish_news_file "$AGGREGATE_NAME" "$summary_txt" || return 1
  if [[ ${#failed_labels[@]} -gt 0 ]]; then
    echo "WARNING: the $AGGREGATE_NAME summary leaves out ${failed_labels[*]}." >&2
  fi
}

# ---------------------------------------------------------------------------
# Polling and command line
# ---------------------------------------------------------------------------

# Fetches every TARGET_NAMES/TARGET_URLS entry once, one after another, then the aggregate with --aggregate; a failed
# site doesn't stop the others. Returns 1 if any site or the aggregate failed.
run_cycle() {
  local i status=0
  for i in "${!TARGET_NAMES[@]}"; do
    if ! fetch_and_summarize "${TARGET_NAMES[$i]}" "${TARGET_URLS[$i]}" "$PROMPT_LINES"; then
      echo "WARNING: ${TARGET_NAMES[$i]} failed this cycle." >&2
      status=1
    fi
  done
  if [[ "$AGGREGATE" == true ]] && ! aggregate_news "$PROMPT_LINES"; then
    echo "WARNING: $AGGREGATE_NAME failed this cycle." >&2
    status=1
  fi
  return "$status"
}

# Sleeps for the given number of minutes with a live countdown on a single line.
sleep_with_countdown() {
  local remaining_minutes="$1"
  while [[ "$remaining_minutes" -gt 0 ]]; do
    printf "\r\033[KSleeping %d minute(s) until next fetch..." "$remaining_minutes"
    sleep 60
    remaining_minutes=$((remaining_minutes - 1))
  done
  printf "\n"
}

# Prints a filesystem-safe name derived from a URL, for --url without --name.
derive_name_from_url() {
  local url="$1" name
  name="$(echo "$url" | sed -E 's#^[a-zA-Z]+://##; s#/$##' | tr '/.:?&=' '-----')"
  echo "${name:0:80}"
}

print_usage() {
  echo "Usage: $0 --site <key>[,<key>...]|--url <URL>|--aggregate [OPTION]..."
  echo ""
  echo "Options:"
  echo "  --site <keys>        Fetch & summarize registered sites, comma-separated, one after another."
  echo "                       Valid keys: ${SITE_KEYS[*]} (e.g. --site cnbc,fundstrat)"
  echo "                       The summary is also written to \$PORTFOLIO_DIR/news-<key>_YYYY-MM-DD.txt and copied to the remote host"
  echo "  --url <URL>          Fetch & summarize an arbitrary URL (any site/page, e.g. Bloomberg)"
  echo "  --aggregate          (Experimental) Fetch the front pages in \$AGGREGATE_URLS and summarize their headlines together"
  echo "                       into \$PORTFOLIO_DIR/news-${AGGREGATE_NAME}_YYYY-MM-DD.txt, copied to the remote host;"
  echo "                       runs after the --site sites, if any. Pages that fail to load are left out."
  echo "  --name <label>       Output file name/label to use with --url (default: derived from URL)"
  echo "  --lines <N>          Number of lines from extracted text fed to Ollama (default: $DEFAULT_PROMPT_LINES;"
  echo "                       --aggregate splits them evenly across the pages that load)"
  echo "  --profile-dir <DIR>  Chrome profile directory (default: \$PROFILE_DIR or ~/workspace/chrome-flashinsights-profile)"
  echo "  --output-dir <DIR>   Directory for output files (default: \$OUTPUT_DIR or ~/Documents/news-aggregate)"
  echo "  --remote-host <U@H>  Host that --site copies news-<key>_YYYY-MM-DD.txt to with scp -P \$REMOTE_PORT"
  echo "                       (default: \$REMOTE_HOST or hil@hil-fr-dc.freeddns.org; \"\" skips the copy)"
  echo "  --poll [MINUTES]     Repeat forever, sleeping MINUTES (default: $DEFAULT_POLL_MINUTES) after each fetch & summarize cycle;"
  echo "                       combine with --site <keys>, --url or --aggregate. Only fetches $POLL_START_ET-$POLL_END_ET ET on trading days."
  echo "  --list               List available registered site keys and their URLs, and the --aggregate URLs"
  echo "  -h, --help           Display this help message"
  echo ""
  echo "At least one of --site, --url or --aggregate is required; --site and --url are mutually exclusive."
  echo ""
  echo "Examples:"
  echo "  $0 --site wsj"
  echo "  $0 --site fundstrat"
  echo "  $0 --site wsj --poll                  # poll WSJ every $DEFAULT_POLL_MINUTES minutes"
  echo "  $0 --site cnbc --poll 15              # poll CNBC every 15 minutes"
  echo "  $0 --site fundstrat --poll 15         # poll Flash Insights every 15 minutes"
  echo "  $0 --site wsj,cnbc,fundstrat --poll   # poll all three sites every $DEFAULT_POLL_MINUTES minutes"
  echo "  $0 --aggregate                        # summarize the \$AGGREGATE_URLS front pages together"
  echo "  $0 --site cnbc --aggregate --poll     # poll CNBC, then the aggregate, every $DEFAULT_POLL_MINUTES minutes"
  echo "  $0 --url \"https://www.bloomberg.com/markets\" --name bloomberg-markets"
  echo "  $0 --url \"https://www.bloomberg.com/news/articles/xxxx\" --name bbg-article --lines 500"
}

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
SELECTED_SITES=""
CUSTOM_URL=""
CUSTOM_NAME=""
PROMPT_LINES="$DEFAULT_PROMPT_LINES"
POLL_MINUTES=""
AGGREGATE=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --site)
      [[ $# -ge 2 ]] || { echo "ERROR: --site requires comma-separated keys (${SITE_KEYS[*]})." >&2; exit 1; }
      SELECTED_SITES="$2"
      shift 2
      ;;
    --url)
      [[ $# -ge 2 ]] || { echo "ERROR: --url requires an argument." >&2; exit 1; }
      CUSTOM_URL="$2"
      shift 2
      ;;
    --aggregate)
      AGGREGATE=true
      shift
      ;;
    --name)
      [[ $# -ge 2 ]] || { echo "ERROR: --name requires an argument." >&2; exit 1; }
      CUSTOM_NAME="$2"
      shift 2
      ;;
    --lines)
      [[ $# -ge 2 ]] || { echo "ERROR: --lines requires a numeric argument." >&2; exit 1; }
      if ! [[ "$2" =~ ^[0-9]+$ ]]; then
        echo "ERROR: --lines must be a positive integer, got '$2'." >&2
        exit 1
      fi
      PROMPT_LINES="$2"
      shift 2
      ;;
    --profile-dir)
      [[ $# -ge 2 ]] || { echo "ERROR: --profile-dir requires a directory argument." >&2; exit 1; }
      PROFILE_DIR="$2"
      shift 2
      ;;
    --output-dir)
      [[ $# -ge 2 ]] || { echo "ERROR: --output-dir requires a directory argument." >&2; exit 1; }
      OUTPUT_DIR="$2"
      shift 2
      ;;
    --remote-host)
      [[ $# -ge 2 ]] || { echo "ERROR: --remote-host requires a USER@HOST argument (\"\" skips the copy)." >&2; exit 1; }
      REMOTE_HOST="$2"
      shift 2
      ;;
    --poll)
      POLL_MINUTES="$DEFAULT_POLL_MINUTES"
      if [[ $# -ge 2 && "$2" =~ ^[0-9]+$ ]]; then
        POLL_MINUTES="$2"
        shift
      fi
      shift
      ;;
    --list)
      echo "Available site keys:"
      for key in "${SITE_KEYS[@]}"; do
        echo "  $key -> ${SITE_URLS[$key]}"
      done
      echo "--aggregate URLs (AGGREGATE_URLS):"
      IFS=',' read -r -a aggregate_urls <<< "$AGGREGATE_URLS"
      for url in "${aggregate_urls[@]}"; do
        echo "  $url"
      done
      exit 0
      ;;
    -h|--help|help)
      print_usage
      exit 0
      ;;
    *)
      echo "ERROR: Unknown argument '$1'. Use -h or --help for usage." >&2
      exit 1
      ;;
  esac
done

if [[ -n "$CUSTOM_URL" && -n "$SELECTED_SITES" ]]; then
  echo "ERROR: --url and --site are mutually exclusive; pass only one." >&2
  exit 1
fi
if [[ -z "$CUSTOM_URL" && -z "$SELECTED_SITES" && "$AGGREGATE" != true ]]; then
  echo "ERROR: pass --site <keys> (${SITE_KEYS[*]}), --url <URL> or --aggregate. Use -h or --help for usage." >&2
  exit 1
fi

if [[ ! -d "$PROFILE_DIR" ]]; then
  echo "ERROR: Profile directory '$PROFILE_DIR' does not exist." >&2
  exit 1
fi

# Resolve the arguments into the output names and URLs to fetch each cycle, in the given order.
TARGET_NAMES=()
TARGET_URLS=()
if [[ -n "$CUSTOM_URL" ]]; then
  custom_name="$CUSTOM_NAME"
  if [[ -z "$custom_name" ]]; then
    custom_name="$(derive_name_from_url "$CUSTOM_URL")"
    echo "INFO: --name not given; derived name '$custom_name' from URL."
  fi
  if [[ -n "${SITE_URLS[$custom_name]+x}" ]]; then
    echo "ERROR: --name $custom_name is reserved for --site $custom_name." >&2
    exit 1
  fi
  if [[ "$custom_name" == "$AGGREGATE_NAME" || "$custom_name" == "$AGGREGATE_NAME"-* ]]; then
    echo "ERROR: --name $custom_name is reserved for the --aggregate output files." >&2
    exit 1
  fi
  TARGET_NAMES=("$custom_name")
  TARGET_URLS=("$CUSTOM_URL")
elif [[ -n "$SELECTED_SITES" ]]; then
  IFS=',' read -r -a selected_keys <<< "$SELECTED_SITES"
  for key in "${selected_keys[@]}"; do
    if [[ -z "$key" || -z "${SITE_URLS[$key]+x}" ]]; then
      echo "ERROR: Unknown site key '$key' in --site $SELECTED_SITES. Valid keys: ${SITE_KEYS[*]} (comma-separated)" >&2
      exit 1
    fi
    if [[ " ${TARGET_NAMES[*]} " == *" $key "* ]]; then
      echo "ERROR: Site key '$key' is repeated in --site $SELECTED_SITES." >&2
      exit 1
    fi
    TARGET_NAMES+=("$key")
    TARGET_URLS+=("${SITE_URLS[$key]}")
  done
fi

# Resolve AGGREGATE_URLS into the site labels (output file names and <source> names in the prompt) and URLs.
AGGREGATE_LABELS=()
AGGREGATE_URL_LIST=()
if [[ "$AGGREGATE" == true ]]; then
  IFS=',' read -r -a aggregate_urls <<< "$AGGREGATE_URLS"
  for url in "${aggregate_urls[@]}"; do
    if ! [[ "$url" =~ ^https?://[^/]+ ]]; then
      echo "ERROR: '$url' in AGGREGATE_URLS is not an http(s) URL (AGGREGATE_URLS is comma-separated)." >&2
      exit 1
    fi
    label="$(derive_label_from_url "$url")"
    # Two pages of one site (e.g. bloomberg.com/markets and bloomberg.com/economics) get bloomberg and bloomberg-2.
    base_label="$label"
    for ((n = 2; ; n++)); do
      [[ " ${AGGREGATE_LABELS[*]} " == *" $label "* ]] || break
      label="$base_label-$n"
    done
    AGGREGATE_LABELS+=("$label")
    AGGREGATE_URL_LIST+=("$url")
  done
  if [[ ${#AGGREGATE_URL_LIST[@]} -eq 0 ]]; then
    echo "ERROR: --aggregate needs at least one URL in AGGREGATE_URLS." >&2
    exit 1
  fi
  if [[ "$PROMPT_LINES" -lt ${#AGGREGATE_URL_LIST[@]} ]]; then
    echo "ERROR: --lines $PROMPT_LINES leaves no line for some of the ${#AGGREGATE_URL_LIST[@]} AGGREGATE_URLS pages." >&2
    exit 1
  fi
fi

mkdir -p "$OUTPUT_DIR"

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if [[ -z "$POLL_MINUTES" ]]; then
  run_cycle || exit 1
  echo "INFO: News aggregate run complete."
  exit 0
fi

echo "Starting news polling for ${TARGET_NAMES[*]}${AGGREGATE_LABELS[*]:+ $AGGREGATE_NAME (${AGGREGATE_LABELS[*]})} (sleeping $POLL_MINUTES minute(s) after each cycle," \
  "fetching only $POLL_START_ET-$POLL_END_ET ET on trading days)..."
while true; do
  # Outside the polling window, sleep until it opens instead of waking every POLL_MINUTES.
  if ! is_poll_window; then
    sleep_until_poll_window
    continue
  fi
  # A failed fetch (e.g. a captcha page) is retried on the next cycle instead of stopping the poll.
  run_cycle || echo "WARNING: retrying the failed site(s) after the sleep." >&2
  sleep_with_countdown "$POLL_MINUTES"
done
