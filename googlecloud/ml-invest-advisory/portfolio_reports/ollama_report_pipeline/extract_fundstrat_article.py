"""
Extracts one fundstratdirect.com research article (e.g. a Daily Technical Strategy or Newton's Upticks report) from its
DOM dump (google-chrome --dump-dom) as plain text:

    Upticks - November 2026 | Thu, November 12, 2026 | 7:34PM ET | Mark L. Newton, CMT, Head of Technical Strategy
    ## Upticks – Newton’s Law
    <article text>

The article is the first <article> element: the date is in its <time>, the title is its first <h1> outside the body,
the author is in its links to /author/... (name, then title) and the text is in div#content-post. Headings in the text
start with "## " and list items with "- ". Images (charts) are dropped; ticker badges keep only the ticker, not the
live price change printed next to it, which is the quote when the page loaded rather than part of the article.

With --latest-url, it instead prints the newest article link in a research listing page (e.g.
fundstratdirect.com/members/latest-research/?category=daily-technical-strategy) that starts with URL_PREFIX: the links
look like URL_PREFIX[<series>/]YYYY/MM/DD/<slug>/, so the newest is the one with the latest date (the first on the
page among links with that date). The listing's article URLs change every day, and its series vary (the Daily
Technical Strategy listing also holds the monthly Upticks report, under technical-strategy/newtons-upticks/ instead of
technical-strategy/daily-technical-strategy/), so this finds the current one.

Usage (used by fetch-news.sh for fundstratdirect.com article pages and --fundstrat-daily-technical):
    python3 extract_fundstrat_article.py PAGE_HTML > article.txt
    python3 extract_fundstrat_article.py --latest-url LISTING_HTML URL_PREFIX

Exit codes: 0 text or URL written to stdout; 3 the page is not signed in (no "logged-in" <body> class, which WordPress
sets for signed-in members); 4 signed in but no article text or no matching article link found (the page layout
changed); 2 usage error. Only the Python standard library is used.
"""
import re
import sys
from html.parser import HTMLParser

from extract_fundstrat_posts import (BADGE_CLASSES, BLOCK_ELEMENTS, EXIT_NO_POSTS, EXIT_NOT_LOGGED_IN,
                                     SKIPPED_ELEMENTS, VOID_ELEMENTS, clean_body, clean_inline)

