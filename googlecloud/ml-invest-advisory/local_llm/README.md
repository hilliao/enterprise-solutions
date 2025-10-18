# Real-time Investment Portfolio Analysis

This document provides an overview and instructions on how to execute the `analyze-portfolio.sh` script to generate real-time investment portfolio analysis using a local Large Language Model (LLM) with Ollama.

## Overview

The `analyze-portfolio.sh` script automates the process of generating detailed financial analysis for one or more investment portfolios. For each portfolio, it performs the following steps:

1.  **Fetches Real-time Quotes**: It calls a Python script (`generate-llm-prompt.py`) that takes a portfolio holdings file, fetches the latest market data for each holding from a Google Cloud Function endpoint, and calculates daily performance metrics.
2.  **Generates an LLM Prompt**: The Python script then injects this real-time data into a prompt template to create a detailed, context-rich prompt for the LLM.
3.  **Runs Local LLM Analysis**: The main script pipes the generated prompt to a local LLM (e.g., `llama3.1`) running via Ollama.
4.  **Saves the Analysis**: The LLM's output, which is a comprehensive portfolio analysis report, is saved as a Markdown file.

This process allows for dynamic, up-to-date analysis of multiple portfolios with a single command.

## Prerequisites

Before running the script, ensure you have the following installed and configured:

*   **Bash Shell**: A standard Unix-like shell environment.
*   **Ollama**: The Ollama service must be installed and running with the desired model (e.g., `llama3.1`) pulled. You can find installation instructions on the Ollama website.
*   **Python 3 & Dependencies**: It is highly recommended to use a Python virtual environment.

    ```bash
    # Create and activate a virtual environment
    python3 -m venv py-venv
    source py-venv/bin/activate
    # Install required packages
    pip install -r requirements.txt
    ```
*   **Google Cloud SDK (`gcloud`)**: Authenticated to your Google Cloud account.

## Configuration

You must configure several environment variables and files for the script to function correctly.

### 1. Portfolio Holdings (`PORTFOLIO_DIR`)

The script looks for portfolio files in a directory specified by the `PORTFOLIO_DIR` environment variable.

*   **Action**: In `analyze-portfolio.sh`, set `PORTFOLIO_DIR` to the absolute path of the directory containing your portfolio `.json` files.

    ```bash
    export PORTFOLIO_DIR="$HOME/git/enterprise-solutions/googlecloud/ml-invest-advisory/local_llm/test-portfolios"
    ```

*   **Format**: Each portfolio must be a JSON file where keys are stock tickers and values are objects containing the number of `shares`.

    **Example (`portfolio_holdings.json`):**
    ```json
    {
      "NVDA": {
        "shares": 117.0
      },
      "GOOG": {
        "shares": 90.0
      },
      "BRK.B": {
        "shares": 103.0
      }
    }
    ```

### 2. LLM Prompt Template (`--llm_prompt_template`)

The `generate-llm-prompt.py` script uses a template file to construct the final prompt for the LLM. A placeholder in the template is replaced with the real-time portfolio data.

*   **Action**: Ensure the path to your prompt template is correctly set in the `GET_QUOTES_CMD` variable within `analyze-portfolio.sh`.

*   **Placeholder**: The template file must contain the `{{PORTFOLIO_HOLDING_DATA_JSON}}` placeholder. This will be replaced by the JSON block of real-time quote data at runtime.

    **Example (`prompt_template.txt`):**
    ```
    [SYSTEM]
    Act as a senior portfolio analyst...

    [INSTRUCTIONS]
    Generate a report with the following exact structure and headers:

    **Portfolio performance**
    ...
    ```json
    {{PORTFOLIO_HOLDING_DATA_JSON}}
    ```

    **AI Daily Briefing**
    ...

    **Daily Performance Breakdown**
    ...

    **Volatility & Impact Analysis**
    ...
    ```

### 3. Google Cloud Authentication (`GOOGLE_APPLICATION_CREDENTIALS`)

To fetch real-time quotes, the Python script needs to authenticate with Google Cloud to invoke the secure Cloud Function.

*   **Action**: Set the `GOOGLE_APPLICATION_CREDENTIALS` environment variable to the path of your Google Cloud service account key file. This service account must have the **Cloud Run Invoker** IAM role granted on the project or the specific Cloud Function.

    ```bash
    export GOOGLE_APPLICATION_CREDENTIALS="/path/to/your/service-account-key.json"
    ```

## How to Run

1.  Ensure your Ollama service is running.
2.  Set the `GOOGLE_APPLICATION_CREDENTIALS` environment variable as described above.
3.  Execute the script from your terminal:

    ```bash
    ./analyze-portfolio.sh
    ```

The script will find all `.json` files in the `PORTFOLIO_DIR`, generate a prompt for each, and create a corresponding analysis report (e.g., `realtime_analysis-my_portfolio.md`) in the same directory.