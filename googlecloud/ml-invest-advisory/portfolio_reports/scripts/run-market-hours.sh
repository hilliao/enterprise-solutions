#!/usr/bin/env bash
#
# Purpose:
#   Continuously regenerates the portfolio reports during this script's execution
#   window (Mon-Fri, 08:00-18:00 America/New_York, excluding HOLIDAYS) and uploads
#   them to GCS. On every loop iteration it evals LOOP_COMMAND, which:
#     1) Runs report-daily.sh, then report-news-impact.sh (one flash-insights report
#        per portfolio and news site; its failure, e.g. no news file yet, is ignored).
#     2) Copies $PORTFOLIO_DIR/*.html to GCS_BUCKET with `gcloud storage cp`.
#   It then sleeps ACTIVE_SLEEP_SECONDS. Outside the window it prints a live
#   countdown (on a single terminal line) to the next 08:00 ET window start and
#   rechecks every IDLE_SLEEP_SECONDS. The window is NOT the market session
#   (09:30-16:00 ET); it starts ~1.5h before the open and runs a few hours after
#   the close to catch pre-market and after-hours moves.
#
#   This file is a template: copy it (e.g. to ~/workspace/ml-invest-report.sh) and
#   fill in the CONFIGURATION section with your paths, bucket and endpoint.
#
# Requirements:
#   - Everything required by report-daily.sh and report-news-impact.sh
#     (python3 with build_portfolio_prompt.py's dependencies, ollama, optional pandoc)
#   - `gcloud` CLI with a configuration (GCLOUD_CONFIG) that can write to GCS_BUCKET
#   - GNU `date` (uses `date -d` for time zone and date arithmetic)
#   - HOLIDAYS kept up to date; it currently lists NYSE holidays for 2026-2028
#
# Configuration (edit the CONFIGURATION section below before running):
#   GOOGLE_APPLICATION_CREDENTIALS  service account JSON key (exported to the report scripts)
#   PORTFOLIO_DIR                   portfolio *.json and news-<SITE>_YYYY-MM-DD.txt input and report output
#                                   directory (exported)
#   STOCK_QUOTES_CLOUD_RUN_URL      stock quotes endpoint (exported to build_portfolio_prompt.py)
#   PYTHON_VENV                     Python virtual environment activated before the reports run
#                                   (empty: use the python3 on PATH)
#   REPORT_SCRIPTS_DIR              folder of report-daily.sh and report-news-impact.sh
#   GCS_BUCKET / GCLOUD_CONFIG      gs:// destination for the *.html reports and the gcloud configuration
#   ACTIVE_SLEEP_SECONDS / IDLE_SLEEP_SECONDS
#                                   defaults 30s / 60s; overridable with the options below
#
# Usage:
#   ./run-market-hours.sh                      # loop forever
#   ./run-market-hours.sh --immediate          # run once now, ignoring the window, then exit
#   ./run-market-hours.sh --active-sleep 300 --idle-sleep 120
#   ./run-market-hours.sh --help
#
# Exit status:
#   0 after a successful --immediate run. Otherwise the loop aborts on the first
#   failing LOOP_COMMAND with that command's exit code; 69 means build_portfolio_prompt.py
#   could not reach the stock quotes endpoint after its retries (exponential
#   backoff up to 16s). 1 on an unknown option or a missing PYTHON_VENV.
#
set -euo pipefail

# ==============================================================================
# CONFIGURATION
# Update these variables with your specific paths and bucket names before running.
# ==============================================================================

# --- Inputs of the report scripts (exported to report-*.sh and build_portfolio_prompt.py) ---
# Service account JSON key used to call the stock quotes endpoint.
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/your/service-account-key.json"
# Portfolio *.json files and today's news-<SITE>_YYYY-MM-DD.txt files; the reports are written here too.
export PORTFOLIO_DIR="$HOME/path/to/output/portfolios"
# Stock quotes endpoint (replace 'my-gcp-project' and the region with where get-us-ticker-quotes is deployed).
export STOCK_QUOTES_CLOUD_RUN_URL="https://europe-west9-my-gcp-project.cloudfunctions.net/get-us-ticker-quotes"

# --- Python virtual environment with build_portfolio_prompt.py's dependencies ---
# Activated before the loop starts, so `. <venv>/bin/activate` isn't needed first; empty uses the python3 on PATH.
PYTHON_VENV=""  # e.g. "$HOME/workspace/py-venv"

# --- Report commands run on every loop iteration ---
# The daily report is required (a failure aborts the loop); the news impact report is optional.
REPORT_SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPORT_COMMAND="$REPORT_SCRIPTS_DIR/report-daily.sh && ($REPORT_SCRIPTS_DIR/report-news-impact.sh || true)"

