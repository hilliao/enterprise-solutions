#!/bin/bash
#
# Purpose:
#   Runs one LLM prompt through several local Ollama models, one after another, and saves
#   the outputs side by side for comparing report quality. For each MODEL it:
#     1) Runs `ollama run --hidethinking --verbose MODEL < PROMPT_FILE` (killed after
#        OLLAMA_TIMEOUT_SECONDS) and writes the report to $RUN_DIR/<model>.md.
#     2) Records the --verbose timings plus the CPU/GPU split and context length from
#        `ollama ps` to $RUN_DIR/<model>.stats, then unloads the model with `ollama stop`
#        so the next model gets all of the VRAM.
#   Finally writes $RUN_DIR/summary.md (one row of timings per model) and
#   $RUN_DIR/comparison.html (the reports in side-by-side columns).
#
# Requirements:
#   - `ollama` CLI with every MODEL pulled
#   - `pandoc` (optional; without it the HTML columns show the raw Markdown)
#
# Environment variables (all optional; defaults shown):
#   OUTPUT_DIR               <directory of PROMPT_FILE>/model-comparison
#   OLLAMA_TIMEOUT_SECONDS   1800 (kill `ollama run` if a model takes longer; no retry)
#   OLLAMA_THINK             unset (passed as --think=$OLLAMA_THINK, e.g. false, low, medium, high)
#   DEBUG                    set to any value to trace execution (set -x)
#
# Usage:
#   ./compare-models.sh PROMPT_FILE [MODEL ...]
#   ./compare-models.sh $PORTFOLIO_DIR/daily-report-my_portfolio.txt
#   ./compare-models.sh $PORTFOLIO_DIR/daily-report-my_portfolio.txt gemma3:12b gemma4:12b-it-qat qwen3.5:9b-q8_0
#
#   MODEL defaults to gemma4:12b-it-qat and qwen3.5:9b-q8_0. Outputs go to a new
#   $OUTPUT_DIR/<prompt name>_YYYYMMDD-HHMMSS directory on every run.
#
# Exit status:
#   1 on a usage error; otherwise 0 if every model finished, or the exit code of the last
#   failing `ollama run` (124 or 137 means it exceeded OLLAMA_TIMEOUT_SECONDS). A failing
#   model doesn't stop the remaining models from running.

set -e # exit the script when execution hits any error
set -o pipefail # ensure exit code of pipe is the rightmost non-zero exit code
[[ -n "${DEBUG:-}" ]] && set -x # print the executing lines if DEBUG is set

# ---------------------------------------------------------------------------
# Arguments and settings (environment variables, see the header for their defaults)
# ---------------------------------------------------------------------------

# Models compared when none is given on the command line.
DEFAULT_MODELS=(gemma4:12b-it-qat qwen3.5:9b-q8_0)

