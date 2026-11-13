# ollama_report_pipeline/

The pipeline that turns news and portfolio data into reports with a local Ollama LLM:
`fetch-news.sh` fetches and summarizes news pages (WSJ, CNBC, other front pages, and
Fundstrat research) into `news-<SITE>_YYYY-MM-DD.txt` files, `report-daily.sh` and
`report-news-impact.sh` turn the portfolios and those news files into reports, and
`run-market-hours.sh` runs the reports during market hours and uploads them to GCS.
Most scripts assume the ml-invest-advisory portfolio_reports layout (portfolio JSON
files, prompt templates, `build_portfolio_prompt.py` in the parent folder).

## Scripts

### report-daily.sh
Generates the daily portfolio analysis report. For every `*.json` file in
`PORTFOLIO_DIR`, builds an LLM prompt via `build_portfolio_prompt.py` (optionally
inlining a `market-commentary_YYYY-MM-DD.txt` file), runs it through
`ollama run $OLLAMA_MODEL` (default `gemma4:12b-it-qat`), and writes a Markdown report
(plus an HTML version if `pandoc` is installed).
Key env vars: `PORTFOLIO_DIR`, `LLM_PROMPT_TEMPLATE`, `USE_CASE`,
`MARKET_COMMENTARY_FILE`, `STOCK_QUOTES_CLOUD_RUN_URL`, `TW_STOCK_QUOTES_CLOUD_RUN_URL`, `OLLAMA_MODEL`, `OLLAMA_TIMEOUT_SECONDS`
(default 600; kills a stuck `ollama run`, retries it once, then fails the script).
Every `ollama run` in `report-daily.sh`, `report-news-impact.sh` and `fetch-news.sh`
uses `--verbose`, so the terminal shows each run's total duration, token counts and
tokens/s (on stderr; the reports and summaries don't include them).

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
`flash-insights-yang-cnbc-llm-generated.html`). Set `NEWS_FILES` to a comma-separated list
to use other files. Exits with an error if no news file is found.
Key env vars: `PORTFOLIO_DIR`, `LLM_PROMPT_TEMPLATE`, `USE_CASE`, `NEWS_FILES`,
`OLLAMA_MODEL`, `OLLAMA_TIMEOUT_SECONDS`.

### compare-models.sh
Runs one prompt (e.g. a `daily-report-<portfolio>-llm-prompt.txt` written by
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
one-time setup) and extracts the posts with `extract_fundstrat_posts.py`. Any
other fundstratdirect.com page (e.g. a `--url` research article) is extracted with
`extract_fundstrat_article.py` instead of `html2text`, so the prompt gets only the
article (title, date, author, text) without the site menus. Technical strategy
articles are summarized with a prompt for the market view, support/resistance
levels and price targets; macro strategy articles (`/macro-strategy/` URLs) with
one for the thesis, the macro drivers and the stocks favored or warned about. Every summary starts with a "Fetched at
... from <URL>; summarized at ..." line in Eastern time. Every `--site` run copies its summary
to `PORTFOLIO_DIR/news-<SITE>_YYYY-MM-DD.txt` (read by `report-news-impact.sh`),
deletes that site's older `news-<SITE>_*.txt` files there (printing each one)
and, with `scp -P $REMOTE_PORT`, to the same path on `--remote-host` (default
`hil@hil-fr-dc.freeddns.org`; `""` skips the copy), where it lists `PORTFOLIO_DIR`
over `ssh` and deletes the site's older `news-<SITE>_*.txt` files too (printing
each one). `--url` runs only write to
`OUTPUT_DIR`.

