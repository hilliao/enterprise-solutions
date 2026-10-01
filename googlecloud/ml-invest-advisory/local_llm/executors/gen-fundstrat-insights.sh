#!/bin/bash
#
# Purpose:
#   Monitors and fetches membership content from fundstratdirect.com using
#   headless Chrome. Supported features include:
#     1) Fetching Flash Insights page, extracting sections into ~/Documents/flash-insights.txt,
#        and generating an AI overview summary with Ollama saved to ~/Documents/flash-insights-overview.md.
#     2) Discovering & dumping the latest Technical Strategy article from the Members page,
#        extracting text between 'Key Takeaways' and '______________________________' into
#        ~/Documents/technical-strategy.txt.
#     3) Discovering & dumping the latest Crypto Comment article from the Members page into
#        ~/Documents/crypto-comment.txt.
#
# Requirements:
#   - google-chrome installed and on PATH
#   - A pre-authenticated Chrome profile at ~/workspace/chrome-flashinsights-profile
#   - `html2text` CLI installed via: sudo apt install html2text
#   - `ollama` CLI installed and accessible
#
# ---------------------------------------------------------------------------
# One-time setup: authenticate the Chrome profile used by this script
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
# Usage:
#   ./gen-fundstrat-insights.sh --flash-insights [LINES]  # Dump Flash Insights & generate summary once and exit.
#                                                          # LINES: number of lines fed to Ollama (default 120)
#   ./gen-fundstrat-insights.sh --technical-strategy    # Dump Technical Strategy article once and exit
#   ./gen-fundstrat-insights.sh --crypto-comment       # Dump Crypto Comment article once and exit
#   ./gen-fundstrat-insights.sh --poll [MINUTES] [LINES]  # Poll Flash Insights every N (default 20) minutes during
#                                                          # market open hours. LINES: lines fed to Ollama (default 120)
#

set -euo pipefail

# Environment & Path Configuration
PROFILE_DIR="$HOME/workspace/chrome-flashinsights-profile"
FLASH_INSIGHTS_URL="https://fundstratdirect.com/members/flashinsights/"
MEMBERS_URL="https://fundstratdirect.com/members/"
FLASH_INSIGHTS_FILE="$HOME/Documents/flash-insights.txt"
TECHNICAL_STRATEGY_FILE="$HOME/Documents/technical-strategy.txt"
CRYPTO_COMMENT_FILE="$HOME/Documents/crypto-comment.txt"
FLASH_INSIGHTS_OVERVIEW_MD="$HOME/Documents/flash-insights-overview.md"
FLASH_INSIGHTS_OVERVIEW="$HOME/Documents/flash-insights-overview.txt"
PORTFOLIO_DIR="$HOME/workspace/portfolios"
INTERVAL_MINUTES=20
FLASH_INSIGHTS_LINES=120
CLOSED_CHECK_SLEEP=60
export OLLAMA_HOST="${OLLAMA_HOST:-8400f:11435}"
OLLAMA_MODEL="qwen2.5:7b"
OLLAMA_MAX_ATTEMPTS=3
# Text rendered by fundstratdirect.com instead of member content when the session is not authenticated.
PAYWALL_MARKER="You need a Fundstrat Direct subscription"
# NYSE/NASDAQ full-day market holidays; polling is skipped on these dates.
# Keep in sync with HOLIDAYS in gen-investment-report-realtime-nonstop.sh.
HOLIDAYS=(
  "2026-01-01" "2026-01-19" "2026-02-16" "2026-04-03" "2026-05-25" "2026-06-19" "2026-07-03" "2026-09-07" "2026-11-26" "2026-12-25"
  "2027-01-01" "2027-01-18" "2027-02-15" "2027-03-26" "2027-05-31" "2027-06-18" "2027-07-05" "2027-09-06" "2027-11-25" "2027-12-24"
  "2028-01-17" "2028-02-21" "2028-04-14" "2028-05-29" "2028-06-19" "2028-07-04" "2028-09-04" "2028-11-23" "2028-12-25"
)

if [[ ! -d "$PROFILE_DIR" ]]; then
  echo "ERROR: Profile directory '$PROFILE_DIR' does not exist." >&2
  exit 1
fi