HEADINGS = {'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}
# Table cells are inline in BLOCK_ELEMENTS terms; separate them so adjacent cells don't run together.
CELL_ELEMENTS = {'td', 'th'}
# Classes of elements inside the body whose content is never article text.
SKIPPED_CLASSES = {'flashinsight-card-footer', 'gps-modal'}
# An article link in a listing page: URL_PREFIX followed by an optional <series>/ and YYYY/MM/DD/<slug>/.
ARTICLE_LINK_PATTERN = r'href="({prefix}(?:[a-z0-9-]+/)?(\d{{4}})/(\d{{2}})/(\d{{2}})/[^"/?#]+/?)"'


class ArticleParser(HTMLParser):
    """Collects the first <article>'s date, title, author name and title, and body text."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.logged_in = False
        # Stack of (tag, set of classes, drop) for the open elements; text inside an element with drop=True is dropped.
        self.stack = []
        # Number of <span>s opened so far in the current ticker badge, or None outside a badge.
        self.badge_spans = None
        # Stack depth of the first <article>, or None outside it; done is True once it has ended.
        self.article_depth = None
        self.done = False
        # Stack depth of the div#content-post holding the article text, or None outside it.
        self.body_depth = None
        # Stack depth of the current /author/ link, or None outside one.
        self.author_link_depth = None
        self.date = []
        self.title = []
        self.title_done = False
        # One list of text pieces per /author/ link (the name, then the job title).
        self.authors = []
        self.body = []

    def _inside(self, css_class):
        return any(css_class in classes for _, classes, _ in self.stack)

    def _has_open(self, tag_name):
        return any(tag == tag_name for tag, _, _ in self.stack)

    def _part(self):
        """Returns the list that text at the current position belongs to, or None to drop it."""
        if self.article_depth is None or any(drop for _, _, drop in self.stack):
            return None
        if self.body_depth is not None:
            return self.body
        if self._has_open('time'):
            return self.date
        if self._has_open('h1') and not self.title_done:
            return self.title
        if self.author_link_depth is not None:
            return self.authors[-1]
        return None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        classes = set((attributes.get('class') or '').split())
        if tag == 'body' and 'logged-in' in classes:
            self.logged_in = True
        if tag in VOID_ELEMENTS:
            if tag == 'br' and self._part() is self.body:
                self.body.append('\n')
            return
        # x-show elements are Alpine.js popups hidden until clicked (the "Share / Or copy link" dialog), and the <sup>
        # after the author's name is the "AC" analyst certification mark.
        drop = (tag in SKIPPED_ELEMENTS or bool(classes & SKIPPED_CLASSES) or 'x-show' in attributes or
                (tag == 'sup' and self.author_link_depth is not None))
        # A ticker badge is <a class="ticker-badge-tag"><span>TMO <span>-2.55%</span></span></a>: keep the first span's
        # own text. Crypto badges are the same with class="asset-badge-tag".
        if classes & BADGE_CLASSES:
            self.badge_spans = 0
        elif tag == 'span' and self.badge_spans is not None:
            self.badge_spans += 1
            drop = drop or self.badge_spans > 1
        self.stack.append((tag, classes, drop))
        if self.done:
            return
        if self.article_depth is None:
            if tag == 'article':
                self.article_depth = len(self.stack)
            return
        if attributes.get('id') == 'content-post' and self.body_depth is None:
            self.body_depth = len(self.stack)
            return
        part = self._part()
        if part is self.body:
            if classes & BADGE_CLASSES:
                self.body.append(' ')
            if tag in HEADINGS:
                self.body.append('\n## ')
            elif tag == 'li':
                self.body.append('\n- ')
            elif tag in BLOCK_ELEMENTS:
                self.body.append('\n')
            elif tag in CELL_ELEMENTS:
                self.body.append(' | ')
        elif (tag == 'a' and '/author/' in (attributes.get('href') or '') and self.author_link_depth is None
              and self.body_depth is None):
            self.author_link_depth = len(self.stack)
            self.authors.append([])

    def handle_endtag(self, tag):
        # Chrome's DOM dump is well-formed, but pop to the matching element to stay safe on stray end tags.
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                break
        else:
            return
        if tag in BLOCK_ELEMENTS and self._part() is self.body:
            self.body.append('\n')
        if tag == 'h1' and self.title and self._part() is self.title:
            self.title_done = True
        del self.stack[i:]
        if not any(classes & BADGE_CLASSES for _, classes, _ in self.stack):
            self.badge_spans = None
        if self.body_depth is not None and len(self.stack) < self.body_depth:
            self.body_depth = None
        if self.author_link_depth is not None and len(self.stack) < self.author_link_depth:
            self.author_link_depth = None
        if self.article_depth is not None and len(self.stack) < self.article_depth:
            self.article_depth = None
            self.done = True

    def handle_data(self, data):
        part = self._part()
        if part is not None:
            part.append(data)


def format_article(parser):
    """Returns the article as text under a "<title> | <date> | <author>, <author title>" header line."""
    header = [value for value in (clean_inline(parser.title), clean_inline(parser.date)) if value]
    # The avatar and the name are separate links to the same /author/ page; keep each distinct text once.
    author_parts = []
    for parts in parser.authors:
        value = clean_inline(parts)
        if value and value not in author_parts:
            author_parts.append(value)
    if author_parts:
        header.append(', '.join(author_parts))
    # Headings left empty (e.g. one holding only a chart image) become a bare "##" line; drop them.
    body = '\n'.join(line for line in clean_body(parser.body).split('\n') if not re.fullmatch(r'#+', line))
    # A ticker badge also leaves a space after an opening parenthesis and before a possessive ("( TMO", "LITE ’s").
    body = re.sub(r'\( +', '(', re.sub(r' +([’\']s\b)', r'\1', body))
    return ' | '.join(header) + '\n' + body + '\n'


def latest_article_url(html, url_prefix):
    """Returns the link starting with URL_PREFIX that has the latest YYYY/MM/DD date, or None if there is none."""
    latest = None
    for match in re.finditer(ARTICLE_LINK_PATTERN.format(prefix=re.escape(url_prefix.rstrip('/') + '/')), html):
        date = match.group(2, 3, 4)
        # Strictly later only: among links with the same date, the first on the page is the newest.
        if latest is None or date > latest[0]:
            latest = (date, match.group(1))
    return latest[1] if latest else None


def main(argv):
    if len(argv) == 4 and argv[1] == '--latest-url':
        html_path, url_prefix = argv[2], argv[3]
    elif len(argv) == 2 and not argv[1].startswith('-'):
        html_path, url_prefix = argv[1], None
    else:
        print(f'Usage: {argv[0]} PAGE_HTML\n       {argv[0]} --latest-url LISTING_HTML URL_PREFIX', file=sys.stderr)
        return 2
    with open(html_path, encoding='utf-8', errors='replace') as html_file:
        html = html_file.read()
    parser = ArticleParser()
    parser.feed(html)
    parser.close()
    if not parser.logged_in:
        print(f'ERROR: {html_path} is not a signed-in page (no "logged-in" <body> class).', file=sys.stderr)
        return EXIT_NOT_LOGGED_IN

    if url_prefix is not None:
        url = latest_article_url(html, url_prefix)
        if url is None:
            print(f'ERROR: no {url_prefix.rstrip("/")}/[<series>/]YYYY/MM/DD/<slug>/ article link found in {html_path}.',
                  file=sys.stderr)
            return EXIT_NO_POSTS
        print(url)
        return 0

    if not clean_body(parser.body):
        print(f'ERROR: no div#content-post article text found in the first <article> of {html_path}.',
              file=sys.stderr)
        return EXIT_NO_POSTS
    sys.stdout.write(format_article(parser))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
