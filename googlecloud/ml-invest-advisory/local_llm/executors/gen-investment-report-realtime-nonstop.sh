#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# CONFIGURATION
# Update these variables with your specific paths and bucket names before running.
# ==============================================================================

# Path to your Google Cloud Service Account JSON key
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/your/service-account-key.json"

# Internal paths
PORTFOLIO_SCRIPT="$HOME/path/to/your/gen-daily-portfolio-reports.sh && ($HOME/path/to/your/gen-flash-insights-portfolio-reports.sh || true)"
export PORTFOLIO_DIR="$HOME/path/to/output/portfolios/"

# GCS Bucket destination (Replace 'folder' and 'bucket-name')
GCS_BUCKET="gs://bucket-name/folder/"
GCLOUD_CONFIG="default"

# Construct the command
export CMD="$PORTFOLIO_SCRIPT && gcloud storage cp $PORTFOLIO_DIR/*.html $GCS_BUCKET --configuration=$GCLOUD_CONFIG"

# Timing configurations (defaults)
ACTIVE_SLEEP=30       # seconds between consecutive runs during the window
IDLE_SLEEP=60         # seconds to wait when outside the window

# ==============================================================================
# LOGIC
# ==============================================================================

# Market holidays - do not run on these dates
HOLIDAYS=(
  "2026-01-01" "2026-01-19" "2026-02-16" "2026-04-03" "2026-05-25" "2026-06-19" "2026-07-03" "2026-09-07" "2026-11-26" "2026-12-25"
  "2027-01-01" "2027-01-18" "2027-02-15" "2027-03-26" "2027-05-31" "2027-06-18" "2027-07-05" "2027-09-06" "2027-11-25" "2027-12-24"
  "2028-01-17" "2028-02-21" "2028-04-14" "2028-05-29" "2028-06-19" "2028-07-04" "2028-09-04" "2028-11-23" "2028-12-25"
)

# Computes the epoch seconds of this script's next execution-window start
# (08:00 America/New_York on the next weekday that isn't a holiday), based on
# the current date_et/hour_et. This is NOT the actual market open (09:30 ET) --
# the window intentionally starts ~1.5h before the open and runs until 18:00 ET,
# a few hours after the 16:00 ET close, to catch pre-market and after-hours moves.
next_script_start_epoch() {
  local candidate_date="$date_et"
  local skip_today=false
  [ "$hour_et" -ge 8 ] && skip_today=true
  while :; do
    if [ "$skip_today" = "true" ]; then
      candidate_date=$(TZ=America/New_York date -d "$candidate_date +1 day" +%Y-%m-%d)
      skip_today=false
    fi
    local cdow cand_is_holiday=false
    cdow=$(TZ=America/New_York date -d "$candidate_date" +%u)
    for holiday in "${HOLIDAYS[@]}"; do
      if [ "$candidate_date" = "$holiday" ]; then
        cand_is_holiday=true
        break
      fi
    done
    if [ "$cdow" -le 5 ] && [ "$cand_is_holiday" = "false" ]; then
      TZ=America/New_York date -d "$candidate_date 08:00:00" +%s
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

Options:
  --immediate          Run the command once immediately, ignoring the market
                        hours/holiday/weekday window, then exit (non-zero exit
                        if the command fails).
  --active-sleep SEC    Seconds to sleep between consecutive runs while inside
                        the active window (default: ${ACTIVE_SLEEP}).
  --idle-sleep SEC      Seconds to sleep between checks while outside the
                        active window (default: ${IDLE_SLEEP}).
  -h, --help            Show this help message and exit.
EOF
}

# Parse command line arguments
IMMEDIATE=false
while [[ $# -gt 0 ]]; do
  case $1 in
    --immediate)
      IMMEDIATE=true
      shift
      ;;
    --active-sleep)
      ACTIVE_SLEEP="$2"
      shift 2
      ;;
    --idle-sleep)
      IDLE_SLEEP="$2"
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

WAS_IDLE=false
while :; do
  # Current hour, weekday, and date in Eastern Time (handles EST/EDT automatically)
  hour_et=$(TZ=America/New_York date +%H)   # 00-23
  dow_et=$(TZ=America/New_York date +%u)    # 1=Mon ... 7=Sun
  date_et=$(TZ=America/New_York date +%Y-%m-%d)

  # Check if today is a holiday
  is_holiday=false
  for holiday in "${HOLIDAYS[@]}"; do
    if [ "$date_et" = "$holiday" ]; then
      is_holiday=true
      break
    fi
  done

  # Run logic: --immediate OR (Not a holiday AND Weekday (1-5) AND execution window)
  # The 08:00-18:00 ET window is this script's execution window, not the actual
  # market session (09:30-16:00 ET): it starts ~1.5h before the open and
  # continues a few hours after the close.
  if [ "$IMMEDIATE" = "true" ] || { [ "$is_holiday" = "false" ] && [ "$dow_et" -le 5 ] && [ "$hour_et" -ge 8 ] && [ "$hour_et" -lt 18 ]; }; then
    # If the previous iterations were printing a countdown, drop to a fresh
    # line first so the command's own output doesn't clobber it.
    if [ "$WAS_IDLE" = "true" ]; then
      printf '\n'
      WAS_IDLE=false
    fi
    # Execute the command
    if ! eval "$CMD"; then
      echo "Warning: Command failed at $(date)" >&2
      if [ "$IMMEDIATE" = "true" ]; then exit 1; fi
    fi
    if [ "$IMMEDIATE" = "true" ]; then exit 0; fi
    sleep "$ACTIVE_SLEEP"
  else
    # Weekend, holiday, or outside window: show a live countdown until this
    # script's next execution-window start (~1.5h before actual market open).
    # No newline is printed here -- every update reuses the same terminal
    # line via \r, including across IDLE_SLEEP recheck cycles, so the
    # countdown doesn't spam a new line every cycle.
    next_run_epoch=$(next_script_start_epoch)
    next_run_display=$(TZ=America/New_York date -d "@$next_run_epoch" "+%Y-%m-%d %H:%M %Z")
    elapsed=0
    while [ "$elapsed" -lt "$IDLE_SLEEP" ]; do
      now_epoch=$(date +%s)
      diff=$(( next_run_epoch - now_epoch ))
      [ "$diff" -le 0 ] && break
      wait_h=$(( diff / 3600 ))
      wait_m=$(( (diff % 3600) / 60 ))
      wait_s=$(( diff % 60 ))
      printf '\rMarket closed. Script resumes in %dh %dm %ds at %s (~1.5h before market open).\033[K' "$wait_h" "$wait_m" "$wait_s" "$next_run_display"
      WAS_IDLE=true
      sleep 1
      elapsed=$(( elapsed + 1 ))
    done
  fi
done