# Temporary file setup and cleanup
RAW_FLASH_INSIGHT_HTML="$(mktemp /tmp/flash-insights-XXXXXX.html)"
RAW_MEMBERS_HTML="$(mktemp /tmp/members-XXXXXX.html)"
RAW_TECH_STRATEGY_HTML="$(mktemp /tmp/tech-strategy-XXXXXX.html)"
RAW_CRYPTO_COMMENT_HTML="$(mktemp /tmp/crypto-comment-XXXXXX.html)"
mkdir -p "$(dirname "$FLASH_INSIGHTS_FILE")"
mkdir -p "$(dirname "$TECHNICAL_STRATEGY_FILE")"
mkdir -p "$(dirname "$CRYPTO_COMMENT_FILE")"
mkdir -p "$PORTFOLIO_DIR"
trap 'rm -f "$RAW_FLASH_INSIGHT_HTML" "$RAW_MEMBERS_HTML" "$RAW_TECH_STRATEGY_HTML" "$RAW_CRYPTO_COMMENT_HTML"' EXIT
trap 'echo "ERROR: interrupted." >&2; exit 130' INT
trap 'echo "ERROR: terminated." >&2; exit 143' TERM

# Fails if the DOM dump is the paywall/sign-in page, i.e. the Chrome profile session has expired.
check_session() {
  local html_file="$1" url="$2"
  if grep -q "$PAYWALL_MARKER" "$html_file"; then
    echo "ERROR: $url returned the subscription paywall — Chrome profile session expired." >&2
    echo "  Re-authenticate: run the command below, log in, confirm the members page loads, then close Chrome completely:" >&2
    echo "    google-chrome --user-data-dir=\"$PROFILE_DIR\" \"$MEMBERS_URL\"" >&2
    return 1
  fi
}

