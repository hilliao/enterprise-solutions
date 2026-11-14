"""
Report catalog (beta): turns the Cloud Storage objects of the portfolio reports into the viewer's tabs.

Purpose:
  The report pipeline (portfolio_reports/ollama_report_pipeline/run-market-hours.sh) uploads each portfolio's HTML
  reports to its own folder under the bucket prefix:
      <prefix><portfolio>/daily-report-<portfolio>-llm-generated.html
      <prefix><portfolio>/news-<site>-<portfolio>-llm-generated.html
  e.g. reports/vicky-tw-portfolio/news-fundstrat-daily-technical-vicky-tw-portfolio-llm-generated.html. This module
  makes one tab per portfolio folder, with one sub-tab per report.

How names are read:
  - The folder names the portfolio, so a report's site is what sits between "news-" and "-<portfolio>-llm-generated
    .html"; site and portfolio names may both contain dashes.
  - Any other *.html in a portfolio folder gets a tab labelled with its file name, after the known reports.
  - Objects directly under the prefix (the old flat layout) or deeper than one folder are not listed.

Maintenance:
  When fetch-news.sh gets a --site whose label needs special capitalization, add it to SITE_LABELS.
"""
import re
import urllib.parse
from dataclasses import asdict, dataclass

REPORT_SUFFIX = '-llm-generated.html'
# Use cases (file name prefixes) in tab order, with their labels.
USE_CASES = {'daily-report': 'Daily report', 'news': 'News'}
SITE_LABELS = {'cnbc': 'CNBC', 'wsj': 'WSJ'}
# The only report paths the viewer lists or serves: <portfolio folder>/<file>.html, each part of letters, digits,
# '.', '_' and '-', not starting with '.'. This also rules out path traversal ('..', extra '/', '%2F').
_SAFE_PART = r'[A-Za-z0-9_-][A-Za-z0-9._-]*'
SAFE_REPORT_PATH = re.compile(rf'^{_SAFE_PART}/{_SAFE_PART}\.html$')


@dataclass(frozen=True)
class Report:
    file: str        # <portfolio>/<file name>.html, relative to the bucket prefix
    portfolio: str   # the folder name
    use_case: str    # a USE_CASES key, or '' for an unrecognized name
    site: str        # news site of a news report, '' otherwise
    label: str       # tab label
    updated: str     # RFC 3339 upload time
    size: int        # bytes
    auth_url: str    # authenticated https://storage.cloud.google.com/... URL


def is_safe_report_path(path: str) -> bool:
    return bool(SAFE_REPORT_PATH.match(path))


def group_reports(objects: list[dict], bucket: str, prefix: str) -> list[dict]:
    """
    Groups Cloud Storage objects ({'name', 'updated', 'size'}) into
        [{'portfolio': str, 'reports': [Report as dict, ...]}, ...]
    with portfolios sorted by name, and in each portfolio the daily report first, then the news reports by site,
    then any other file. Objects whose path under the prefix fails is_safe_report_path() are left out.
    """
    groups: dict[str, list[Report]] = {}
    for obj in objects:
        path = obj['name'].removeprefix(prefix)
        if obj['name'].startswith(prefix) and is_safe_report_path(path):
            report = _make_report(path, obj, bucket)
            groups.setdefault(report.portfolio, []).append(report)

    return [{'portfolio': portfolio, 'reports': [asdict(report) for report in sorted(reports, key=_tab_order)]}
            for portfolio, reports in sorted(groups.items())]


def parse_report_name(file_name: str, portfolio: str) -> tuple[str, str]:
    """Returns (use case, site) of a report file name in the portfolio's folder; ('', '') if it isn't recognized."""
    if file_name == f'daily-report-{portfolio}{REPORT_SUFFIX}':
        return 'daily-report', ''
    site = file_name.removeprefix('news-').removesuffix(f'-{portfolio}{REPORT_SUFFIX}')
    if file_name.startswith('news-') and file_name.endswith(f'-{portfolio}{REPORT_SUFFIX}') and site:
        return 'news', site
    return '', ''


def site_label(site: str) -> str:
    """'fundstrat-daily-technical' -> 'Fundstrat daily technical', 'wsj' -> 'WSJ'."""
    if site in SITE_LABELS:
        return SITE_LABELS[site]
    first, *rest = site.split('-')
    return ' '.join([first.capitalize(), *rest])


def _make_report(path: str, obj: dict, bucket: str) -> Report:
    portfolio, file_name = path.split('/')
    use_case, site = parse_report_name(file_name, portfolio)
    if not use_case:
        label = file_name.removesuffix('.html')
    elif site:
        label = f'{USE_CASES[use_case]} · {site_label(site)}'
    else:
        label = USE_CASES[use_case]
    return Report(file=path, portfolio=portfolio, use_case=use_case, site=site, label=label,
                  updated=obj.get('updated', ''), size=int(obj.get('size', 0)),
                  auth_url=f'https://storage.cloud.google.com/{bucket}/{urllib.parse.quote(obj["name"])}')


def _tab_order(report: Report):
    use_case_rank = list(USE_CASES).index(report.use_case) if report.use_case in USE_CASES else len(USE_CASES)
    return use_case_rank, report.site, report.file
