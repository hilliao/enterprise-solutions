#!/bin/bash
#
# Purpose:
#   PoC news aggregator that fetches page(s) from news sites using headless
#   Chrome, converts the DOM dump to text, and generates an AI summary with
#   Ollama. Supports both a built-in site registry (wsj, cnbc) and arbitrary
#   ad-hoc URLs (e.g. a specific Bloomberg article page).
#
# Requirements:
#   - google-chrome installed and on PATH
#   - `html2text` CLI installed via: sudo apt install html2text
#   - `ollama` CLI installed and accessible
#   - `pandoc` (optional, for markdown -> plain text conversion of the summary)
#
# Usage:
#   ./news-aggregate.sh                                   # Fetch & summarize ALL registered sites
#   ./news-aggregate.sh --site wsj                        # Fetch & summarize only WSJ
#   ./news-aggregate.sh --site cnbc                       # Fetch & summarize only CNBC
#   ./news-aggregate.sh --site all                        # Fetch & summarize all registered sites (explicit)
#   ./news-aggregate.sh --url <URL> --name <label>        # Fetch & summarize an arbitrary URL
#   ./news-aggregate.sh --url <URL> --name <label> --lines 400
#                                                          # Use first 400 lines of extracted text as the Ollama prompt input (default 200)
#   ./news-aggregate.sh --list                            # List available site keys
#   ./news-aggregate.sh -h|--help                         # Show help
#
# Examples:
#   ./news-aggregate.sh --url "https://www.bloomberg.com/markets" --name bloomberg-markets
#   ./news-aggregate.sh --url "https://www.bloomberg.com/news/articles/xxxx" --name bbg-article --lines 500
#

set -euo pipefail

# ---------------------------------------------------------------------------
# Environment & Path Configuration
# ---------------------------------------------------------------------------
PROFILE_DIR="$HOME/workspace/chrome-flashinsights-profile"
if [[ ! -d "$PROFILE_DIR" ]]; then
  echo "ERROR: Profile directory '$PROFILE_DIR' does not exist." >&2
  exit 1
fi

OUTPUT_DIR="$HOME/Documents/news-aggregate"
mkdir -p "$OUTPUT_DIR"

export OLLAMA_HOST="${OLLAMA_HOST:-8400f:11435}"
OLLAMA_MODEL="${OLLAMA_MODEL:-gemma3:4b}"

DEFAULT_PROMPT_LINES=200
DEFAULT_VIRTUAL_TIME_BUDGET=15000

# Registry of built-in sites: key -> URL
declare -A SITE_URLS=(
  [wsj]="https://www.wsj.com/"
  [cnbc]="https://www.cnbc.com/"
)

PROMPT_TEXT="Summarize the following news page content. Highlight the top headlines, key macro/market-moving stories, and any notable stock, sector, or economic developments. Prioritize the most prominent and most recent items. The audience is a portfolio manager and certified financial planner. Article: "

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

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
  trap 'rm -f "$raw_html"' RETURN

  local text_file="$OUTPUT_DIR/${name}.txt"
  local summary_md="$OUTPUT_DIR/${name}-summary.md"
  local summary_txt="$OUTPUT_DIR/${name}-summary.txt"

  echo "[$now_str] Fetching $name ($url)..."

  if ! google-chrome \
    --headless=new \
    --disable-gpu \
    --user-data-dir="$PROFILE_DIR" \
    --virtual-time-budget="$DEFAULT_VIRTUAL_TIME_BUDGET" \
    --dump-dom \
    "$url" 2>/dev/null > "$raw_html"; then
    echo "ERROR: google-chrome execution failed for $url." >&2
    return 1
  fi

  if [[ ! -s "$raw_html" ]]; then
    echo "ERROR: DOM dump for $url is empty." >&2
    return 1
  fi

  html2text "$raw_html" > "$text_file"

  if [[ ! -s "$text_file" ]]; then
    echo "ERROR: html2text produced empty output for $name." >&2
    return 1
  fi
  echo "OK: wrote $(wc -l < "$text_file") lines to $text_file"

  echo "Generating summary for $name with Ollama (using first $prompt_lines lines)..."
  local ollama_success=false
  local attempt=1

  while [[ "$ollama_success" == "false" ]]; do
    if [[ "$attempt" -gt 1 ]]; then
      echo "Retrying Ollama generation for $name (attempt $attempt)..."
    fi

    if ollama run --nowordwrap "$OLLAMA_MODEL" \
      "$PROMPT_TEXT" < <(head -n "$prompt_lines" "$text_file") \
      > "$summary_md" && [[ -s "$summary_md" ]]; then
      ollama_success=true
      echo "OK: wrote summary markdown to $summary_md"
    else
      echo "ERROR: Ollama summary generation failed for $name. Retrying..." >&2
      attempt=$((attempt + 1))
      sleep 2
      if [[ "$attempt" -gt 5 ]]; then
        echo "ERROR: giving up on $name after $((attempt - 1)) attempts." >&2
        return 1
      fi
    fi
  done

  if command -v pandoc >/dev/null 2>&1; then
    pandoc "$summary_md" -f markdown -t plain -o "$summary_txt" --wrap=none
    echo "OK: wrote summary text to $summary_txt"
  else
    cp "$summary_md" "$summary_txt"
    echo "WARNING: pandoc not found; copied markdown as-is to $summary_txt" >&2
  fi
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
  echo "Usage: $0 [OPTION]"
  echo ""
  echo "Options:"
  echo "  --site <key>         Fetch & summarize a registered site. Valid keys: ${!SITE_URLS[*]}, all"
  echo "  --url <URL>          Fetch & summarize an arbitrary URL (any site/page, e.g. Bloomberg)"
  echo "  --name <label>       Output file name/label to use with --url (default: derived from URL)"
  echo "  --lines <N>          Number of lines from extracted text fed to Ollama (default: $DEFAULT_PROMPT_LINES)"
  echo "  --list               List available registered site keys and their URLs"
  echo "  -h, --help           Display this help message"
  echo ""
  echo "With no arguments, fetches & summarizes ALL registered sites using $DEFAULT_PROMPT_LINES lines."
  echo ""
  echo "Examples:"
  echo "  $0 --site wsj"
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

while [[ $# -gt 0 ]]; do
  case "$1" in
    --site)
      [[ $# -ge 2 ]] || { echo "ERROR: --site requires an argument (${!SITE_URLS[*]}, all)." >&2; exit 1; }
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

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if [[ -n "$CUSTOM_URL" ]]; then
  NAME="$CUSTOM_NAME"
  if [[ -z "$NAME" ]]; then
    NAME="$(derive_name_from_url "$CUSTOM_URL")"
    echo "INFO: --name not given; derived name '$NAME' from URL."
  fi
  process_site "$NAME" "$CUSTOM_URL" "$PROMPT_LINES"
elif [[ -z "$SELECTED_SITE" || "$SELECTED_SITE" == "all" ]]; then
  overall_status=0
  for key in "${!SITE_URLS[@]}"; do
    process_site "$key" "${SITE_URLS[$key]}" "$PROMPT_LINES" || overall_status=1
  done
  exit "$overall_status"
else
  if [[ -z "${SITE_URLS[$SELECTED_SITE]+x}" ]]; then
    echo "ERROR: Unknown site key '$SELECTED_SITE'. Valid keys: ${!SITE_URLS[*]}, all" >&2
    exit 1
  fi
  process_site "$SELECTED_SITE" "${SITE_URLS[$SELECTED_SITE]}" "$PROMPT_LINES"
fi

echo "INFO: News aggregate run complete."