if [ $# -lt 1 ] || [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
  sed -n '2,/^$/s/^# \{0,1\}//p' "$0"
  exit 1
fi
PROMPT_FILE="$1"
shift
MODELS=("$@")
if [ ${#MODELS[@]} -eq 0 ]; then
  MODELS=("${DEFAULT_MODELS[@]}")
fi

# Parent folder of the timestamped run folder.
OUTPUT_DIR="${OUTPUT_DIR:-$(dirname "$PROMPT_FILE")/model-comparison}"
# How long one model may take before `ollama run` is killed (no retry).
OLLAMA_TIMEOUT_SECONDS="${OLLAMA_TIMEOUT_SECONDS:-1800}"
# Passed as --think=$OLLAMA_THINK when set (e.g. false, low, medium, high).
OLLAMA_THINK="${OLLAMA_THINK:-}"

# ---------------------------------------------------------------------------
# Input checks
# ---------------------------------------------------------------------------
if [ ! -r "$PROMPT_FILE" ]; then
  echo "ERROR: Prompt file is missing or not readable at: $PROMPT_FILE" >&2
  exit 1
fi
if ! [[ "$OLLAMA_TIMEOUT_SECONDS" =~ ^[1-9][0-9]*$ ]]; then
  echo "ERROR: OLLAMA_TIMEOUT_SECONDS must be a positive integer number of seconds, got: $OLLAMA_TIMEOUT_SECONDS" >&2
  exit 1
fi
THINK_ARGS=()
if [ -n "$OLLAMA_THINK" ]; then
  THINK_ARGS=("--think=$OLLAMA_THINK")
fi

# Fail fast on a typo'd or un-pulled model instead of after the earlier models have run.
for model in "${MODELS[@]}"; do
  if ! ollama show "$model" > /dev/null 2>&1; then
    echo "ERROR: Model $model is not available locally. Run: ollama pull $model" >&2
    exit 1
  fi
done

# ---------------------------------------------------------------------------
# Run every model
# ---------------------------------------------------------------------------
PROMPT_NAME=$(basename "$PROMPT_FILE" .txt)
RUN_DIR="$OUTPUT_DIR/${PROMPT_NAME}_$(date +%Y%m%d-%H%M%S)"
mkdir -p "$RUN_DIR"
cp "$PROMPT_FILE" "$RUN_DIR/prompt.txt"
echo "Comparing ${MODELS[*]} on $PROMPT_FILE; writing outputs to $RUN_DIR"

# Prints the value of the `ollama run --verbose` timing line named LABEL (e.g. "eval rate") from STATS_FILE.
stat_value() {
  local label="$1" stats_file="$2"
  grep -m1 "^$label:" "$stats_file" | sed "s/^$label: *//" || true
}

# Model names contain ':' and may contain '/', which are awkward in file names.
model_file_name() {
  echo "$1" | tr ':/' '__'
}

# The model's outputs are $RUN_DIR/<model file name>.md (report) and .stats (timings).
final_exit_code=0
for model in "${MODELS[@]}"; do
  output_base="$RUN_DIR/$(model_file_name "$model")"
  echo -e "\n=== $model: started at $(date) ==="
  exit_code=0
  start_seconds=$SECONDS
  # stdout is the report. stderr carries the spinner's terminal escape codes and the --verbose timings.
  timeout --foreground --kill-after=10s "${OLLAMA_TIMEOUT_SECONDS}s" \
    ollama run --nowordwrap --hidethinking --verbose "${THINK_ARGS[@]}" "$model" < "$PROMPT_FILE" \
    > "$output_base.md" 2> "$output_base.stderr" || exit_code=$?
  wall_seconds=$((SECONDS - start_seconds))

  # Strip the escape codes and spinner characters so only the timing lines remain.
  sed -e 's/\x1b\[[0-9;?]*[a-zA-Z]//g' -e 's/[⠀-⣿]//g' -e 's/^ *//' "$output_base.stderr" | grep -v '^$' > "$output_base.stats" || true
  rm -f "$output_base.stderr"
  {
    echo "wall clock: ${wall_seconds}s"
    echo "exit code: $exit_code"
    # The model stays loaded after `ollama run` returns, so `ollama ps` still shows how it was split.
    # Columns: NAME ID SIZE(2 fields) PROCESSOR(2 fields, e.g. "27%/73% CPU/GPU" or "100% GPU") CONTEXT ...
    ollama ps | awk -v m="$model" '$1 == m { print "processor: " $5 " " $6; print "context: " $7 }'
  } >> "$output_base.stats"
  ollama stop "$model" || true

  if [ "$exit_code" -ne 0 ]; then
    echo "WARNING: ollama run exited with $exit_code for $model after ${wall_seconds}s (124 or 137 means it exceeded ${OLLAMA_TIMEOUT_SECONDS}s)" >&2
    final_exit_code=$exit_code
  fi
  echo "=== $model: finished in ${wall_seconds}s, $(wc -w < "$output_base.md") words, $(stat_value "eval rate" "$output_base.stats") ==="
done

# ---------------------------------------------------------------------------
# Summary table and side-by-side HTML
# ---------------------------------------------------------------------------
SUMMARY_FILE="$RUN_DIR/summary.md"
{
  echo "| Model | Exit code | Wall clock | Words | Prompt tokens | Output tokens | Output rate | CPU/GPU | Context |"
  echo "|---|---|---|---|---|---|---|---|---|"
  for model in "${MODELS[@]}"; do
    output_base="$RUN_DIR/$(model_file_name "$model")"
    echo "| $model | $(stat_value "exit code" "$output_base.stats") | $(stat_value "wall clock" "$output_base.stats") | $(wc -w < "$output_base.md") \
| $(stat_value "prompt eval count" "$output_base.stats") | $(stat_value "eval count" "$output_base.stats") | $(stat_value "eval rate" "$output_base.stats") \
| $(stat_value "processor" "$output_base.stats") | $(stat_value "context" "$output_base.stats") |"
  done
} > "$SUMMARY_FILE"
echo -e "\n--- Summary ($SUMMARY_FILE) ---"
cat "$SUMMARY_FILE"

# Converts a Markdown file to an HTML fragment, falling back to the escaped raw text without pandoc.
markdown_to_html() {
  if command -v pandoc &> /dev/null; then
    pandoc -f gfm -t html5 "$1"
  else
    echo "<pre>"
    sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g' "$1"
    echo "</pre>"
  fi
}

HTML_FILE="$RUN_DIR/comparison.html"
{
  cat <<EOF
<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Model comparison: $PROMPT_NAME</title>
<style>
  body { font-family: sans-serif; margin: 1em; }
  table { border-collapse: collapse; } td, th { border: 1px solid #ccc; padding: 4px 8px; }
  .columns { display: grid; grid-template-columns: repeat(${#MODELS[@]}, minmax(0, 1fr)); gap: 1em; }
  .column { border: 1px solid #ccc; padding: 0 1em; overflow-wrap: anywhere; }
  .column h1 { font-size: 1.3em; } .column h2 { font-size: 1.15em; }
  p, li, td, th { line-height: 1.5; }
</style></head><body>
<h1>Model comparison: $PROMPT_NAME ($(date +"%Y-%m-%d %H:%M:%S %Z"))</h1>
EOF
  markdown_to_html "$SUMMARY_FILE"
  echo '<div class="columns">'
  for model in "${MODELS[@]}"; do
    echo "<div class=\"column\"><h2 style=\"color: brown;\">$model</h2>"
    markdown_to_html "$RUN_DIR/$(model_file_name "$model").md"
    echo "</div>"
  done
  echo "</div></body></html>"
} > "$HTML_FILE"
echo -e "\nSide-by-side comparison: $HTML_FILE"

exit "$final_exit_code"
