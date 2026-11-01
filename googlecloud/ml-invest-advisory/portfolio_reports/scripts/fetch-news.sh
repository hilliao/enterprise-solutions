#!/bin/bash
#
# Purpose:
#   News aggregator that fetches page(s) from news sites using headless
#   Chrome, converts the DOM dump to text, and generates an AI summary with
#   Ollama. Supports both a built-in site registry (wsj, cnbc, fundstrat) and
#   arbitrary ad-hoc URLs (e.g. a specific Bloomberg article page).
#
#   --site fundstrat fetches the fundstratdirect.com Flash Insights page and extracts its posts.
#
#   Every --site run mirrors its summary to PORTFOLIO_DIR/news-<SITE>_YYYY-MM-DD.txt (e.g.
#   news-wsj_2026-11-01.txt), which report-news-impact.sh reads, and to the same path on
#   REMOTE_HOST. --url runs only write to OUTPUT_DIR.
#
# Requirements:
#   - google-chrome installed and on PATH
#   - `html2text` CLI installed via: sudo apt install html2text
#   - `ollama` CLI installed and accessible
#   - `pandoc` (optional, for markdown -> plain text conversion of the summary)
#   - For --site fundstrat: a Chrome profile at PROFILE_DIR logged in to fundstratdirect.com
#     (see "One-time setup" below)
#
# Usage (one of --site or --url is required):
#   ./fetch-news.sh --site wsj                        # Fetch & summarize WSJ into PORTFOLIO_DIR/news-wsj_YYYY-MM-DD.txt
#   ./fetch-news.sh --site cnbc                       # Fetch & summarize CNBC into PORTFOLIO_DIR/news-cnbc_YYYY-MM-DD.txt
#   ./fetch-news.sh --site fundstrat                  # Fetch & summarize Fundstrat Flash Insights into
#                                                      # PORTFOLIO_DIR/news-fundstrat_YYYY-MM-DD.txt
#   ./fetch-news.sh --url <URL> --name <label>        # Fetch & summarize an arbitrary URL
#   ./fetch-news.sh --url <URL> --name <label> --lines 400
#                                                      # Use first 400 lines of extracted text as the Ollama prompt input (default 600)
#   ./fetch-news.sh --site wsj --profile-dir <DIR>    # Use a different Chrome profile directory
#   ./fetch-news.sh --site wsj --output-dir <DIR>     # Write output files to DIR instead of ~/Documents/news-aggregate
#   ./fetch-news.sh --site wsj --remote-host <USER@HOST>
#                                                      # Copy news-wsj_YYYY-MM-DD.txt to another host ("" skips the copy)
#   ./fetch-news.sh --site wsj --poll [MINUTES]       # Poll only WSJ forever, sleeping MINUTES (default 30) after each cycle
#   ./fetch-news.sh --site cnbc --poll [MINUTES]      # Poll only CNBC forever
#   ./fetch-news.sh --site fundstrat --poll [MINUTES] # Poll Fundstrat only from 08:30 to 17:30 ET on trading days
#   ./fetch-news.sh --url <URL> --name <label> --poll [MINUTES]
#                                                      # Poll an arbitrary URL forever
#   ./fetch-news.sh --list                            # List available site keys
#   ./fetch-news.sh -h|--help                         # Show help
#
# Examples:
#   ./fetch-news.sh --url "https://www.bloomberg.com/markets" --name bloomberg-markets
#   ./fetch-news.sh --url "https://www.bloomberg.com/news/articles/xxxx" --name bbg-article --lines 500
#   ./fetch-news.sh --site wsj --poll                 # Poll WSJ every 30 minutes (after each cycle ends)
#   ./fetch-news.sh --site cnbc --poll 15             # Poll CNBC every 15 minutes (after each cycle ends)
#   ./fetch-news.sh --site fundstrat --poll 15        # Poll Flash Insights every 15 minutes during market hours
#
# Environment variables (all optional; defaults shown):
#   PROFILE_DIR             ~/workspace/chrome-flashinsights-profile (overridden by --profile-dir)
#   OUTPUT_DIR              ~/Documents/news-aggregate (overridden by --output-dir)
#   PORTFOLIO_DIR           ~/workspace/portfolios (where --site writes news-<SITE>_YYYY-MM-DD.txt)
#   REMOTE_HOST             hil@hil-fr-dc.freeddns.org (overridden by --remote-host; empty skips the copy)
#   REMOTE_PORT             23 (ssh port for the scp to REMOTE_HOST)
#   OLLAMA_HOST             8400f:11434
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