# --- GCS upload of the HTML reports ---
GCS_BUCKET="gs://bucket-name/folder/"  # replace 'bucket-name' and 'folder'
GCLOUD_CONFIG="default"

# --- Timing (defaults; --active-sleep and --idle-sleep override them) ---
ACTIVE_SLEEP_SECONDS=30  # seconds between consecutive runs during the window
IDLE_SLEEP_SECONDS=60    # seconds between window rechecks outside the window
# Execution window hours, America/New_York: from WINDOW_START_HOUR_ET:00 until WINDOW_END_HOUR_ET:00.
WINDOW_START_HOUR_ET=8
WINDOW_END_HOUR_ET=18

# --- Market holidays: the loop doesn't run on these dates ---
HOLIDAYS=(
  "2026-01-01" "2026-01-19" "2026-02-16" "2026-04-03" "2026-05-25" "2026-06-19" "2026-07-03" "2026-09-07" "2026-11-26" "2026-12-25"
  "2027-01-01" "2027-01-18" "2027-02-15" "2027-03-26" "2027-05-31" "2027-06-18" "2027-07-05" "2027-09-06" "2027-11-25" "2027-12-24"
  "2028-01-17" "2028-02-21" "2028-04-14" "2028-05-29" "2028-06-19" "2028-07-04" "2028-09-04" "2028-11-23" "2028-12-25"
)

# Exit code of build_portfolio_prompt.py (EXIT_CODE_QUOTES_UNAVAILABLE) when the stock quotes endpoint still fails
# after its retries; reported with its own error message before aborting.
QUOTES_UNAVAILABLE_EXIT_CODE=69

# ==============================================================================
# FUNCTIONS
# ==============================================================================

# Returns 0 if the given YYYY-MM-DD date is in HOLIDAYS.
is_holiday() {
  local candidate_date="$1" holiday
  for holiday in "${HOLIDAYS[@]}"; do
    if [ "$candidate_date" = "$holiday" ]; then
      return 0
    fi
  done
  return 1
}

# Prints the epoch seconds of this script's next execution-window start
# (WINDOW_START_HOUR_ET:00 America/New_York on the next weekday that isn't a holiday), based on
# the current today_et/hour_et. This is NOT the actual market open (09:30 ET) --
# the window intentionally starts ~1.5h before the open and runs until 18:00 ET,
# a few hours after the 16:00 ET close, to catch pre-market and after-hours moves.
next_window_start_epoch() {
  local candidate_date="$today_et" candidate_weekday
  # Today's window has already started (or ended), so the next one is on a later day.
  if [ "$hour_et" -ge "$WINDOW_START_HOUR_ET" ]; then
    candidate_date=$(TZ=America/New_York date -d "$candidate_date +1 day" +%Y-%m-%d)
  fi
  while :; do
    candidate_weekday=$(TZ=America/New_York date -d "$candidate_date" +%u)
    if [ "$candidate_weekday" -le 5 ] && ! is_holiday "$candidate_date"; then
      TZ=America/New_York date -d "$candidate_date $(printf '%02d' "$WINDOW_START_HOUR_ET"):00:00" +%s
      return
    fi
    candidate_date=$(TZ=America/New_York date -d "$candidate_date +1 day" +%Y-%m-%d)
  done
}

print_help() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Runs the portfolio report/upload command in a loop during this script's
execution window: Mon-Fri, 08:00-18:00 America/New_York, excluding configured
holidays. Note this window is NOT the market's own hours (09:30-16:00 ET) --
it starts ~1.5h before the market open and keeps running a few hours after
the close, to also catch pre-market and after-hours activity.

If the command fails, an ERROR is printed to stderr and the script exits with
the command's exit code (69 if the stock quotes Cloud Run endpoint still fails
after retries with exponential backoff up to 16 seconds).

Options:
  --immediate          Run the command once immediately, ignoring the market
                        hours/holiday/weekday window, then exit (non-zero exit
                        if the command fails).
  --active-sleep SEC    Seconds to sleep between consecutive runs while inside
                        the active window (default: ${ACTIVE_SLEEP_SECONDS}).
  --idle-sleep SEC      Seconds to sleep between checks while outside the
                        active window (default: ${IDLE_SLEEP_SECONDS}).
  -h, --help            Show this help message and exit.
EOF
}

# ==============================================================================
# ARGUMENTS AND SETUP
# ==============================================================================

