# ml-invest-advisory

An AI-assisted investment advisory pipeline: real-time quotes and financial market news go into a local Ollama LLM,
which writes one HTML report per portfolio and news source. The reports are uploaded to Cloud Storage and read in a
browser through the Report Viewer.

Start here, then read the README of the folder you work on. Each folder README lists its files, settings and tests.

## Components

| Folder | What it is | Runs on | README |
|---|---|---|---|
| [market_symbol_quotes/](market_symbol_quotes) | Two Cloud Functions (gen2): `get-us-ticker-quotes` (Alpaca) and `get-tw-ticker-quotes` (SinoTrade Shioaji) | Google Cloud | [README](market_symbol_quotes/README.md) |
| [portfolio_reports/](portfolio_reports) | `build_portfolio_prompt.py` (portfolio + quotes → LLM prompt), the prompt templates and ticker names | the report machine | [README](portfolio_reports/README.md) |
| [portfolio_reports/ollama_report_pipeline/](portfolio_reports/ollama_report_pipeline) | Shell pipeline: fetch and summarize news, generate reports with Ollama, upload them | the report machine(s) | [README](portfolio_reports/ollama_report_pipeline/README.md) |
| [report_viewer/](report_viewer) | Web UI with Google sign-in that shows the uploaded reports in tabs; also a Docker image | a server behind a TLS proxy, or localhost | [README](report_viewer/README.md) |

## Data flow

```
                 headless Chrome                    Ollama
news sites ──► fetch-news.sh --site <KEY> ──────────────────► PORTFOLIO_DIR/news-<KEY>_YYYY-MM-DD.txt
(WSJ, CNBC,      (ollama_report_pipeline/)                    (also copied to REMOTE_HOST's PORTFOLIO_DIR)
 Fundstrat, ...)                                                        │
                                                                        ▼
PORTFOLIO_DIR/<portfolio>.json ──► build_portfolio_prompt.py ◄── market_symbol_quotes Cloud Functions
                                   (prompt with live values)      (STOCK_QUOTES_CLOUD_RUN_URL, TW_STOCK_QUOTES_CLOUD_RUN_URL)
                                            │
                                            ▼
                   report-daily.sh, report-news-impact.sh ──► ollama run ──► pandoc ──► *-llm-generated.html
                   (run in a loop by run-market-hours.sh)                                       │
                                                                                upload-report.sh (gcloud storage cp)
                                                                                                ▼
                                          gs://<bucket>/<prefix><portfolio>/<report>.html
                                                                                                │
                                                     report_viewer.py (the visitor's own Google token)
                                                                                                ▼
                                                                                   browser, one tab per report
```

## Contracts between the folders

Changing one side of these breaks the other side; update both.

| Contract | Producer | Consumer |
|---|---|---|
| Quote JSON (`price`, `previous-close`, `currency`, ...) | `market_symbol_quotes/main.py` | `portfolio_reports/build_portfolio_prompt.py` |
| Quote URLs and caller identity: the service account in `GOOGLE_APPLICATION_CREDENTIALS` needs `roles/run.invoker` on both functions | `market_symbol_quotes/deploy.sh` | `STOCK_QUOTES_CLOUD_RUN_URL`, `TW_STOCK_QUOTES_CLOUD_RUN_URL` in `run-market-hours.sh` |
| News files `PORTFOLIO_DIR/news-<KEY>_YYYY-MM-DD.txt`; `news-fundstrat-daily-technical_*` also feeds the daily report | `fetch-news.sh` | `report-news-impact.sh`, `report-daily.sh` |
| Placeholders `{{PORTFOLIO_HOLDING_DATA_JSON}}`, `{{MARKET_COMMENTARY}}`, `{{NEWS_CONTENT}}` | `prompt_templates/*.txt` | `build_portfolio_prompt.py`, `report-daily.sh`, `report-news-impact.sh` |
| Report names `daily-report-<portfolio>-llm-generated.html`, `news-<KEY>-<portfolio>-llm-generated.html` | `report-daily.sh`, `report-news-impact.sh` | `upload-report.sh` (finds the portfolio), `report_viewer/report_catalog.py` (tab labels) |
| Bucket layout `<prefix><portfolio>/<report>.html`. The pipeline's `GCS_BUCKET` (a `gs://bucket/prefix/` URL) must equal the viewer's `gs://$GCS_BUCKET/$GCS_PREFIX` | `run-market-hours.sh` `CONFIGURATION`, `upload-report.sh` | `report_viewer` `GCS_BUCKET`, `GCS_PREFIX` |
| Write access: the `GCLOUD_CONFIG` account in `run-market-hours.sh` needs write access to the bucket | `run-market-hours.sh` | Cloud Storage IAM |
| Read access: each viewer user's Google account needs `roles/storage.objectViewer` on the bucket | Cloud Storage IAM | `report_viewer` (reads with the visitor's token) |
| Report HTML style, including the dark theme (`HTML_REPORT_STYLE`) | `report-common.sh` | the reports shown in the viewer |
| News site keys (`wsj`, `cnbc`, `fundstrat-*`, `aggregate`) | `SITE_KEYS` in `fetch-news.sh` | `SITE_LABELS` in `report_catalog.py`, for special capitalization only |

## Getting the whole system running

1. Deploy the quote functions: [market_symbol_quotes/README.md](market_symbol_quotes/README.md#deploy).
2. Set up the Python environment and portfolios: [portfolio_reports/README.md](portfolio_reports/README.md#prerequisites).
3. Run Ollama with `OLLAMA_CONTEXT_LENGTH=16384`, and pull the model (default `gemma4:12b-it-qat`).
4. Start the news fetcher, e.g. `fetch-news.sh --site all --poll`, on a machine with Chrome and the Fundstrat
   profile: [ollama_report_pipeline/README.md](portfolio_reports/ollama_report_pipeline/README.md#fetch-newssh).
5. Copy `run-market-hours.sh`, fill in its `CONFIGURATION` section (quote URLs, `PORTFOLIO_DIR`, `GCS_BUCKET`,
   `GCLOUD_CONFIG`), and run it: [ollama_report_pipeline/README.md](portfolio_reports/ollama_report_pipeline/README.md#run-market-hourssh).
6. Run the viewer with the same bucket and prefix: [report_viewer/README.md](report_viewer/README.md#setup).

## Tests

| Folder | Command |
|---|---|
| `market_symbol_quotes/` | `python -m pytest -v` |
| `portfolio_reports/` | `python -m pytest -v test_build_portfolio_prompt.py` |
| `portfolio_reports/ollama_report_pipeline/` | `python -m pytest -v test_extract_fundstrat_posts.py` (the shell scripts have no tests; check them with `bash -n`) |
| `report_viewer/` | `python3 -m unittest -v test_report_viewer.py` |

None of the tests need credentials or network access, except the live SinoTrade tests, which are skipped unless
configured.

## Not in the repository

These files are kept out of git on purpose; don't commit them:

- Portfolio files (`PORTFOLIO_DIR/*.json`), generated reports and news files.
- The OAuth client JSON for the viewer, service account keys, and the Chrome profile used for Fundstrat.
- `shioaji.log` (it can contain the Taiwan national ID) and the SEC EDGAR caches `portfolio_reports/sec_*.json`.
