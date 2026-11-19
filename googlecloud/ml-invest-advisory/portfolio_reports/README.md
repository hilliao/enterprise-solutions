# Real-time Investment Portfolio Analysis

This system provides a suite of tools to generate real-time investment portfolio analysis reports using local Large Language Models (LLMs) via Ollama. It automates the fetching of market data, prompt construction, and report generation for one or more portfolios.

It is one part of [ml-invest-advisory](../README.md), whose README shows the whole data flow:
- **Upstream:** the quote functions in [market_symbol_quotes](../market_symbol_quotes) provide the quotes, and
  `ollama_report_pipeline/fetch-news.sh` provides the news files.
- **Downstream:** the HTML reports are uploaded to Cloud Storage, and [report_viewer](../report_viewer) shows them.

## Overview

The system uses specialized scripts in the `ollama_report_pipeline/` directory to perform the following core operations:

1.  **Fetch News**: `fetch-news.sh` summarizes news sites and Fundstrat research into `PORTFOLIO_DIR/news-<SITE>_YYYY-MM-DD.txt` files. It runs separately, usually with `--poll`.
2.  **Fetch Real-time Quotes**: `build_portfolio_prompt.py` gets current quotes for the securities in a portfolio file from the `get-us-ticker-quotes` and `get-tw-ticker-quotes` Cloud Functions.
3.  **Prompt Construction**: Injects the real-time data and external context (news or market commentary) into the templates in `prompt_templates/`.
4.  **Local LLM Inference**: Pipes the generated prompt to a local LLM running on Ollama.
5.  **Reporting**: Saves the analysis as Markdown (`.md`) and converts it to HTML with `pandoc`, if installed.
6.  **Upload**: `run-market-hours.sh` has `upload-report.sh` copy each HTML report to `GCS_BUCKET<portfolio>/` as soon as it is written.

## Files