`--aggregate` (experimental) fetches the front pages in `AGGREGATE_URLS` (default:
Bloomberg, Financial Times, Yahoo Finance, MarketWatch, Investing.com and Barron's,
comma-separated), keeps each page's headlines and teasers (lines of 5 or more words,
without navigation, cookie banners or repeats), splits `--lines` evenly across the
pages that load, and summarizes them together in one Ollama run into
`PORTFOLIO_DIR/news-global-headlines_YYYY-MM-DD.txt`, which `report-news-impact.sh` picks up
like the other news files and which is copied to `--remote-host` the same way. A
page that fails to load (e.g. a captcha page) is left out with a warning; the run
fails only if every page fails. CNBC and WSJ aren't in the default list because
`--site cnbc` and `--site wsj` already cover them. Reuters and The Economist aren't
either: both answer headless Chrome with a DataDome captcha page.

`--fundstrat-daily-technical` and `--fundstrat-macro-analysis` (experimental) summarize
the newest article of a Fundstrat research listing, whose URL changes with every
article (`<prefix><series>/YYYY/MM/DD/<slug>/`): the script fetches the listing page,
takes the article link with the latest date (`extract_fundstrat_article.py
--latest-url`), then fetches and summarizes that article into
`PORTFOLIO_DIR/news-<flag>_YYYY-MM-DD.txt`, published like the `--site` files
(and picked up by `report-news-impact.sh`). The listings are set in
`FUNDSTRAT_LISTING_URLS` in the script:

| Flag | Listing page | Article links |
|---|---|---|
| `--fundstrat-daily-technical` | `latest-research/?category=daily-technical-strategy` (Mark Newton) | `technical-strategy/daily-technical-strategy/...`, and `technical-strategy/newtons-upticks/...` on the monthly Upticks day |
| `--fundstrat-macro-analysis` | `latest-research/?category=first-word` (Tom Lee) | `macro-strategy/first-word/...` |

Both run after the `--site` sites and before `--aggregate`, and work with `--poll`.

Every Fundstrat prompt (Flash Insights, technical and macro articles) carries
`FUNDSTRAT_ACCURACY_RULES`: keep the author's negations and qualifiers, quote word for
word, give each discussed stock's stance in the author's own words before its risks,
and list only the risks the text states ("No risks stated" otherwise). They were added
after gemma4:12b-it-qat turned "a negative, but not a 'thesis changer'" into a
"thesis changer" risk; with them, 3 of 3 reruns of that article kept the author's view.
```
./fetch-news.sh --site wsj|cnbc|fundstrat
./fetch-news.sh --site wsj,cnbc,fundstrat         # several sites, one after another
./fetch-news.sh --aggregate                       # AGGREGATE_URLS front pages, summarized together
./fetch-news.sh --site cnbc --aggregate --poll    # CNBC, then the aggregate, every cycle
./fetch-news.sh --fundstrat-daily-technical       # newest Daily Technical Strategy (or Upticks) article
./fetch-news.sh --fundstrat-macro-analysis        # newest First Word macro article
./fetch-news.sh --url <fundstratdirect.com article URL> --name <label>   # one Fundstrat article
./fetch-news.sh --url <URL> --name <label> [--lines N]
./fetch-news.sh --site wsj --profile-dir DIR      # use another Chrome profile
./fetch-news.sh --site wsj --output-dir DIR       # write to DIR
./fetch-news.sh --site wsj --remote-host U@H       # copy news-wsj_YYYY-MM-DD.txt to another host
./fetch-news.sh --site cnbc,fundstrat --poll [MIN]  # repeat forever, sleeping MIN (default 30) after each cycle
./fetch-news.sh --list
./fetch-news.sh -h|--help
```
Requires `google-chrome`, `html2text`, `ollama` (optionally `pandoc`), and `python3` for
`--site fundstrat`, the `--fundstrat-*` flags and fundstratdirect.com `--url` pages. Writes
to `OUTPUT_DIR` (default `~/Documents/news-aggregate/`). For other sites, the site navigation before the first `******`
or `*****` heading (html2text `<h1>` or `<h2>`) is skipped, and the next `--lines` lines (default
600) go to Ollama. Several `--site` keys are fetched one after another; a
failed site (e.g. a WSJ captcha page) doesn't stop the others, and the run then
exits 1. `--poll` only fetches 08:00-18:00 ET on trading days (1.5 hours before
the NYSE open until 2 hours after the close, the same window as
`run-market-hours.sh`) and otherwise sleeps until the window opens; a failed site is retried next
cycle instead of stopping the loop. Key env vars: `PROFILE_DIR`,
`OUTPUT_DIR`, `PORTFOLIO_DIR`, `REMOTE_HOST`, `REMOTE_PORT`, `AGGREGATE_URLS`,
`OLLAMA_HOST` (default `8400f:11434`), `OLLAMA_MODEL` (default `gemma4:12b-it-qat` for every site), `OLLAMA_THINK`.

