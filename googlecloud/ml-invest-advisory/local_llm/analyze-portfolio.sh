#!/bin/bash
set -e # exit the script when execution hits any error
#set -x # print the executing lines

export PORTFOLIO_DIR="$HOME/git/enterprise-solutions/googlecloud/ml-invest-advisory/local_llm/test-portfolios"

# Check for dependencies at the start, outside the loop
if ! command -v pandoc &> /dev/null; then
  echo "Warning: pandoc is not installed. HTML reports will not be generated."
  PANDOC_EXISTS=false
else
  PANDOC_EXISTS=true
fi

PORTFOLIO_FILES=$(find "$PORTFOLIO_DIR" -maxdepth 1 -type f -name "*.json")

# Loop through each portfolio file and print its name and first x lines
for file in $PORTFOLIO_FILES; do
  echo "Found portfolio file: $file"
  head -n 6 "$file"
  echo "" # Add a blank line for readability

  PORTFOLIO_NAME=$(basename "$file" .json)
  export GET_QUOTES_CMD="python $HOME/git/enterprise-solutions/googlecloud/ml-invest-advisory/local_llm/generate-llm-prompt.py \
    --portfolio_file=$file \
    --llm_prompt_template=$HOME/git/enterprise-solutions/googlecloud/ml-invest-advisory/local_llm/prompt_template.txt \
    --output_prompt=$PORTFOLIO_DIR/llm_prompt-${PORTFOLIO_NAME}.txt"

  MD_OUTPUT_FILE="${PORTFOLIO_DIR}/realtime_analysis-${PORTFOLIO_NAME}.md"
  $GET_QUOTES_CMD && \
  ollama run gemma3 --verbose < $PORTFOLIO_DIR/llm_prompt-${PORTFOLIO_NAME}.txt   | tee "$MD_OUTPUT_FILE"

  # Convert markdown to HTML if pandoc is available
  if [ "$PANDOC_EXISTS" = true ]; then
    HTML5_OUTPUT_FILE="${PORTFOLIO_DIR}/realtime_analysis-${PORTFOLIO_NAME}.html"
    echo -e "\n--- Generating HTML report using pandoc at $HTML5_OUTPUT_FILE ---"
    DATETIME_NOW="Portfolio Analysis Report at $(date +"%Y-%m-%d %H:%M:%S %Z")"
    pandoc -s -f gfm -t html5 -o "$HTML5_OUTPUT_FILE" "$MD_OUTPUT_FILE" \
    --metadata title="$DATETIME_NOW" --include-in-header <(echo '<style>body { max-width: 80%; margin: 0 auto; } p, li, td, th { line-height: 1.5; }</style>')
  fi
done