| File | Purpose |
|---|---|
| [build_portfolio_prompt.py](build_portfolio_prompt.py) | Portfolio JSON + live quotes + ticker names → the LLM prompt (`{{PORTFOLIO_HOLDING_DATA_JSON}}`). Called by `report-common.sh`. |
| [prompt_templates/daily_report_prompt_template.txt](prompt_templates/daily_report_prompt_template.txt) | Daily report prompt; `{{MARKET_COMMENTARY}}` is filled with the Fundstrat daily technical strategy. |
| [prompt_templates/news-report-template.txt](prompt_templates/news-report-template.txt) | News report prompt; `{{NEWS_CONTENT}}` is filled with one news file. |
| [ticker_names.json](ticker_names.json) | Ticker names that override SEC EDGAR, mainly for ETFs (see [Ticker Names](#ticker-names)). |
| [portfolio_holdings.json](portfolio_holdings.json) | Sample portfolio in the [portfolio format](#portfolio-format); real portfolios live in `PORTFOLIO_DIR`, outside the repo. |
| [requirements.txt](requirements.txt) | Python dependencies of `build_portfolio_prompt.py` (`google-auth`, `requests`). |
| [test_build_portfolio_prompt.py](test_build_portfolio_prompt.py) | Unit tests, see [Tests](#tests). |
| [ollama_report_pipeline/](ollama_report_pipeline) | The shell scripts that run everything; see its [README](ollama_report_pipeline/README.md). |
| `sec_*.json` | SEC EDGAR caches written next to the script (refreshed after 24 hours); git-ignored. |

## Prerequisites

Ensure you have the following installed and configured:

*   **Ollama**: Installed and running with a model pulled (e.g., `gemma4:12b-it-qat`).
*   **Python 3**: Recommended to use a virtual environment.
    ```bash
    python3 -m venv py-venv
    source py-venv/bin/activate
    pip install -r requirements.txt
    ```
*   **A service account key** (`GOOGLE_APPLICATION_CREDENTIALS`) with `roles/run.invoker` on both quote functions. `build_portfolio_prompt.py` uses it to get the ID token for the quote calls.
*   **Google Cloud SDK (`gcloud`)**: only for the upload, with a configuration (`GCLOUD_CONFIG` in `run-market-hours.sh`) that can write to the bucket.
*   **Pandoc** (Optional): Used for generating HTML versions of reports.

## Configuration

Set the following environment variables to customize the behavior:

*   `PORTFOLIO_DIR`: Directory containing your portfolio `.json` files. The reports, prompts and news files are written there too. The scripts' default, `portfolio_reports/test-portfolios`, isn't in the repository, so set it.
*   `GOOGLE_APPLICATION_CREDENTIALS`: Path to your Google Cloud service account key.
*   `STOCK_QUOTES_CLOUD_RUN_URL` and `TW_STOCK_QUOTES_CLOUD_RUN_URL`: URLs of the `get-us-ticker-quotes` and `get-tw-ticker-quotes` functions. The TW URL is needed only for portfolios with `TW:` tickers.
*   `LLM_PROMPT_TEMPLATE`: Prompt template; the default is the one in `prompt_templates/` for each script.
*   `SEC_USER_AGENT`: (Optional) Name and contact email that SEC EDGAR requires in the User-Agent.
*   `MARKET_COMMENTARY_FILE`: (For daily reports) Path to the text file with the Fundstrat daily technical strategy (this feeds the prompt's market commentary section); defaults to `$PORTFOLIO_DIR/news-fundstrat-daily-technical_YYYY-MM-DD.txt` for today.
*   `NEWS_FILES`: (For news reports) Comma-separated news files; defaults to every `news-<SITE>_YYYY-MM-DD.txt` for today in `PORTFOLIO_DIR`, written by `ollama_report_pipeline/fetch-news.sh --site <SITE>`.
*   `OLLAMA_MODEL`: Ollama model used for the reports (default `gemma4:12b-it-qat`).

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

The `ollama_report_pipeline/` directory contains different scripts tailored for specific reporting needs:

### 1. Daily Portfolio Reports
**Script**: `ollama_report_pipeline/report-daily.sh`

Generates a comprehensive daily analysis. It searches for all `.json` portfolios in `PORTFOLIO_DIR`, incorporates the Fundstrat daily technical strategy from `MARKET_COMMENTARY_FILE` (default `news-fundstrat-daily-technical_YYYY-MM-DD.txt`, if present), and saves both `.md` and `.html` reports.

### 2. News reports
**Script**: `ollama_report_pipeline/report-news-impact.sh`

Designed for rapid analysis of financial market news. It uses the `prompt_templates/news-report-template.txt` template and injects each of today's news files from `ollama_report_pipeline/fetch-news.sh` in place of its `{{NEWS_CONTENT}}` placeholder to analyze how current events might impact your specific holdings, producing one report per news site and portfolio named `news-<site>-<portfolio>-llm-generated.html` (e.g. `news-cnbc-yang-llm-generated.html`).

### 3. Realtime Continuous Monitoring
**Script**: `ollama_report_pipeline/run-market-hours.sh`

A continuous monitoring loop that executes during market hours (08:00 - 18:00 ET, Mon-Fri). It runs the daily and news report generators at a specified interval, and each HTML report is uploaded to a Google Cloud Storage (GCS) bucket for remote access as soon as it is written (`ollama_report_pipeline/upload-report.sh`), in one folder per portfolio (e.g. `gs://bucket/reports/yang/news-cnbc-yang-llm-generated.html`). Set `PYTHON_VENV` in its `CONFIGURATION` section to the virtual environment above; the script activates it, so `source py-venv/bin/activate` isn't needed first.

## Usage

The scripts find their templates and `build_portfolio_prompt.py` relative to their own folder, so they can run from any directory. From this folder:

```bash
PORTFOLIO_DIR=~/workspace/portfolios ./ollama_report_pipeline/report-daily.sh
```

The reports will be saved in your `PORTFOLIO_DIR` with filenames prefixing the use-case: the LLM's input prompt (e.g. `daily-report-my_portfolio-llm-prompt.txt`) and the generated report (e.g. `daily-report-my_portfolio-llm-generated.md` and `.html`).

The report file names are a contract: `upload-report.sh` reads the portfolio from them, and the Report Viewer's tab labels come from them (`report_viewer/report_catalog.py`). Keep the `daily-report-<portfolio>-llm-generated.html` and `news-<site>-<portfolio>-llm-generated.html` forms.

## Tests

[test_build_portfolio_prompt.py](test_build_portfolio_prompt.py) unit-tests [build_portfolio_prompt.py](build_portfolio_prompt.py)
with the stock quotes Cloud Run service, Google ID tokens and SEC EDGAR mocked, so it needs no credentials or network:

```bash
pip install -r requirements.txt pytest
python -m pytest -v test_build_portfolio_prompt.py
```

The pipeline's tests are in [ollama_report_pipeline/README.md](ollama_report_pipeline/README.md).