RUN_ONCE_NOW=false
while [[ $# -gt 0 ]]; do
  case $1 in
    --immediate)
      RUN_ONCE_NOW=true
      shift
      ;;
    --active-sleep)
      ACTIVE_SLEEP_SECONDS="$2"
      shift 2
      ;;
    --idle-sleep)
      IDLE_SLEEP_SECONDS="$2"
      shift 2
      ;;
    -h|--help)
      print_help
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      print_help
      exit 1
      ;;
  esac
done

if [ -n "$PYTHON_VENV" ]; then
  if [ ! -f "$PYTHON_VENV/bin/activate" ]; then
    echo "ERROR: PYTHON_VENV '$PYTHON_VENV' has no bin/activate; create it or fix PYTHON_VENV." >&2
    exit 1
  fi
  # The activate script reads variables that may be unset, so relax `set -u` while sourcing it.
  set +u
  source "$PYTHON_VENV/bin/activate"
  set -u
  echo "Using Python virtual environment: $VIRTUAL_ENV"
fi

# Generate the reports, then upload every HTML report in PORTFOLIO_DIR.
LOOP_COMMAND="$REPORT_COMMAND && gcloud storage cp $PORTFOLIO_DIR/*.html $GCS_BUCKET --configuration=$GCLOUD_CONFIG"

# ==============================================================================
# MAIN LOOP
# ==============================================================================

countdown_shown=false
while :; do
  # Current hour, weekday, and date in Eastern Time (handles EST/EDT automatically)
  hour_et=$((10#$(TZ=America/New_York date +%H)))  # 0-23
  weekday_et=$(TZ=America/New_York date +%u)        # 1=Mon ... 7=Sun
  today_et=$(TZ=America/New_York date +%Y-%m-%d)

  # Run when --immediate, or on a weekday that isn't a holiday inside the execution window.
  # The 08:00-18:00 ET window is this script's execution window, not the actual
  # market session (09:30-16:00 ET): it starts ~1.5h before the open and
  # continues a few hours after the close.
  in_window=false
  if [ "$weekday_et" -le 5 ] && ! is_holiday "$today_et" \
    && [ "$hour_et" -ge "$WINDOW_START_HOUR_ET" ] && [ "$hour_et" -lt "$WINDOW_END_HOUR_ET" ]; then
    in_window=true
  fi

  if [ "$RUN_ONCE_NOW" = "true" ] || [ "$in_window" = "true" ]; then
    # If the previous iterations were printing a countdown, drop to a fresh
    # line first so the command's own output doesn't clobber it.
    if [ "$countdown_shown" = "true" ]; then
      printf '\n'
      countdown_shown=false
    fi
    # Execute the command and abort on any failure, so a failing step isn't repeated every ACTIVE_SLEEP_SECONDS.
    # build_portfolio_prompt.py already retries the stock quotes Cloud Run endpoint with exponential backoff
    # (1, 2, 4, 8, 16s) before exiting with QUOTES_UNAVAILABLE_EXIT_CODE.
    exit_code=0
    eval "$LOOP_COMMAND" || exit_code=$?
    if [ "$exit_code" -eq "$QUOTES_UNAVAILABLE_EXIT_CODE" ]; then
      echo "ERROR: Stock quotes Cloud Run endpoint still failing after retries with exponential backoff up to 16s; aborting at $(date)" >&2
      exit "$exit_code"
    elif [ "$exit_code" -ne 0 ]; then
      echo "ERROR: Command failed with exit code $exit_code; aborting at $(date)" >&2
      exit "$exit_code"
    fi
    if [ "$RUN_ONCE_NOW" = "true" ]; then exit 0; fi
    sleep "$ACTIVE_SLEEP_SECONDS"
  else
    # Weekend, holiday, or outside window: show a live countdown until this
    # script's next execution-window start (~1.5h before actual market open).
    # No newline is printed here -- every update reuses the same terminal
    # line via \r, including across IDLE_SLEEP_SECONDS recheck cycles, so the
    # countdown doesn't spam a new line every cycle.
    next_start_epoch=$(next_window_start_epoch)
    next_start_display=$(TZ=America/New_York date -d "@$next_start_epoch" "+%Y-%m-%d %H:%M %Z")
    elapsed_seconds=0
    while [ "$elapsed_seconds" -lt "$IDLE_SLEEP_SECONDS" ]; do
      seconds_left=$(( next_start_epoch - $(date +%s) ))
      [ "$seconds_left" -le 0 ] && break
      printf '\rMarket closed. Script resumes in %dh %dm %ds at %s (~1.5h before market open).\033[K' \
        $(( seconds_left / 3600 )) $(( (seconds_left % 3600) / 60 )) $(( seconds_left % 60 )) "$next_start_display"
      countdown_shown=true
      sleep 1
      elapsed_seconds=$(( elapsed_seconds + 1 ))
    done
  fi
done
