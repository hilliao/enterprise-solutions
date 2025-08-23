#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

# Function to check if a command exists
command_exists () {
  command -v "$1" >/dev/null 2>&1
}

# --- Check for required commands ---
echo "--- Checking for required commands ---"

if ! command_exists ollama; then
  echo "Error: 'ollama' command not found." >&2
  echo "Please install Ollama (https://ollama.com/download) to use this script." >&2
  exit 1
fi

if ! command_exists pandoc; then
  echo "Error: 'pandoc' command not found." >&2
  echo "Please install Pandoc (https://pandoc.org/installing.html) to use this script." >&2
  exit 1
fi

echo "--- All required commands found ---"

# --- Script variables ---
export PROMPT_FILE="prompt.txt"
TEMPLATE_FILE="prompt_template.md" # Assuming this file exists in the same directory
NARRATE_SCRIPT="./narrate_portfolio.sh" # Assuming this script is executable in the same directory
OUTPUT_REPORT="portfolio_summary_report.md"
FINAL_HTML_REPORT="portfolio_summary_report.html"

# --- Main script logic ---

echo "--- Narrating the portfolio..."
# Execute the narrate_portfolio.sh script and capture its output
# Ensure narrate_portfolio.sh is executable and returns relevant output
if [ ! -f "$NARRATE_SCRIPT" ]; then
  echo "Error: '$NARRATE_SCRIPT' not found. Please ensure it's in the same directory and executable." >&2
  exit 1
fi

NARRATED_OUTPUT=$("$NARRATE_SCRIPT") # Using command substitution to capture output
echo "$NARRATED_OUTPUT" # Print the captured narration to terminal

echo "--- Building and sending the prompt to Ollama ---"

# Copy the template file to the prompt file
if [ ! -f "$TEMPLATE_FILE" ]; then
  echo "Error: '$TEMPLATE_FILE' not found. Please ensure it's in the same directory." >&2
  exit 1
fi
cp "$TEMPLATE_FILE" "$PROMPT_FILE"

# Append the narrated output to the prompt file
echo "$NARRATED_OUTPUT" >> "$PROMPT_FILE"

# Display the final prompt content (optional, for debugging/verification)
echo "--- Final prompt content being sent to Ollama ---"
cat "$PROMPT_FILE"
echo "-------------------------------------------------"

# Run Ollama with the generated prompt and pipe output to a markdown file and terminal
echo "--- Running Ollama (gemma3:12b) with the prompt ---"
ollama run gemma3:12b "Execute prompt: " < "$PROMPT_FILE" | tee "$OUTPUT_REPORT"

echo "--- Converting Markdown report to HTML using Pandoc ---"
# Convert the markdown report to HTML
pandoc -s "$OUTPUT_REPORT" -o "$FINAL_HTML_REPORT"

echo "--- Process complete. Report saved to $FINAL_HTML_REPORT ---"
