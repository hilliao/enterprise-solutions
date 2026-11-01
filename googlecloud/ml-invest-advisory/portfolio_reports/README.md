# Real-time Investment Portfolio Analysis

This system provides a suite of tools to generate real-time investment portfolio analysis reports using local Large Language Models (LLMs) via Ollama. It automates the fetching of market data, prompt construction, and report generation for one or more portfolios.

## Overview

The system uses specialized scripts in the `scripts/` directory to perform the following core operations:

1.  **Fetch Real-time Quotes**: Uses `build_portfolio_prompt.py` to get current market data for securities in a portfolio file via a Google Cloud Function endpoint.
2.  **Prompt Construction**: Injects real-time data and external context (like news or market commentary) into predefined templates.
3.  **Local LLM Inference**: Pipes the generated prompt to a local LLM running on Ollama.
4.  **Reporting**: Saves the analysis as Markdown (`.md`) and optionally converts it to HTML using `pandoc`.

## Prerequisites

Ensure you have the following installed and configured:

*   **Ollama**: Installed and running with a model pulled (e.g., `gemma4:12b-it-qat`).
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
*   `NEWS_FILES`: (For flash insights) Comma-separated news files; defaults to every `news-<SITE>_YYYY-MM-DD.txt` for today in `PORTFOLIO_DIR`, written by `scripts/fetch-news.sh --site <SITE>`.
*   `OLLAMA_MODEL`: Ollama model used for the reports (default `gemma4:12b-it-qat`). Use `scripts/compare-models.sh` to compare candidate models on the same prompt.

### Portfolio Format
Each portfolio should be a `.json` file in the `PORTFOLIO_DIR`:
```json
{
  "NVDA": { "shares": 117.0 },
  "GOOG": { "shares": 90.0 }
}
```

## Executors

The `scripts/` directory contains different scripts tailored for specific reporting needs:

### 1. Daily Portfolio Reports
**Script**: `scripts/report-daily.sh`

Generates a comprehensive daily analysis. It searches for all `.json` portfolios in `PORTFOLIO_DIR`, incorporates market commentary from `MARKET_COMMENTARY_FILE` (if provided), and saves both `.md` and `.html` reports.

### 2. Flash Insights reports
**Script**: `scripts/report-news-impact.sh`

Designed for rapid analysis of breaking news. It uses a specific "flash insights" template and injects each of today's news files from `scripts/fetch-news.sh` to analyze how current events might impact your specific holdings, producing one report per portfolio and news site (e.g. `flash-insights-yang-cnbc.html`).

### 3. Realtime Continuous Monitoring
**Script**: `scripts/run-market-hours.sh`

A continuous monitoring loop that executes during market hours (08:00 - 18:00 ET, Mon-Fri). It runs the daily and flash insights report generators at a specified interval and uploads the HTML reports to a Google Cloud Storage (GCS) bucket for remote access. Set `PYTHON_VENV` in its `CONFIGURATION` section to the virtual environment above; the script activates it, so `source py-venv/bin/activate` isn't needed first.

## Usage

To generate reports, simply execute the desired script from the root of the project:

```bash
./scripts/report-daily.sh
```

The reports will be saved in your `PORTFOLIO_DIR` with filenames prefixing the use-case (e.g., `daily-report-my_portfolio.md`).