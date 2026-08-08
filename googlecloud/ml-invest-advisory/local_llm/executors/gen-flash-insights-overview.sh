#!/bin/bash
#
# Purpose:
#   Monitors and fetches the logged-in "Flash Insights" members page from
#   fundstratdirect.com using headless Chrome continuously during NYSE/NASDAQ
#   market open hours (Monday-Friday 09:30 - 16:00 ET).
#   Converts HTML to plain text, extracts relevant sections into
#   ~/Documents/flash-insights.txt, and generates an AI summary with Ollama
#   saved to ~/Documents/flash-insights.md.
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
#          "https://fundstratdirect.com/members/flashinsights/"
#
#   2. In that window, log in manually with your fundstratdirect.com
#      credentials. Confirm the Flash Insights page loads correctly (you
#      should see article content, not a login form), then close Chrome
#      completely. The profile directory now holds the session cookie(s)
#      that headless Chrome will reuse on every run of this script.
#
#   Note: Most membership sites issue cookies with expiration dates, or rely
#   on short-lived sessions with server-side timeouts. Expect this session
#   to expire eventually — if the script starts writing a login page instead
#   of article text, repeat steps 1-2 to re-authenticate the profile.
#
# Usage:
#   ./gen-flash-insights-overview.sh           # Normal mode (loops continuously during market hours)
#   ./gen-flash-insights-overview.sh --force   # Force mode (runs exactly once, regardless of market hours)
#

set -euo pipefail

# Environment & Path Configuration
PROFILE_DIR="$HOME/workspace/chrome-flashinsights-profile"
URL="https://fundstratdirect.com/members/flashinsights/"
FLASH_INSIGHTS_FILE="$HOME/Documents/flash-insights.txt"
FLASH_INSIGHTS_OVERVIEW_MD="$HOME/Documents/flash-insights-overview.md"
FLASH_INSIGHTS_OVERVIEW="$HOME/Documents/flash-insights-overview.txt"
PORTFOLIO_DIR="$HOME/workspace/portfolios"
INTERVAL_MINUTES=20
CLOSED_CHECK_SLEEP=60
export OLLAMA_HOST="${OLLAMA_HOST:-8400f:11435}"
OLLAMA_MODEL="gemma3:4b"

if [[ ! -d "$PROFILE_DIR" ]]; then
  echo "ERROR: Profile directory '$PROFILE_DIR' does not exist." >&2
  exit 1
fi

FORCE_EXECUTION=false
if [[ "${1:-}" == "--force" || \
      "${1:-}" == "-f" || \
      "${1:-}" == "force" || \
      "${1:-}" == "true" || \
      "${1:-}" == "1" ]]; then
  FORCE_EXECUTION=true
  echo "INFO: Force execution enabled via command-line argument. Script will run once and exit."
fi

# Temporary file setup and cleanup
RAW_HTML="$(mktemp /tmp/flash-insights-XXXXXX.html)"
mkdir -p "$(dirname "$FLASH_INSIGHTS_FILE")"
mkdir -p "$PORTFOLIO_DIR"
trap 'rm -f "$RAW_HTML"' EXIT INT TERM

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

# Performs a single fetch -> extract -> summarize -> mirror cycle.
run_once() {
  local now_str="$(TZ="America/New_York" date '+%Y-%m-%d %H:%M:%S %Z')"

  if [[ "$FORCE_EXECUTION" == "true" ]]; then
    echo "[$now_str] FORCE execution active. Fetching Flash Insights..."
  else
    echo "[$now_str] NYSE/NASDAQ market is open. Fetching Flash Insights..."
  fi

  # Step 1: Launch headless Chrome against the authenticated profile.
  if google-chrome \
    --headless=new \
    --disable-gpu \
    --user-data-dir="$PROFILE_DIR" \
    --virtual-time-budget=15000 \
    --dump-dom \
    "$URL" > "$RAW_HTML"; then

    if [[ ! -s "$RAW_HTML" ]]; then
      echo "ERROR: DOM dump is empty — check Chrome profile session/login state." >&2
      return 1
    fi

    # Step 2: Convert raw HTML to text and extract sections.
    html2text "$RAW_HTML" | \
      awk '/^[⚡âš¡]* FlashInsights$/,/\[FlashInsights\]/' \
      > "$FLASH_INSIGHTS_FILE"

    if ! grep -q "[⚡âš¡]* FlashInsights" "$FLASH_INSIGHTS_FILE"; then
      echo "WARNING: 'âš¡ FlashInsights' not found in $FLASH_INSIGHTS_FILE — session may have expired." >&2
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
        "$prompt_text" < <(head -n 60 "$FLASH_INSIGHTS_FILE") \
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

    # Step 4: Mirror the same overview content to a dated file under portfolios/.
    NEWS_DATED_FILE="$PORTFOLIO_DIR/news_$(date +%Y-%m-%d).txt"
    cp "$FLASH_INSIGHTS_OVERVIEW" "$NEWS_DATED_FILE"
    echo "OK: wrote overview text to $NEWS_DATED_FILE"
  else
    echo "ERROR: google-chrome execution failed." >&2
    return 1
  fi
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

echo "Starting web content polling monitor (Execution frequency: every ${INTERVAL_MINUTES} minutes)..."

# FORCE_EXECUTION path: run exactly one cycle and exit immediately.
if [[ "$FORCE_EXECUTION" == "true" ]]; then
  run_once || true
  echo "INFO: Force execution complete. Exiting after single run."
  exit 0
fi

# Normal path: loop continuously, only fetching during market hours.
closed_status_printed=false
while true; do
  if is_market_open; then
    if [[ "$closed_status_printed" == "true" ]]; then
      printf "\n"
      closed_status_printed=false
    fi
    run_once || true
    sleep_with_countdown "$INTERVAL_MINUTES"
  else
    local now_str="$(TZ="America/New_York" date '+%Y-%m-%d %H:%M:%S %Z')"
    printf "\r\033[K[%s] NYSE and NASDAQ markets are closed." "$now_str"
    closed_status_printed=true
    sleep "$CLOSED_CHECK_SLEEP"
  fi
done
