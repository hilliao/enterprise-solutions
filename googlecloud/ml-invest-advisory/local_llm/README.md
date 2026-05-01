# Real-time Investment Portfolio Analysis

This system provides a suite of tools to generate real-time investment portfolio analysis reports using local Large Language Models (LLMs) via Ollama. It automates the fetching of market data, prompt construction, and report generation for one or more portfolios.

## Overview

The system uses specialized scripts in the `executors/` directory to perform the following core operations:

1.  **Fetch Real-time Quotes**: Uses `generate-llm-prompt.py` to get current market data for securities in a portfolio file via a Google Cloud Function endpoint.
2.  **Prompt Construction**: Injects real-time data and external context (like news or market commentary) into predefined templates.
3.  **Local LLM Inference**: Pipes the generated prompt to a local LLM running on Ollama.
4.  **Reporting**: Saves the analysis as Markdown (`.md`) and optionally converts it to HTML using `pandoc`.

## Prerequisites

Ensure you have the following installed and configured:

*   **Ollama**: Installed and running with a model pulled (e.g., `gemma3:12b`).
*   **Python 3**: Recommended to use a virtual environment.
    ```bash
    python3 -m venv py-venv
    source py-venv/bin/activate
    pip install -r requirements.txt
    ```
*   **Google Cloud SDK (`gcloud`)**: Authenticated to access the Cloud Function.
*   **Pandoc** (Optional): Used for generating HTML versions of reports.

## Configuration

Set the following environment variables to customize the behavior:

*   `PORTFOLIO_DIR`: Directory containing your portfolio `.json` files.
*   `GOOGLE_APPLICATION_CREDENTIALS`: Path to your Google Cloud service account key.
*   `MARKET_COMMENTARY_FILE`: (For daily reports) Path to a text file containing market commentary.
*   `NEWS_FILE`: (For flash insights) Path to a text file containing breaking news/insights.

### Portfolio Format
Each portfolio should be a `.json` file in the `PORTFOLIO_DIR`:
```json
{
  "NVDA": { "shares": 117.0 },
  "GOOG": { "shares": 90.0 }
}
```

## Executors

The `executors/` directory contains different scripts tailored for specific reporting needs:

### 1. Daily Portfolio Reports
**Script**: `executors/gen-daily-portfolio-reports.sh`

Generates a comprehensive daily analysis. It searches for all `.json` portfolios in `PORTFOLIO_DIR`, incorporates market commentary from `MARKET_COMMENTARY_FILE` (if provided), and saves both `.md` and `.html` reports.

### 2. Flash Insights reports
**Script**: `executors/gen-flash-insights-portfolio-reports.sh`

Designed for rapid analysis of breaking news. It uses a specific "flash insights" template and injects content from `NEWS_FILE` to analyze how current events might impact your specific holdings.

### 3. Realtime Continuous Monitoring
**Script**: `executors/gen-investment-report-realtime-nonstop.sh`

A continuous monitoring loop that executes during market hours (08:00 - 18:00 ET, Mon-Fri). It runs the daily report generator at a specified interval and can be configured to upload output files to a Google Cloud Storage (GCS) bucket for remote access.

## Usage

To generate reports, simply execute the desired script from the root of the project:

```bash
./executors/gen-daily-portfolio-reports.sh
```

The reports will be saved in your `PORTFOLIO_DIR` with filenames prefixing the use-case (e.g., `daily-report-my_portfolio.md`).