# Fails if the given output file has no lines.
require_nonempty() {
  local file="$1"
  if [[ ! -s "$file" ]]; then
    echo "ERROR: wrote 0 lines to $file." >&2
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

# Check if NYSE/NASDAQ market is open (Mon-Fri 09:30 - 16:00 US/Eastern, excluding HOLIDAYS).
is_market_open() {
  local day_of_week hour min total_min
  if is_market_holiday "$(TZ="America/New_York" date +%Y-%m-%d)"; then
    return 1
  fi
  day_of_week="$(TZ="America/New_York" date +%u)" # 1=Mon, ..., 7=Sun
  hour="$(TZ="America/New_York" date +%-H)"        # 0..23 (no leading zero)
  min="$(TZ="America/New_York" date +%-M)"         # 0..59 (no leading zero)
  total_min=$((hour * 60 + min))

  # Mon (1) to Fri (5) between 09:30 (570 min) and 16:00 (960 min) ET
  if [[ "$day_of_week" -ge 1 && "$day_of_week" -le 5 ]]; then
    if [[ "$total_min" -ge 570 && "$total_min" -lt 960 ]]; then
      return 0
    fi
  fi
  return 1
}

# Prints the epoch seconds of the next market open (09:30 US/Eastern on the next weekday not in HOLIDAYS).
next_market_open_epoch() {
  local candidate_date day_of_week open_epoch now_epoch
  candidate_date="$(TZ="America/New_York" date +%Y-%m-%d)"
  now_epoch="$(date +%s)"
  while true; do
    day_of_week="$(TZ="America/New_York" date -d "$candidate_date" +%u)"
    open_epoch="$(TZ="America/New_York" date -d "$candidate_date 09:30:00" +%s)"
    if [[ "$day_of_week" -le 5 && "$open_epoch" -gt "$now_epoch" ]] && ! is_market_holiday "$candidate_date"; then
      echo "$open_epoch"
      return 0
    fi
    candidate_date="$(TZ="America/New_York" date -d "$candidate_date +1 day" +%Y-%m-%d)"
  done
}

# Helper to fetch MEMBERS_URL DOM dump if not already cached in RAW_MEMBERS_HTML
ensure_members_html() {
  if [[ ! -s "$RAW_MEMBERS_HTML" ]]; then
    echo "Fetching Members page to discover latest articles..."
    if ! google-chrome \
      --headless=new \
      --disable-gpu \
      --user-data-dir="$PROFILE_DIR" \
      --virtual-time-budget=15000 \
      --dump-dom \
      "$MEMBERS_URL" 2>/dev/null > "$RAW_MEMBERS_HTML"; then
      echo "ERROR: google-chrome execution failed for $MEMBERS_URL." >&2
      return 1
    fi

    if [[ ! -s "$RAW_MEMBERS_HTML" ]]; then
      echo "ERROR: DOM dump for $MEMBERS_URL is empty — check Chrome profile session/login state." >&2
      return 1
    fi

    if ! check_session "$RAW_MEMBERS_HTML" "$MEMBERS_URL"; then
      # Clear the cache so a later call does not reuse the paywall page.
      : > "$RAW_MEMBERS_HTML"
      return 1
    fi
  fi
}

# Performs a single fetch for Flash Insights -> extract -> summarize -> mirror cycle.
run_flash_insights_once() {
  local now_str="$(TZ="America/New_York" date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "[$now_str] Fetching Flash Insights..."

  # Step 1: Launch headless Chrome against the authenticated profile for FLASH_INSIGHTS_URL.
  if ! google-chrome \
    --headless=new \
    --disable-gpu \
    --user-data-dir="$PROFILE_DIR" \
    --virtual-time-budget=15000 \
    --dump-dom \
    "$FLASH_INSIGHTS_URL" 2>/dev/null > "$RAW_FLASH_INSIGHT_HTML"; then
    echo "ERROR: google-chrome execution failed for $FLASH_INSIGHTS_URL." >&2
    return 1
  fi

  if [[ ! -s "$RAW_FLASH_INSIGHT_HTML" ]]; then
    echo "ERROR: DOM dump for Flash Insights is empty — check Chrome profile session/login state." >&2
    return 1
  fi

  check_session "$RAW_FLASH_INSIGHT_HTML" "$FLASH_INSIGHTS_URL" || return 1

  # Step 2: Convert raw HTML to text and extract sections.
  html2text "$RAW_FLASH_INSIGHT_HTML" | \
    awk '/^[⚡âš¡]* FlashInsights$/{f=1} f&&/click="shareOpen/{f=0; next} f{print} f&&/\[FlashInsights\]/{f=0}' \
    > "$FLASH_INSIGHTS_FILE"

  if ! grep -q "[⚡âš¡]* FlashInsights" "$FLASH_INSIGHTS_FILE"; then
    echo "ERROR: '⚡ FlashInsights' not found in $FLASH_INSIGHTS_FILE — session may have expired or page layout changed." >&2
    return 1
  fi
  require_nonempty "$FLASH_INSIGHTS_FILE" || return 1

  echo "OK: wrote $(wc -l < "$FLASH_INSIGHTS_FILE") lines to $FLASH_INSIGHTS_FILE"

  # Step 3: Generate summary with Ollama and output to markdown file (retry immediately on failure).
  echo "Generating summary with Ollama..."
  local ollama_success=false
  local attempt=1
  local prompt_text="Summarize the following article. highlight key macro and technical insights. prioritize posts with the most recent date and time. the audience is portfolio manager and certified financial planner. Execute risk assessments on the mentioned stocks, ETFs. Article: "

  while [[ "$ollama_success" == "false" ]]; do
    if [[ "$attempt" -gt "$OLLAMA_MAX_ATTEMPTS" ]]; then
      echo "ERROR: Ollama summary generation failed after $OLLAMA_MAX_ATTEMPTS attempts." >&2
      return 1
    fi
    if [[ "$attempt" -gt 1 ]]; then
      echo "Retrying Ollama generation (attempt $attempt of $OLLAMA_MAX_ATTEMPTS)..."
    fi

    if ollama run --nowordwrap "$OLLAMA_MODEL" \
      "$prompt_text" < <(head -n "$FLASH_INSIGHTS_LINES" "$FLASH_INSIGHTS_FILE") \
      > "$FLASH_INSIGHTS_OVERVIEW_MD" && [[ -s "$FLASH_INSIGHTS_OVERVIEW_MD" ]]; then
      ollama_success=true
      echo "OK: wrote overview markdown to $FLASH_INSIGHTS_OVERVIEW_MD"
    else
      echo "ERROR: Ollama summary generation failed." >&2
      attempt=$((attempt + 1))
      sleep 2
    fi
  done

  pandoc "$FLASH_INSIGHTS_OVERVIEW_MD" \
    -f markdown \
    -t plain \
    -o "$FLASH_INSIGHTS_OVERVIEW" \
    --wrap=none
  require_nonempty "$FLASH_INSIGHTS_OVERVIEW" || return 1
  echo "OK: wrote overview text to $FLASH_INSIGHTS_OVERVIEW"

  # Step 4: Mirror the same overview content to a dated file under the portfolio directory.
  NEWS_DATED_FILE="$PORTFOLIO_DIR/news_$(date +%Y-%m-%d).txt"
  cp "$FLASH_INSIGHTS_OVERVIEW" "$NEWS_DATED_FILE"
  echo "OK: wrote overview text to $NEWS_DATED_FILE"
  scp -P 23 "$NEWS_DATED_FILE" hil@hil-fr-dc.freeddns.org:"$PORTFOLIO_DIR/"
  echo "OK: wrote overview text to $NEWS_DATED_FILE on hil@hil-fr-dc.freeddns.org"
}

# Performs a single fetch for the latest Technical Strategy article.
fetch_technical_strategy_once() {
  local now_str="$(TZ="America/New_York" date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "[$now_str] Fetching Technical Strategy..."

  ensure_members_html || return 1

  local tech_strategy_url
  tech_strategy_url="$(grep -Eo 'https://fundstratdirect\.com/technical-strategy/daily-technical-strategy/[^"'\''<>[:space:]]+' "$RAW_MEMBERS_HTML" | head -n 1 || true)"

  if [[ -z "$tech_strategy_url" ]]; then
    echo "ERROR: Technical strategy URL starting with https://fundstratdirect.com/technical-strategy/daily-technical-strategy/ not found on $MEMBERS_URL." >&2
    return 1
  fi
  echo "INFO: Found Technical Strategy URL: $tech_strategy_url"

  if ! google-chrome \
    --headless=new \
    --disable-gpu \
    --user-data-dir="$PROFILE_DIR" \
    --virtual-time-budget=15000 \
    --dump-dom \
    "$tech_strategy_url" 2>/dev/null > "$RAW_TECH_STRATEGY_HTML"; then
    echo "ERROR: google-chrome execution failed for $tech_strategy_url." >&2
    return 1
  fi

  if [[ ! -s "$RAW_TECH_STRATEGY_HTML" ]]; then
    echo "ERROR: DOM dump for Technical Strategy page ($tech_strategy_url) is empty." >&2
    return 1
  fi

  check_session "$RAW_TECH_STRATEGY_HTML" "$tech_strategy_url" || return 1

  html2text "$RAW_TECH_STRATEGY_HTML" | \
    awk '/Key Takeaways/{flag=1} flag{print} /______________________________/ && flag{exit}' \
    > "$TECHNICAL_STRATEGY_FILE"
  require_nonempty "$TECHNICAL_STRATEGY_FILE" || return 1
  echo "OK: wrote $(wc -l < "$TECHNICAL_STRATEGY_FILE") lines to $TECHNICAL_STRATEGY_FILE"
}