# ---------------------------------------------------------------------------
# Environment & Path Configuration
# ---------------------------------------------------------------------------
PROFILE_DIR="${PROFILE_DIR:-$HOME/workspace/chrome-flashinsights-profile}"
OUTPUT_DIR="${OUTPUT_DIR:-$HOME/Documents/news-aggregate}"
PORTFOLIO_DIR="${PORTFOLIO_DIR:-$HOME/workspace/portfolios}"
REMOTE_HOST="${REMOTE_HOST-hil@hil-fr-dc.freeddns.org}"
REMOTE_PORT="${REMOTE_PORT:-23}"

export OLLAMA_HOST="${OLLAMA_HOST:-8400f:11434}"
# gemma3:4b fits the 6 GB A380 and is ~6x faster, but it invented stock moves (e.g. REGN +109%) in
# CNBC summaries; gemma4:12b-it-qat takes ~4-7 minutes per page, well inside DEFAULT_POLL_MINUTES.
OLLAMA_MODEL="${OLLAMA_MODEL:-gemma4:12b-it-qat}"
OLLAMA_THINK="${OLLAMA_THINK:-false}"
OLLAMA_MAX_ATTEMPTS=3

# Measured 12-19 tokens per line on WSJ/CNBC/Flash Insights pages, so 600 lines stays under ~11.5k
# tokens and fits the 16384-token context (OLLAMA_CONTEXT_LENGTH on 8400f) with room for the summary.
DEFAULT_PROMPT_LINES=600
DEFAULT_VIRTUAL_TIME_BUDGET=15000
# --virtual-time-budget does not bound wall-clock time, and headless Chrome has hung on cnbc.com for
# over 10 minutes, which would stall --poll forever; kill it after this many seconds.
CHROME_TIMEOUT_SECONDS=120
# WSJ serves a captcha after a few fetches in quick succession, so poll conservatively by default.
DEFAULT_POLL_MINUTES=30
# Some sites answer "403 Forbidden" when the user agent says HeadlessChrome, so present
# the installed Chrome version as a regular desktop browser.
CHROME_USER_AGENT="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/$(google-chrome --version | sed -E 's/[^0-9]*([0-9]+).*/\1/').0.0.0 Safari/537.36"

# Registry of built-in sites: key -> URL
declare -A SITE_URLS=(
  [wsj]="https://www.wsj.com/"
  [cnbc]="https://www.cnbc.com/"
  [fundstrat]="https://fundstratdirect.com/members/flashinsights/"
)

# html2text renders <h2> as "***** ... *****"; the first one marks the end of the site navigation
# menus (WSJ "Top Stories", CNBC lead headline), which would otherwise fill the Ollama prompt.
CONTENT_START_PATTERN='^\*{5} '

# Text rendered by fundstratdirect.com instead of member content when the session is not authenticated.
PAYWALL_MARKER="You need a Fundstrat Direct subscription"
FUNDSTRAT_LOGIN_URL="https://fundstratdirect.com/members/"
# Flash Insights are posted up to 1 hour before the 09:30 ET open and 1.5 hours after the 16:00 ET close,
# so --poll only fetches fundstrat inside this window on trading days.
POLL_START_TIME="08:30" # America/New_York
POLL_END_TIME="17:30"   # America/New_York
# NYSE/NASDAQ full-day market holidays; fundstrat polling is skipped on these dates.
# Keep in sync with HOLIDAYS in run-market-hours.sh.
HOLIDAYS=(
  "2026-01-01" "2026-01-19" "2026-02-16" "2026-04-03" "2026-05-25" "2026-06-19" "2026-07-03" "2026-09-07" "2026-11-26" "2026-12-25"
  "2027-01-01" "2027-01-18" "2027-02-15" "2027-03-26" "2027-05-31" "2027-06-18" "2027-07-05" "2027-09-06" "2027-11-25" "2027-12-24"
  "2028-01-17" "2028-02-21" "2028-04-14" "2028-05-29" "2028-06-19" "2028-07-04" "2028-09-04" "2028-11-23" "2028-12-25"
)

