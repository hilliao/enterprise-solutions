# executors/

Scripts that generate portfolio/market reports with a local Ollama LLM and (in
some cases) upload the results to GCS. Most scripts assume the ml-invest-advisory
local_llm layout (portfolio JSON files, prompt templates, `generate-llm-prompt.py`).

## Scripts

### gen-daily-portfolio-reports.sh
Generates the daily portfolio analysis report. For every `*.json` file in
`PORTFOLIO_DIR`, builds an LLM prompt via `generate-llm-prompt.py` (optionally
inlining a `market-commentary_YYYY-MM-DD.txt` file), runs it through
`ollama run gemma3:12b`, and writes a Markdown report (plus an HTML version if
`pandoc` is installed).
Key env vars: `PORTFOLIO_DIR`, `LLM_PROMPT_TEMPLATE`, `USE_CASE`,
`MARKET_COMMENTARY_FILE`, `STOCK_QUOTES_CLOUD_RUN_URL`.

### gen-flash-insights-portfolio-reports.sh
Same pipeline as `gen-daily-portfolio-reports.sh`, but generates a "flash
insights" / breaking-news impact report per portfolio, injecting a
`news_YYYY-MM-DD.txt` file (produced by `gen-fundstrat-insights.sh` or
`gen-news-aggregate.sh`) in place of `{{FLASH_INSIGHTS}}`. Exits with an error
if the news file is missing.
Key env vars: `PORTFOLIO_DIR`, `LLM_PROMPT_TEMPLATE`, `USE_CASE`, `NEWS_FILE`.

### gen-fundstrat-insights.sh
Fetches membership content from fundstratdirect.com via headless Chrome
(reusing a pre-authenticated Chrome profile — see the script header for
one-time setup) and, for Flash Insights, summarizes it with Ollama.
```
./gen-fundstrat-insights.sh --flash-insights [LINES]        # dump + summarize once
./gen-fundstrat-insights.sh --technical-strategy            # dump latest article once
./gen-fundstrat-insights.sh --crypto-comment                # dump latest article once
./gen-fundstrat-insights.sh --poll [MINUTES] [LINES]         # poll during market hours (default 20 min)
./gen-fundstrat-insights.sh -h|--help
```
Requires `google-chrome`, `html2text`, `ollama`. Writes to `~/Documents/` and
mirrors the Flash Insights overview to `PORTFOLIO_DIR/news_YYYY-MM-DD.txt`
(also scp'd to a remote host).

### gen-news-aggregate.sh
PoC news aggregator: fetches one or more news pages via headless Chrome
(built-in registry: `wsj`, `cnbc`, or any ad-hoc `--url`) and summarizes each
with Ollama.
```
./gen-news-aggregate.sh                                   # all registered sites
./gen-news-aggregate.sh --site wsj|cnbc|all
./gen-news-aggregate.sh --url <URL> --name <label> [--lines N]
./gen-news-aggregate.sh --list
./gen-news-aggregate.sh -h|--help
```
Requires `google-chrome`, `html2text`, `ollama` (optionally `pandoc`). Writes
to `~/Documents/news-aggregate/`.

### gen-investment-report-realtime-nonstop.sh / ryzen7-7700x_gen-investment-report-realtime.sh
Loop that runs the daily + flash-insights portfolio scripts and uploads the
resulting HTML reports to a GCS bucket, repeatedly, during this script's
execution window (Mon-Fri, 08:00-18:00 America/New_York, excluding configured
holidays — intentionally ~1.5h before the actual 09:30-16:00 ET market
session and a few hours after it, to also catch pre-market/after-hours
activity). The two files are identical except for the paths/GCS
bucket/config baked into their `CONFIGURATION` section (`ryzen7-7700x_...` is
tailored to that machine; `gen-investment-report-realtime-nonstop.sh` is the
generic/template version).
```
./gen-investment-report-realtime-nonstop.sh [--immediate] [--active-sleep SEC] [--idle-sleep SEC] [-h|--help]
```
- `--immediate`: run once now, ignoring the window, then exit.
- `--active-sleep`: seconds between runs while inside the window (default 30).
- `--idle-sleep`: seconds between recheck cycles while outside the window
  (default 60); while idle, prints a live single-line countdown to the next
  execution-window start.

If the command fails, the loop prints an `ERROR` to stderr and exits with the
command's exit code, instead of repeating the failing step every
`--active-sleep` seconds. `generate-llm-prompt.py` retries a failed stock
quotes Cloud Run request with exponential backoff (1, 2, 4, 8, 16 seconds),
printing each failure's status code and response body (e.g. the 500 with
TradeStation's 403 in `detail`) to stderr, then exits with code 69. The
flash-insights step stays optional (`|| true` in `PORTFOLIO_SCRIPT`), so its
failures don't abort the loop.

Before running, edit the `CONFIGURATION` section for
`GOOGLE_APPLICATION_CREDENTIALS`, the portfolio script paths, `PORTFOLIO_DIR`,
and the GCS bucket/`gcloud` configuration.
