#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# CONFIGURATION
# Update these variables with your specific paths and bucket names before running.
# ==============================================================================

# Path to your Google Cloud Service Account JSON key
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/your/service-account-key.json"

# Internal paths
PORTFOLIO_SCRIPT="$HOME/path/to/your/gen-daily-portfolio-reports.sh && $HOME/path/to/your/gen-flash-insights-portfolio-reports.sh"
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
    *)
      echo "Unknown option: $1"
      exit 1
      ;;
  esac
done

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

  # Run logic: --immediate OR (Not a holiday AND Weekday (1-5) AND Business Hours)
  if [ "$IMMEDIATE" = "true" ] || { [ "$is_holiday" = "false" ] && [ "$dow_et" -le 5 ] && [ "$hour_et" -ge 8 ] && [ "$hour_et" -lt 18 ]; }; then
    # Execute the command
    if ! eval "$CMD"; then
      echo "Warning: Command failed at $(date)" >&2
      if [ "$IMMEDIATE" = "true" ]; then exit 1; fi
    fi
    if [ "$IMMEDIATE" = "true" ]; then exit 0; fi
    sleep "$ACTIVE_SLEEP"
  else
    # Weekend or outside window: sleep until next check
    sleep "$IDLE_SLEEP"
  fi
done