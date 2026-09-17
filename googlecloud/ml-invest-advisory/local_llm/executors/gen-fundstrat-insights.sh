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
trap 'rm -f "$RAW_FLASH_INSIGHT_HTML" "$RAW_MEMBERS_HTML" "$RAW_TECH_STRATEGY_HTML" "$RAW_CRYPTO_COMMENT_HTML"' EXIT INT TERM

# Check if NYSE/NASDAQ market is open (Mon-Fri 09:30 - 16:00 US/Eastern).
is_market_open() {
  local day_of_week hour min total_min
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
  fi
}

# Performs a single fetch for Flash Insights -> extract -> summarize -> mirror cycle.
run_flash_insights_once() {
  local now_str="$(TZ="America/New_York" date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "[$now_str] Fetching Flash Insights..."

  # Step 1: Launch headless Chrome against the authenticated profile for FLASH_INSIGHTS_URL.
  if google-chrome \
    --headless=new \
    --disable-gpu \
    --user-data-dir="$PROFILE_DIR" \
    --virtual-time-budget=15000 \
    --dump-dom \
    "$FLASH_INSIGHTS_URL" 2>/dev/null > "$RAW_FLASH_INSIGHT_HTML"; then

    if [[ ! -s "$RAW_FLASH_INSIGHT_HTML" ]]; then
      echo "ERROR: DOM dump for Flash Insights is empty — check Chrome profile session/login state." >&2
      return 1
    fi

    # Step 2: Convert raw HTML to text and extract sections.
    html2text "$RAW_FLASH_INSIGHT_HTML" | \
      awk '/^[⚡âš¡]* FlashInsights$/{f=1} f&&/click="shareOpen/{f=0; next} f{print} f&&/\[FlashInsights\]/{f=0}' \
      > "$FLASH_INSIGHTS_FILE"

    if ! grep -q "[⚡âš¡]* FlashInsights" "$FLASH_INSIGHTS_FILE"; then
      echo "WARNING: '⚡ FlashInsights' not found in $FLASH_INSIGHTS_FILE — session may have expired." >&2
    fi

    echo "OK: wrote $(wc -l < "$FLASH_INSIGHTS_FILE") lines to $FLASH_INSIGHTS_FILE"

    # Step 3: Generate summary with Ollama and output to markdown file (retry immediately on failure).
    echo "Generating summary with Ollama..."
    local ollama_success=false
    local attempt=1
    local prompt_text="Summarize the following article. highlight key macro and technical insights. prioritize posts with the most recent date and time. the audience is portfolio manager and certified financial planner. Execute risk assessments on the mentioned stocks, ETFs. Article: "

    while [[ "$ollama_success" == "false" ]]; do
      if [[ "$attempt" -gt 1 ]]; then
        echo "Retrying Ollama generation immediately (attempt $attempt)..."
      fi

      if ollama run --nowordwrap "$OLLAMA_MODEL" \
        "$prompt_text" < <(head -n "$FLASH_INSIGHTS_LINES" "$FLASH_INSIGHTS_FILE") \
        > "$FLASH_INSIGHTS_OVERVIEW_MD" && [[ -s "$FLASH_INSIGHTS_OVERVIEW_MD" ]]; then
        ollama_success=true
        echo "OK: wrote overview markdown to $FLASH_INSIGHTS_OVERVIEW_MD"
      else
        echo "ERROR: Ollama summary generation failed. Retrying immediately..." >&2
        attempt=$((attempt + 1))
        sleep 2
      fi
    done

    pandoc "$FLASH_INSIGHTS_OVERVIEW_MD" \
      -f markdown \
      -t plain \
      -o "$FLASH_INSIGHTS_OVERVIEW" \
      --wrap=none
    echo "OK: wrote overview text to $FLASH_INSIGHTS_OVERVIEW"

    # Step 4: Mirror the same overview content to a dated file under the portfolio directory.
    NEWS_DATED_FILE="$PORTFOLIO_DIR/news_$(date +%Y-%m-%d).txt"
    cp "$FLASH_INSIGHTS_OVERVIEW" "$NEWS_DATED_FILE"
    echo "OK: wrote overview text to $NEWS_DATED_FILE"
    scp -P 23 "$NEWS_DATED_FILE" hil@hil-fr-dc.freeddns.org:"$PORTFOLIO_DIR/"
    echo "OK: wrote overview text to $NEWS_DATED_FILE on hil@hil-fr-dc.freeddns.org"
  else
    echo "ERROR: google-chrome execution failed." >&2
    return 1
  fi
}

# Performs a single fetch for the latest Technical Strategy article.
fetch_technical_strategy_once() {
  local now_str="$(TZ="America/New_York" date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "[$now_str] Fetching Technical Strategy..."

  ensure_members_html

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

  html2text "$RAW_TECH_STRATEGY_HTML" | \
    awk '/Key Takeaways/{flag=1} flag{print} /______________________________/ && flag{exit}' \
    > "$TECHNICAL_STRATEGY_FILE"
  echo "OK: wrote $(wc -l < "$TECHNICAL_STRATEGY_FILE") lines to $TECHNICAL_STRATEGY_FILE"
}

# Performs a single fetch for the latest Crypto Comment article.
fetch_crypto_comment_once() {
  local now_str="$(TZ="America/New_York" date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "[$now_str] Fetching Crypto Comment..."

  ensure_members_html

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

  html2text "$RAW_CRYPTO_COMMENT_HTML" > "$CRYPTO_COMMENT_FILE"
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
        run_flash_insights_once || true
        sleep_with_countdown "$INTERVAL_MINUTES"
      else
        now_str="$(TZ="America/New_York" date '+%Y-%m-%d %H:%M:%S %Z')"
        printf "\r\033[K[%s] NYSE and NASDAQ markets are closed." "$now_str"
        closed_status_printed=true
        sleep "$CLOSED_CHECK_SLEEP"
      fi
    done
    ;;
esac