# Performs a single fetch for the latest Crypto Comment article.
fetch_crypto_comment_once() {
  local now_str="$(TZ="America/New_York" date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "[$now_str] Fetching Crypto Comment..."

  ensure_members_html || return 1

  local crypto_comment_url
  crypto_comment_url="$(grep -Eo 'https://fundstratdirect\.com/crypto-research/crypto-comments/[^"'\''<>[:space:]]+' "$RAW_MEMBERS_HTML" | head -n 1 || true)"

  if [[ -z "$crypto_comment_url" ]]; then
    echo "ERROR: Crypto comment URL starting with https://fundstratdirect.com/crypto-research/crypto-comments/ not found on $MEMBERS_URL." >&2
    return 1
  fi
  echo "INFO: Found Crypto Comment URL: $crypto_comment_url"

  if ! google-chrome \
    --headless=new \
    --disable-gpu \
    --user-data-dir="$PROFILE_DIR" \
    --virtual-time-budget=15000 \
    --dump-dom \
    "$crypto_comment_url" 2>/dev/null > "$RAW_CRYPTO_COMMENT_HTML"; then
    echo "ERROR: google-chrome execution failed for $crypto_comment_url." >&2
    return 1
  fi

  if [[ ! -s "$RAW_CRYPTO_COMMENT_HTML" ]]; then
    echo "ERROR: DOM dump for Crypto Comment page ($crypto_comment_url) is empty." >&2
    return 1
  fi

  check_session "$RAW_CRYPTO_COMMENT_HTML" "$crypto_comment_url" || return 1

  html2text "$RAW_CRYPTO_COMMENT_HTML" > "$CRYPTO_COMMENT_FILE"
  require_nonempty "$CRYPTO_COMMENT_FILE" || return 1
  echo "OK: wrote $(wc -l < "$CRYPTO_COMMENT_FILE") lines to $CRYPTO_COMMENT_FILE"
}