The 600-line default assumes the Ollama server runs with
`OLLAMA_CONTEXT_LENGTH=16384` (set in the local `ollama` systemd service); with Ollama's 4096-token default
the prompt does not fit and Ollama truncates it.

### extract_fundstrat_posts.py
Used by `fetch-news.sh --site fundstrat`: parses the Flash Insights posts (each
`div.sub-insight-card`) out of Chrome's DOM dump of the members page and prints
them as text, each under a `⚡ FlashInsights post N of M | <date> | <author>, <title>`
line. Share buttons, like counts, images and the live price change in ticker
badges (`ticker-badge-tag`, and `asset-badge-tag` for crypto such as ETH) are
dropped. Exits 3 if the page isn't signed in (no `logged-in` `<body>`
class) and 4 if it finds no posts. Standard library only; tests:
`python -m pytest -v test_extract_fundstrat_posts.py`.

### extract_fundstrat_article.py
Used by `fetch-news.sh` for fundstratdirect.com research articles and the
`--fundstrat-*` flags. `extract_fundstrat_article.py PAGE_HTML` prints the first
`<article>` as text: a `<title> | <date> | <author>, <author title>` line, then
`div#content-post` with headings as `## ` and list items as `- `; images, share
popups and the live price change in ticker badges are dropped (it reuses the badge
and text-cleanup code of `extract_fundstrat_posts.py`).
`extract_fundstrat_article.py --latest-url LISTING_HTML URL_PREFIX` prints the
listing page's article link under `URL_PREFIX` (`URL_PREFIX[<series>/]YYYY/MM/DD/<slug>/`)
with the latest date, the first on the page among links of that date. Same exit
codes as `extract_fundstrat_posts.py` (3 not signed in, 4 no article text or link).
Standard library only; no unit tests yet.

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
./run-market-hours.sh [--immediate] [--idle-sleep SEC] [-h|--help]
```
- `--immediate`: run once now, ignoring the window, then exit.
- `--idle-sleep`: seconds between recheck cycles while outside the window
  (default 60); while idle, prints a live single-line countdown to the next
  execution-window start.

If the command fails, the loop prints an `ERROR` to stderr and exits with the
command's exit code, instead of repeating the failing step in a tight loop.
Inside the window, each run starts as soon as the previous one finishes, so before
every run the loop checks that `PORTFOLIO_DIR` has a portfolio `*.json` file and
exits with code 66 if not; without portfolios each run would finish instantly and
the loop would spin. `build_portfolio_prompt.py` retries a failed stock
quotes Cloud Run request with exponential backoff (1, 2, 4, 8, 16 seconds),
printing each failure's status code and response body (e.g. the 500 with
Alpaca's error in `detail`) to stderr, then exits with code 69. The
flash-insights step stays optional (`|| true` in `REPORT_COMMAND`), so its
failures don't abort the loop.

Before running, edit the `CONFIGURATION` section for
`GOOGLE_APPLICATION_CREDENTIALS`, `PORTFOLIO_DIR`, `STOCK_QUOTES_CLOUD_RUN_URL`,
`TW_STOCK_QUOTES_CLOUD_RUN_URL`,
`PYTHON_VENV` (activated by the script, so no `source <venv>/bin/activate` is
needed first; empty uses the `python3` on `PATH`), `REPORT_SCRIPTS_DIR`, and the
GCS bucket/`gcloud` configuration.