# The whole prompt goes through stdin as "<head> <article>text</article> <tail>"; ollama would
# otherwise place stdin before a prompt argument.
NEWS_PROMPT_HEAD="You are a financial analyst writing for a portfolio manager and certified financial planner. The news page content is between the <article> tags below."
NEWS_PROMPT_TAIL="Task: Summarize the news page above. Highlight the top headlines, key macro/market-moving stories, and any notable stock, sector, or economic developments. Prioritize the most prominent and most recent items.
Use only facts stated in the page; never invent numbers.
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
# Helper functions
# ---------------------------------------------------------------------------

# Fails if the DOM dump is a captcha, paywall, or HTTP error page instead of the requested content.
check_page() {
  local html_file="$1" url="$2"
  # WSJ answers repeated requests with a DataDome captcha page instead of the news page.
  if grep -q 'captcha-delivery' "$html_file"; then
    echo "ERROR: $url returned a bot-detection captcha page; try again later." >&2
    return 1
  fi
  if grep -q "$PAYWALL_MARKER" "$html_file"; then
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

# Returns 0 if now is inside the fundstrat polling window (Mon-Fri POLL_START_TIME - POLL_END_TIME
# US/Eastern, excluding HOLIDAYS).
is_poll_window() {
  local day_of_week hour min total_min start_min end_min
  if is_market_holiday "$(TZ="America/New_York" date +%Y-%m-%d)"; then
    return 1
  fi
  day_of_week="$(TZ="America/New_York" date +%u)" # 1=Mon, ..., 7=Sun
  hour="$(TZ="America/New_York" date +%-H)"        # 0..23 (no leading zero)
  min="$(TZ="America/New_York" date +%-M)"         # 0..59 (no leading zero)
  total_min=$((hour * 60 + min))
  start_min=$((10#${POLL_START_TIME%:*} * 60 + 10#${POLL_START_TIME#*:}))
  end_min=$((10#${POLL_END_TIME%:*} * 60 + 10#${POLL_END_TIME#*:}))

  [[ "$day_of_week" -le 5 && "$total_min" -ge "$start_min" && "$total_min" -lt "$end_min" ]]
}

# Copies a site's summary to PORTFOLIO_DIR/news-<name>_YYYY-MM-DD.txt, which report-news-impact.sh
# reads, and to the same path on REMOTE_HOST. Args: <name> <summary_txt>
mirror_news_dated_file() {
  local name="$1" summary_txt="$2"
  local news_dated_file
  news_dated_file="$PORTFOLIO_DIR/news-${name}_$(date +%Y-%m-%d).txt"

  mkdir -p "$PORTFOLIO_DIR"
  cp "$summary_txt" "$news_dated_file"
  echo "OK: wrote news file $news_dated_file"

  if [[ -z "$REMOTE_HOST" ]]; then
    echo "INFO: REMOTE_HOST is empty; skipped copying $news_dated_file to a remote host."
    return 0
  fi
  if ! scp -P "$REMOTE_PORT" "$news_dated_file" "$REMOTE_HOST:$PORTFOLIO_DIR/"; then
    echo "ERROR: scp of $news_dated_file to $REMOTE_HOST failed." >&2
    return 1
  fi
  echo "OK: copied news file $news_dated_file to $REMOTE_HOST"
}

# Fetch a page's DOM via headless Chrome, convert to text, and summarize it
# with Ollama. Args: <name> <url> <prompt_lines>
process_site() {
  local name="$1"
  local url="$2"
  local prompt_lines="$3"
  local now_str
  now_str="$(date '+%Y-%m-%d %H:%M:%S %Z')"

  local raw_html
  raw_html="$(mktemp "/tmp/news-${name}-XXXXXX.html")"
  # A RETURN trap outlives the function, so reset it once it has run; otherwise it fires on every
  # later function return with $raw_html unset, which `set -u` turns into an error.
  trap 'rm -f "$raw_html"; trap - RETURN' RETURN

  local text_file="$OUTPUT_DIR/${name}.txt"
  local summary_md="$OUTPUT_DIR/${name}-summary.md"
  local summary_txt="$OUTPUT_DIR/${name}-summary.txt"

  local prompt_head="$NEWS_PROMPT_HEAD"
  local prompt_tail="$NEWS_PROMPT_TAIL"
  if [[ "$name" == "fundstrat" ]]; then
    prompt_head="$FUNDSTRAT_PROMPT_HEAD"
    prompt_tail="$FUNDSTRAT_PROMPT_TAIL"
  fi

  echo "[$now_str] Fetching $name ($url)..."

  if ! timeout --kill-after=10 "$CHROME_TIMEOUT_SECONDS" google-chrome \
    --headless=new \
    --disable-gpu \
    --user-data-dir="$PROFILE_DIR" \
    --user-agent="$CHROME_USER_AGENT" \
    --virtual-time-budget="$DEFAULT_VIRTUAL_TIME_BUDGET" \
    --dump-dom \
    "$url" 2>/dev/null > "$raw_html"; then
    echo "ERROR: google-chrome failed or exceeded ${CHROME_TIMEOUT_SECONDS}s for $url." >&2
    return 1
  fi

  if [[ ! -s "$raw_html" ]]; then
    echo "ERROR: DOM dump for $url is empty." >&2
    return 1
  fi

  check_page "$raw_html" "$url" || return 1

  local content_start=1
  if [[ "$name" == "fundstrat" ]]; then
    # Keep only the Flash Insights posts, between the "⚡ FlashInsights" heading and the share buttons.
    html2text "$raw_html" | \
      awk '/^[⚡âš¡]* FlashInsights$/{f=1} f&&/click="shareOpen/{f=0; next} f{print} f&&/\[FlashInsights\]/{f=0}' \
      > "$text_file"
    if ! grep -q "[⚡âš¡]* FlashInsights" "$text_file"; then
      echo "ERROR: '⚡ FlashInsights' not found in $text_file — session may have expired or page layout changed." >&2
      return 1
    fi
  else
    html2text "$raw_html" > "$text_file"
  fi

  if [[ ! -s "$text_file" ]]; then
    echo "ERROR: html2text produced empty output for $name." >&2
    return 1
  fi
  echo "OK: wrote $(wc -l < "$text_file") lines to $text_file"

  if [[ "$name" != "fundstrat" ]]; then
    content_start="$(grep -n -m 1 -E "$CONTENT_START_PATTERN" "$text_file" | cut -d: -f1 || true)"
    if [[ -z "$content_start" ]]; then
      echo "WARNING: no '*****' heading found in $text_file; sending text from line 1 to Ollama." >&2
      content_start=1
    fi
  fi

  echo "Generating summary for $name with $OLLAMA_MODEL (using $prompt_lines lines from line $content_start)..."
  local ollama_success=false
  local attempt=1

  while [[ "$ollama_success" == "false" ]]; do
    if [[ "$attempt" -gt "$OLLAMA_MAX_ATTEMPTS" ]]; then
      echo "ERROR: Ollama summary generation failed for $name after $OLLAMA_MAX_ATTEMPTS attempts." >&2
      return 1
    fi
    if [[ "$attempt" -gt 1 ]]; then
      echo "Retrying Ollama generation for $name (attempt $attempt of $OLLAMA_MAX_ATTEMPTS)..."
    fi

    if ollama run --nowordwrap --think="$OLLAMA_THINK" "$OLLAMA_MODEL" \
      < <(printf '%s\n<article>\n' "$prompt_head"
          tail -n "+$content_start" "$text_file" | head -n "$prompt_lines"
          printf '</article>\n\n%s\n' "$prompt_tail") \
      > "$summary_md" && [[ -s "$summary_md" ]]; then
      # Some models (e.g. qwen2.5) drift into Chinese; reject output containing CJK characters/punctuation and retry.
      if LC_ALL=C.UTF-8 grep -qP '[\x{3000}-\x{303F}\x{3400}-\x{9FFF}\x{F900}-\x{FAFF}\x{FF00}-\x{FFEF}]' "$summary_md"; then
        echo "ERROR: Ollama summary for $name contains CJK characters." >&2
        attempt=$((attempt + 1))
        sleep 2
        continue
      fi
      ollama_success=true
      echo "OK: wrote summary markdown to $summary_md"
    else
      echo "ERROR: Ollama summary generation failed for $name." >&2
      attempt=$((attempt + 1))
      sleep 2
    fi
  done

  if command -v pandoc >/dev/null 2>&1; then
    pandoc "$summary_md" -f markdown -t plain -o "$summary_txt" --wrap=none
    echo "OK: wrote summary text to $summary_txt"
  else
    cp "$summary_md" "$summary_txt"
    echo "WARNING: pandoc not found; copied markdown as-is to $summary_txt" >&2
  fi

  # Only registered sites feed the portfolio reports; ad-hoc --url pages stay in OUTPUT_DIR.
  if [[ -n "${SITE_URLS[$name]+x}" ]]; then
    mirror_news_dated_file "$name" "$summary_txt" || return 1
  fi
}

# Processes TARGET_NAME/TARGET_URL once; under --poll, fundstrat is skipped outside its trading-day window.
run_cycle() {
  if [[ -n "$POLL_MINUTES" && "$TARGET_NAME" == "fundstrat" ]] && ! is_poll_window; then
    echo "[$(TZ="America/New_York" date '+%Y-%m-%d %H:%M:%S %Z')] Skipping fundstrat outside the $POLL_START_TIME-$POLL_END_TIME ET trading-day window."
    return 0
  fi
  process_site "$TARGET_NAME" "$TARGET_URL" "$PROMPT_LINES"
}

# Sleeps for the given number of minutes with a live countdown on a single line.
sleep_with_countdown() {
  local remaining="$1"
  while [[ "$remaining" -gt 0 ]]; do
    printf "\r\033[KSleeping %d minute(s) until next fetch..." "$remaining"
    sleep 60
    remaining=$((remaining - 1))
  done
  printf "\n"
}

# Derives a filesystem-safe name from a URL when --name is not given.
derive_name_from_url() {
  local url="$1"
  local name
  name="$(echo "$url" | sed -E 's#^[a-zA-Z]+://##; s#/$##' | tr '/.:?&=' '-----')"
  name="${name:0:80}"
  echo "$name"
}

print_usage() {
  echo "Usage: $0 --site <key>|--url <URL> [OPTION]..."
  echo ""
  echo "Options:"
  echo "  --site <key>         Fetch & summarize a registered site. Valid keys: ${!SITE_URLS[*]}"
  echo "                       The summary is also written to \$PORTFOLIO_DIR/news-<key>_YYYY-MM-DD.txt and copied to the remote host"
  echo "  --url <URL>          Fetch & summarize an arbitrary URL (any site/page, e.g. Bloomberg)"
  echo "  --name <label>       Output file name/label to use with --url (default: derived from URL)"
  echo "  --lines <N>          Number of lines from extracted text fed to Ollama (default: $DEFAULT_PROMPT_LINES)"
  echo "  --profile-dir <DIR>  Chrome profile directory (default: \$PROFILE_DIR or ~/workspace/chrome-flashinsights-profile)"
  echo "  --output-dir <DIR>   Directory for output files (default: \$OUTPUT_DIR or ~/Documents/news-aggregate)"
  echo "  --remote-host <U@H>  Host that --site copies news-<key>_YYYY-MM-DD.txt to with scp -P \$REMOTE_PORT"
  echo "                       (default: \$REMOTE_HOST or hil@hil-fr-dc.freeddns.org; \"\" skips the copy)"
  echo "  --poll [MINUTES]     Repeat forever, sleeping MINUTES (default: $DEFAULT_POLL_MINUTES) after each fetch & summarize cycle;"
  echo "                       combine with --site <key> or --url."
  echo "                       fundstrat is only fetched $POLL_START_TIME-$POLL_END_TIME ET on trading days."
  echo "  --list               List available registered site keys and their URLs"
  echo "  -h, --help           Display this help message"
  echo ""
  echo "One of --site or --url is required."
  echo ""
  echo "Examples:"
  echo "  $0 --site wsj"
  echo "  $0 --site fundstrat"
  echo "  $0 --site wsj --poll                  # poll WSJ every $DEFAULT_POLL_MINUTES minutes"
  echo "  $0 --site cnbc --poll 15              # poll CNBC every 15 minutes"
  echo "  $0 --site fundstrat --poll 15         # poll Flash Insights every 15 minutes during market hours"
  echo "  $0 --url \"https://www.bloomberg.com/markets\" --name bloomberg-markets"
  echo "  $0 --url \"https://www.bloomberg.com/news/articles/xxxx\" --name bbg-article --lines 500"
}

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
SELECTED_SITE=""
CUSTOM_URL=""
CUSTOM_NAME=""
PROMPT_LINES="$DEFAULT_PROMPT_LINES"
POLL_MINUTES=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --site)
      [[ $# -ge 2 ]] || { echo "ERROR: --site requires an argument (${!SITE_URLS[*]})." >&2; exit 1; }
      SELECTED_SITE="$2"
      shift 2
      ;;
    --url)
      [[ $# -ge 2 ]] || { echo "ERROR: --url requires an argument." >&2; exit 1; }
      CUSTOM_URL="$2"
      shift 2
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
      for key in "${!SITE_URLS[@]}"; do
        echo "  $key -> ${SITE_URLS[$key]}"
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

if [[ -n "$CUSTOM_URL" && -n "$SELECTED_SITE" ]]; then
  echo "ERROR: --url and --site are mutually exclusive; pass only one." >&2
  exit 1
fi
if [[ -z "$CUSTOM_URL" && -z "$SELECTED_SITE" ]]; then
  echo "ERROR: pass --site <key> (${!SITE_URLS[*]}) or --url <URL>. Use -h or --help for usage." >&2
  exit 1
fi

if [[ ! -d "$PROFILE_DIR" ]]; then
  echo "ERROR: Profile directory '$PROFILE_DIR' does not exist." >&2
  exit 1
fi

# Resolve the arguments into the output name and URL to fetch each cycle.
if [[ -n "$CUSTOM_URL" ]]; then
  TARGET_NAME="$CUSTOM_NAME"
  if [[ -z "$TARGET_NAME" ]]; then
    TARGET_NAME="$(derive_name_from_url "$CUSTOM_URL")"
    echo "INFO: --name not given; derived name '$TARGET_NAME' from URL."
  fi
  if [[ -n "${SITE_URLS[$TARGET_NAME]+x}" ]]; then
    echo "ERROR: --name $TARGET_NAME is reserved for --site $TARGET_NAME." >&2
    exit 1
  fi
  TARGET_URL="$CUSTOM_URL"
else
  if [[ -z "${SITE_URLS[$SELECTED_SITE]+x}" ]]; then
    echo "ERROR: Unknown site key '$SELECTED_SITE'. Valid keys: ${!SITE_URLS[*]}" >&2
    exit 1
  fi
  TARGET_NAME="$SELECTED_SITE"
  TARGET_URL="${SITE_URLS[$SELECTED_SITE]}"
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

echo "Starting news polling for $TARGET_NAME (sleeping $POLL_MINUTES minute(s) after each cycle)..."
while true; do
  # A failed fetch (e.g. a captcha page) is retried on the next cycle instead of stopping the poll.
  run_cycle || echo "WARNING: $TARGET_NAME failed this cycle; retrying after the sleep." >&2
  sleep_with_countdown "$POLL_MINUTES"
done
