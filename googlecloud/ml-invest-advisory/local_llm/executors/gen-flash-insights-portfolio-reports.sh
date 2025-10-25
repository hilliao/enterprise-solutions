#!/bin/bash
set -e # exit the script when execution hits any error
#set -x # print the executing lines

export PORTFOLIO_DIR="$HOME/git/enterprise-solutions/googlecloud/ml-invest-advisory/local_llm/test-portfolios"
export LLM_PROMPT_TEMPLATE="$HOME/git/enterprise-solutions/googlecloud/ml-invest-advisory/local_llm/prompt_templates/flash-insights-report-template.txt"
export USE_CASE="flash-insights"
export NEWS_FILE="$PORTFOLIO_DIR/news.txt" # Assuming news.txt is in the same directory as portfolios

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
  OUTPUT_PROMPT_FILE="$PORTFOLIO_DIR/$USE_CASE-${PORTFOLIO_NAME}.txt"
  export GET_QUOTES_CMD="python $HOME/git/enterprise-solutions/googlecloud/ml-invest-advisory/local_llm/generate-llm-prompt.py \
    --portfolio_file=$file \
    --llm_prompt_template=$LLM_PROMPT_TEMPLATE \
    --output_prompt=$OUTPUT_PROMPT_FILE"

  $GET_QUOTES_CMD

  # replace the {{FLASH_INSIGHTS}} keyword with breaking news such as Mark Newton's flash insights
  sed -i "s/{{FLASH_INSIGHTS}}/$(cat "$NEWS_FILE")/g" "$OUTPUT_PROMPT_FILE"

  MD_OUTPUT_FILE="${PORTFOLIO_DIR}/$USE_CASE-${PORTFOLIO_NAME}.md"
  ollama run gemma3 --verbose < "$OUTPUT_PROMPT_FILE" | tee "$MD_OUTPUT_FILE"

  # Convert markdown to HTML if pandoc is available
  if [ "$PANDOC_EXISTS" = true ]; then
    HTML5_OUTPUT_FILE="${PORTFOLIO_DIR}/$USE_CASE-${PORTFOLIO_NAME}.html"
    echo -e "\n--- Generating HTML report using pandoc at $HTML5_OUTPUT_FILE ---"
    DATETIME_NOW="Breaking News Impact Report for $PORTFOLIO_NAME at $(date +"%Y-%m-%d %H:%M:%S %Z")"
    pandoc -s -f gfm -t html5 -o "$HTML5_OUTPUT_FILE" "$MD_OUTPUT_FILE" \
    --metadata title="$DATETIME_NOW" --include-in-header <(echo '<style>body { max-width: 80%; margin: 0 auto; } p, li, td, th { line-height: 1.5; }</style>')
  fi
done