# Sleeps for the given number of minutes with a live countdown on a single line.
sleep_with_countdown() {
  local total_minutes="$1"
  local remaining="$total_minutes"

  while [[ "$remaining" -gt 0 ]]; do
    printf "\r\033[KSleeping %d minute(s) until next fetch..." "$remaining"
    sleep 60
    remaining=$((remaining - 1))
  done
  printf "\n"
}

MODE="poll"

if [[ $# -eq 0 ]]; then
  MODE="poll"
else
  case "$1" in
    --flash-insights|--dump-flash-insights|flash-insights)
      MODE="flash-insights"
      if [[ $# -gt 1 && "$2" =~ ^[0-9]+$ ]]; then
        FLASH_INSIGHTS_LINES="$2"
      fi
      ;;
    --technical-strategy|--dump-technical-strategy|technical-strategy)
      MODE="technical-strategy"
      ;;
    --crypto-comment|--dump-crypto-comment|crypto-comment)
      MODE="crypto-comment"
      ;;
    --poll|--loop|poll)
      MODE="poll"
      if [[ $# -gt 1 && "$2" =~ ^[0-9]+$ ]]; then
        INTERVAL_MINUTES="$2"
      fi
      if [[ $# -gt 2 && "$3" =~ ^[0-9]+$ ]]; then
        FLASH_INSIGHTS_LINES="$3"
      fi
      ;;
    -h|--help|help)
      echo "Usage: $0 [OPTION]"
      echo ""
      echo "Options:"
      echo "  --flash-insights, --dump-flash-insights [LINES] Dump Flash Insights & generate AI summary once and exit"
      echo "                                                  LINES: number of lines fed to Ollama (default 120)"
      echo "  --technical-strategy, --dump-technical-strategy Dump Technical Strategy article once and exit"
      echo "  --crypto-comment, --dump-crypto-comment        Dump Crypto Comment article once and exit"
      echo "  --poll [MINUTES] [LINES]                       Poll Flash Insights every N (default 20) minutes during market open hours"
      echo "                                                  LINES: number of lines fed to Ollama (default 120)"
      echo "  -h, --help                                     Display this help message"
      exit 0
      ;;
    *)
      echo "ERROR: Unknown argument '$1'. Use -h or --help for usage." >&2
      exit 1
      ;;
  esac
fi

case "$MODE" in
  "flash-insights")
    run_flash_insights_once
    echo "INFO: Flash Insights dump complete."
    exit 0
    ;;
  "technical-strategy")
    fetch_technical_strategy_once
    echo "INFO: Technical Strategy dump complete."
    exit 0
    ;;
  "crypto-comment")
    fetch_crypto_comment_once
    echo "INFO: Crypto Comment dump complete."
    exit 0
    ;;
  "poll")
    echo "Starting web content polling monitor (Execution frequency: every ${INTERVAL_MINUTES} minutes)..."
    closed_status_printed=false
    while true; do
      if is_market_open; then
        if [[ "$closed_status_printed" == "true" ]]; then
          printf "\n"
          closed_status_printed=false
        fi
        run_flash_insights_once
        sleep_with_countdown "$INTERVAL_MINUTES"
      else
        # Refresh the countdown every second on the same line until the next market-open recheck.
        next_open_epoch="$(next_market_open_epoch)"
        elapsed=0
        while [[ "$elapsed" -lt "$CLOSED_CHECK_SLEEP" ]]; do
          remaining=$((next_open_epoch - $(date +%s)))
          if [[ "$remaining" -le 0 ]]; then
            break
          fi
          now_str="$(TZ="America/New_York" date '+%Y-%m-%d %H:%M:%S %Z')"
          printf "\r\033[K[%s] NYSE and NASDAQ markets are closed. Script to resume in %dh %dm %ds." \
            "$now_str" $((remaining / 3600)) $((remaining % 3600 / 60)) $((remaining % 60))
          closed_status_printed=true
          sleep 1
          elapsed=$((elapsed + 1))
        done
      fi
    done
    ;;
esac
