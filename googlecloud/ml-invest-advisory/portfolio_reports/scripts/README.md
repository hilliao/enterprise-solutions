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

### report-common.sh
Helper functions shared by `report-daily.sh` and `report-news-impact.sh`
(building the prompt with `build_portfolio_prompt.py`, `run_ollama` with its
timeout and retry, appending the input prompt to the report, and the pandoc
HTML conversion). Sourced by those scripts; not run on its own.

### report-news-impact.sh
Same pipeline as `report-daily.sh`, but generates a "flash
insights" / breaking-news impact report per portfolio and news site. It
reads every `PORTFOLIO_DIR/news-<SITE>_YYYY-MM-DD.txt` file for today
(produced by `fetch-news.sh --site <SITE>`, e.g. `news-fundstrat_2026-11-01.txt`,
`news-cnbc_2026-11-01.txt`, `news-wsj_2026-11-01.txt`) and prints which files
it found. For each portfolio it fetches quotes once, then writes one report per
news file, with that file in place of `{{FLASH_INSIGHTS}}`:
`$USE_CASE-<portfolio>-<SITE>.{txt,md,html}` (e.g.
`flash-insights-yang-cnbc.html`). Set `NEWS_FILES` to a comma-separated list
to use other files. Exits with an error if no news file is found.
Key env vars: `PORTFOLIO_DIR`, `LLM_PROMPT_TEMPLATE`, `USE_CASE`, `NEWS_FILES`,
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

### fetch-news.sh
News aggregator: fetches one news page via headless Chrome (a built-in site
`wsj`, `cnbc` or `fundstrat`, or any ad-hoc `--url`) and summarizes it with
Ollama. `--site fundstrat` fetches the fundstratdirect.com Flash Insights page
(reusing a pre-authenticated Chrome profile — see the script header for
one-time setup) and extracts the posts. Every `--site` run copies its summary
to `PORTFOLIO_DIR/news-<SITE>_YYYY-MM-DD.txt` (read by `report-news-impact.sh`)
and, with `scp -P $REMOTE_PORT`, to the same path on `--remote-host` (default
`hil@hil-fr-dc.freeddns.org`; `""` skips the copy). `--url` runs only write to
`OUTPUT_DIR`.
```
./fetch-news.sh --site wsj|cnbc|fundstrat
./fetch-news.sh --url <URL> --name <label> [--lines N]
./fetch-news.sh --site wsj --profile-dir DIR      # use another Chrome profile
./fetch-news.sh --site wsj --output-dir DIR       # write to DIR
./fetch-news.sh --site wsj --remote-host U@H       # copy news-wsj_YYYY-MM-DD.txt to another host
./fetch-news.sh --site wsj|cnbc|fundstrat --poll [MIN]  # repeat forever, sleeping MIN (default 30) after each cycle
./fetch-news.sh --list
./fetch-news.sh -h|--help
```
Requires `google-chrome`, `html2text`, `ollama` (optionally `pandoc`). Writes
to `OUTPUT_DIR` (default `~/Documents/news-aggregate/`). The site navigation before the first `*****`
heading (html2text `<h2>`) is skipped, and the next `--lines` lines (default
600) go to Ollama. With `--poll`, a failed fetch (e.g. a WSJ captcha page) is
retried next cycle instead of stopping the loop, and `fundstrat` is only
fetched 08:30-17:30 ET on trading days. Key env vars: `PROFILE_DIR`,
`OUTPUT_DIR`, `PORTFOLIO_DIR`, `REMOTE_HOST`, `REMOTE_PORT`, `OLLAMA_HOST`,
`OLLAMA_MODEL` (default `gemma4:12b-it-qat` for every site), `OLLAMA_THINK`.

The 600-line default assumes the Ollama server runs with
`OLLAMA_CONTEXT_LENGTH=16384` (set on 8400f); with Ollama's 4096-token default
the prompt does not fit and Ollama truncates it.

### run-market-hours.sh
Loop that runs the daily + flash-insights portfolio scripts and uploads the
resulting HTML reports to a GCS bucket, repeatedly, during this script's
execution window (Mon-Fri, 08:00-18:00 America/New_York, excluding configured
holidays — intentionally ~1.5h before the actual 09:30-16:00 ET market
session and a few hours after it, to also catch pre-market/after-hours
activity). The paths, Python virtual environment, GCS bucket and gcloud
config are set in its `CONFIGURATION` section; the checked-in version is a
generic template to copy (e.g. to `~/workspace/ml-invest-report.sh`) and fill
in.
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
flash-insights step stays optional (`|| true` in `REPORT_COMMAND`), so its
failures don't abort the loop.

Before running, edit the `CONFIGURATION` section for
`GOOGLE_APPLICATION_CREDENTIALS`, `PORTFOLIO_DIR`, `STOCK_QUOTES_CLOUD_RUN_URL`,
`PYTHON_VENV` (activated by the script, so no `source <venv>/bin/activate` is
needed first; empty uses the `python3` on `PATH`), `REPORT_SCRIPTS_DIR`, and the
GCS bucket/`gcloud` configuration.
