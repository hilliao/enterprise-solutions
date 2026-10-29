# scripts/

Scripts that generate portfolio/market reports with a local Ollama LLM and (in
some cases) upload the results to GCS. Most scripts assume the ml-invest-advisory
portfolio_reports layout (portfolio JSON files, prompt templates, `build_portfolio_prompt.py`).

## Scripts

### report-daily.sh
Generates the daily portfolio analysis report. For every `*.json` file in
`PORTFOLIO_DIR`, builds an LLM prompt via `build_portfolio_prompt.py` (optionally
inlining a `market-commentary_YYYY-MM-DD.txt` file), runs it through
`ollama run $OLLAMA_MODEL` (default `gemma4:12b-it-qat`), and writes a Markdown report
(plus an HTML version if `pandoc` is installed).
Key env vars: `PORTFOLIO_DIR`, `LLM_PROMPT_TEMPLATE`, `USE_CASE`,
`MARKET_COMMENTARY_FILE`, `STOCK_QUOTES_CLOUD_RUN_URL`, `OLLAMA_MODEL`, `OLLAMA_TIMEOUT_SECONDS`
(default 600; kills a stuck `ollama run`, retries it once, then fails the script).

### report-news-impact.sh
Same pipeline as `report-daily.sh`, but generates a "flash
insights" / breaking-news impact report per portfolio, injecting a
`news_YYYY-MM-DD.txt` file (produced by `fetch-fundstrat.sh` or
`fetch-news.sh`) in place of `{{FLASH_INSIGHTS}}`. Exits with an error
if the news file is missing.
Key env vars: `PORTFOLIO_DIR`, `LLM_PROMPT_TEMPLATE`, `USE_CASE`, `NEWS_FILE`,
`OLLAMA_MODEL`, `OLLAMA_TIMEOUT_SECONDS`.

### compare-models.sh
Runs one prompt (e.g. a `daily-report-<portfolio>.txt` written by
`report-daily.sh`) through several Ollama models in turn, unloading each
before the next, and writes every report plus a timing summary (wall clock,
tokens/s, CPU/GPU split, context length) and a side-by-side `comparison.html`
to a new timestamped directory under `<prompt dir>/model-comparison/`.
```
./compare-models.sh PROMPT_FILE [MODEL ...]   # default: gemma4:12b-it-qat qwen3.5:9b-q8_0
```
Key env vars: `OUTPUT_DIR`, `OLLAMA_TIMEOUT_SECONDS` (default 1800), `OLLAMA_THINK`.

### fetch-fundstrat.sh
Fetches membership content from fundstratdirect.com via headless Chrome
(reusing a pre-authenticated Chrome profile — see the script header for
one-time setup) and, for Flash Insights, summarizes it with Ollama.
```
./fetch-fundstrat.sh --flash-insights [LINES]        # dump + summarize once
./fetch-fundstrat.sh --technical-strategy            # dump latest article once
./fetch-fundstrat.sh --crypto-comment                # dump latest article once
./fetch-fundstrat.sh --poll [MINUTES] [LINES]         # poll during market hours (default 20 min)
./fetch-fundstrat.sh -h|--help
```
Requires `google-chrome`, `html2text`, `ollama`. Writes to `~/Documents/` and
mirrors the Flash Insights overview to `PORTFOLIO_DIR/news_YYYY-MM-DD.txt`
(also scp'd to a remote host). Key env vars: `OLLAMA_HOST`, `OLLAMA_MODEL`
(default `gemma4:12b-it-qat`), `OLLAMA_THINK` (default `false`).

### fetch-news.sh
PoC news aggregator: fetches one or more news pages via headless Chrome
(built-in registry: `wsj`, `cnbc`, or any ad-hoc `--url`) and summarizes each
with Ollama.
```
./fetch-news.sh                                   # all registered sites
./fetch-news.sh --site wsj|cnbc|all
./fetch-news.sh --url <URL> --name <label> [--lines N]
./fetch-news.sh --list
./fetch-news.sh -h|--help
```
Requires `google-chrome`, `html2text`, `ollama` (optionally `pandoc`). Writes
to `~/Documents/news-aggregate/`.

### run-market-hours.sh
Loop that runs the daily + flash-insights portfolio scripts and uploads the
resulting HTML reports to a GCS bucket, repeatedly, during this script's
execution window (Mon-Fri, 08:00-18:00 America/New_York, excluding configured
holidays — intentionally ~1.5h before the actual 09:30-16:00 ET market
session and a few hours after it, to also catch pre-market/after-hours
activity). The paths, GCS bucket and gcloud config are set in its
`CONFIGURATION` section; the checked-in version is a generic template.
```
./run-market-hours.sh [--immediate] [--active-sleep SEC] [--idle-sleep SEC] [-h|--help]
```
- `--immediate`: run once now, ignoring the window, then exit.
- `--active-sleep`: seconds between runs while inside the window (default 30).
- `--idle-sleep`: seconds between recheck cycles while outside the window
  (default 60); while idle, prints a live single-line countdown to the next
  execution-window start.

If the command fails, the loop prints an `ERROR` to stderr and exits with the
command's exit code, instead of repeating the failing step every
`--active-sleep` seconds. `build_portfolio_prompt.py` retries a failed stock
quotes Cloud Run request with exponential backoff (1, 2, 4, 8, 16 seconds),
printing each failure's status code and response body (e.g. the 500 with
TradeStation's 403 in `detail`) to stderr, then exits with code 69. The
flash-insights step stays optional (`|| true` in `PORTFOLIO_SCRIPT`), so its
failures don't abort the loop.

Before running, edit the `CONFIGURATION` section for
`GOOGLE_APPLICATION_CREDENTIALS`, the portfolio script paths, `PORTFOLIO_DIR`,
and the GCS bucket/`gcloud` configuration.
