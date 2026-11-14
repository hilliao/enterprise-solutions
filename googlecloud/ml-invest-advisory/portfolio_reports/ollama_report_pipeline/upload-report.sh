#!/usr/bin/env bash
#
# Purpose:
#   Uploads one HTML report to its portfolio's folder in Cloud Storage:
#     GCS_BUCKET<portfolio>/<report>.html, e.g. gs://bucket/reports/yang/daily-report-yang-llm-generated.html
#   The portfolio is the longest portfolio *.json name in PORTFOLIO_DIR that the report's file name ends with, as in
#   daily-report-<portfolio>-llm-generated.html and news-<site>-<portfolio>-llm-generated.html. Longest wins, so
#   news-wsj-vicky-tw-portfolio-... goes to vicky-tw-portfolio, not to a portfolio named tw-portfolio.
#
#   report-common.sh's write_html_report runs this script (as REPORT_UPLOAD_COMMAND) as soon as it has written a
#   report, so each report is uploaded when it is generated instead of after all of them. run-market-hours.sh sets
#   REPORT_UPLOAD_COMMAND and the variables below.
#
# Requirements:
#   - `gcloud` CLI with a configuration (GCLOUD_CONFIG) that can write to GCS_BUCKET
#
# Environment variables (all required):
#   GCS_BUCKET     gs:// folder that gets one sub-folder per portfolio, e.g. gs://bucket-name/reports/
#   GCLOUD_CONFIG  gcloud configuration used for the upload (--configuration)
#   PORTFOLIO_DIR  folder of the portfolio *.json files
#
# Usage:
#   GCS_BUCKET=gs://bucket-name/reports/ GCLOUD_CONFIG=default PORTFOLIO_DIR=~/workspace/portfolios \
#     ./upload-report.sh ~/workspace/portfolios/daily-report-yang-llm-generated.html
#
# Exit status:
#   0 after the upload; 64 on a usage error or missing variable; 66 if the file is missing; 65 if the file name
#   matches no portfolio; otherwise gcloud's exit code.

set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "Usage: $0 REPORT_HTML_FILE" >&2
  exit 64
fi
for variable in GCS_BUCKET GCLOUD_CONFIG PORTFOLIO_DIR; do
  if [ -z "${!variable:-}" ]; then
    echo "ERROR: $variable is not set." >&2
    exit 64
  fi
done

report_html="$1"
if [ ! -f "$report_html" ]; then
  echo "ERROR: report file not found: $report_html" >&2
  exit 66
fi

file_name="$(basename "$report_html")"
shopt -s nullglob
portfolio_name=""
for portfolio_file in "$PORTFOLIO_DIR"/*.json; do
  candidate="$(basename "$portfolio_file" .json)"
  if [[ "$file_name" == *-"$candidate"-llm-generated.html && ${#candidate} -gt ${#portfolio_name} ]]; then
    portfolio_name="$candidate"
  fi
done
if [ -z "$portfolio_name" ]; then
  echo "ERROR: $file_name matches no portfolio *.json in $PORTFOLIO_DIR; not uploaded." >&2
  exit 65
fi

destination="${GCS_BUCKET%/}/$portfolio_name/"
echo "--- Uploading $file_name to $destination ---"
gcloud storage cp "$report_html" "$destination" --configuration="$GCLOUD_CONFIG"
