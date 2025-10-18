#!/bin/bash
set -e # exit the script when execution hits any error
set -x # print the executing lines

export PORTFOLIO_DIR="$HOME/git/enterprise-solutions/googlecloud/ml-invest-advisory/local_llm/test-portfolios"
export PORTFOLIO_FILES=$(find "$PORTFOLIO_DIR" -maxdepth 1 -type f -name "*.json")

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

  $GET_QUOTES_CMD && \
  ollama run llama3.1 --verbose < $PORTFOLIO_DIR/llm_prompt-${PORTFOLIO_NAME}.txt \
  | tee ${PORTFOLIO_DIR}/realtime_analysis-${PORTFOLIO_NAME}.md
done
