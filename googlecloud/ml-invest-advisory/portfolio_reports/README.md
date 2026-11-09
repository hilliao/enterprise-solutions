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
Each portfolio should be a `.json` file in the `PORTFOLIO_DIR`. Prefix Taiwan stocks with `TW:`:
```json
{
  "NVDA": { "shares": 117.0 },
  "GOOG": { "shares": 90.0 },
  "TW:2330": { "shares": 1000.0 }
}
```
US tickers are quoted by `get-us-ticker-quotes` (`STOCK_QUOTES_CLOUD_RUN_URL`) and `TW:` tickers by
`get-tw-ticker-quotes` (`TW_STOCK_QUOTES_CLOUD_RUN_URL`); see [market_symbol_quotes](../market_symbol_quotes). The
service account in `GOOGLE_APPLICATION_CREDENTIALS` needs `roles/run.invoker` on both functions.

Taiwan prices are in TWD and are converted to USD with the day's exchange rate from
[ExchangeRate-API](https://www.exchangerate-api.com) (Rates By Exchange Rate API: free, no API key, updated once a day),
so the prompt's values, totals and weights are all in USD. The current rate converts both the price and the previous
close, so a Taiwan holding's daily change leaves out the exchange rate's own move.

### Ticker Names
`build_portfolio_prompt.py` gives every holding a `"Name"` in the prompt. Names come from `ticker_names.json`
(or the file passed with `--ticker_names_file`) first, then from SEC EDGAR. SEC EDGAR names ETFs by the trust that
issues them, e.g. `iSHARES TRUST` for IVV, SOXX and IGV alike, so the LLM can't tell what an ETF holds. Add every ETF
you hold to `ticker_names.json`, with what it holds in parentheses:
```json
{
  "EWT": "iShares MSCI Taiwan ETF (Taiwanese stocks)",
  "SOXX": "iShares Semiconductor ETF (US-listed semiconductor stocks)"
}
```
A missing or invalid file only prints a warning; the SEC EDGAR names are used instead.

## Executors

The `scripts/` directory contains different scripts tailored for specific reporting needs:

### 1. Daily Portfolio Reports
**Script**: `scripts/report-daily.sh`

Generates a comprehensive daily analysis. It searches for all `.json` portfolios in `PORTFOLIO_DIR`, incorporates market commentary from `MARKET_COMMENTARY_FILE` (if provided), and saves both `.md` and `.html` reports.

### 2. Flash Insights reports
**Script**: `scripts/report-news-impact.sh`

Designed for rapid analysis of breaking news. It uses a specific "flash insights" template and injects each of today's news files from `scripts/fetch-news.sh` to analyze how current events might impact your specific holdings, producing one report per portfolio and news site (e.g. `flash-insights-yang-cnbc-llm-generated.html`).

### 3. Realtime Continuous Monitoring
**Script**: `scripts/run-market-hours.sh`

A continuous monitoring loop that executes during market hours (08:00 - 18:00 ET, Mon-Fri). It runs the daily and flash insights report generators at a specified interval and uploads the HTML reports to a Google Cloud Storage (GCS) bucket for remote access. Set `PYTHON_VENV` in its `CONFIGURATION` section to the virtual environment above; the script activates it, so `source py-venv/bin/activate` isn't needed first.

## Usage

To generate reports, simply execute the desired script from the root of the project:

```bash
./scripts/report-daily.sh
```

The reports will be saved in your `PORTFOLIO_DIR` with filenames prefixing the use-case: the LLM's input prompt (e.g. `daily-report-my_portfolio-llm-prompt.txt`) and the generated report (e.g. `daily-report-my_portfolio-llm-generated.md` and `.html`).

## Tests

[test_build_portfolio_prompt.py](test_build_portfolio_prompt.py) unit-tests [build_portfolio_prompt.py](build_portfolio_prompt.py)
with the stock quotes Cloud Run service, Google ID tokens and SEC EDGAR mocked, so it needs no credentials or network:

```bash
pip install -r requirements.txt pytest
python -m pytest -v test_build_portfolio_prompt.py
```
