"""
Extracts the Flash Insights posts from a fundstratdirect.com/members/flashinsights/ DOM dump (google-chrome
--dump-dom) as plain text, one post after another, newest first as on the page:

    ⚡ FlashInsights post 1 of 10 | Tue, November 10, 2026 | 11:57AM ET | Mark L. Newton, CMT, Head of Technical Strategy
    <post text>

Each post is a <div class="sub-insight-card" id="fsi-alert-<post id>">, with the date in div.time-stamps, the author
in div.strategy-author-detail (name in <h6>, title in <p>) and the text in div.flashinsight-card-body. Images (charts)
are dropped; ticker badges keep only the ticker, not the live price change printed next to it, which is the quote
when the page loaded rather than part of the post.

Usage (used by fetch-news.sh --site fundstrat):
    python3 extract_fundstrat_posts.py PAGE_HTML > posts.txt

Exit codes: 0 posts written to stdout; 3 the page is not signed in (no "logged-in" <body> class, which WordPress
sets for signed-in members); 4 signed in but no posts found (the page layout changed); 2 usage error.
Only the Python standard library is used.
"""
import re
import sys
from html.parser import HTMLParser

EXIT_NOT_LOGGED_IN = 3
EXIT_NO_POSTS = 4

# Elements without an end tag; they're never pushed on the element stack.
VOID_ELEMENTS = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'source', 'track', 'wbr'}
# Elements whose text starts on a new line.
BLOCK_ELEMENTS = {'p', 'div', 'li', 'ul', 'ol', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'blockquote', 'table', 'tr',
                  'section', 'article', 'pre'}
# Elements whose content is never post text.
SKIPPED_ELEMENTS = {'script', 'style', 'svg', 'noscript', 'button', 'template'}
# Classes of elements whose content is never post text: the like count and share buttons below each post.
SKIPPED_CLASSES = {'flashinsight-card-footer'}
# Classes of the ticker badges: ticker-badge-tag for stocks, ETFs and indexes, asset-badge-tag for crypto (e.g. ETH).
BADGE_CLASSES = {'ticker-badge-tag', 'asset-badge-tag'}


class FlashInsightsParser(HTMLParser):
    """Collects each sub-insight-card's date, author name, author title and body text."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.logged_in = False
        self.posts = []
        # Stack of (tag, set of classes, drop) for the open elements; text inside an element with drop=True is dropped.
        self.stack = []
        # Number of <span>s opened so far in the current ticker badge, or None outside a badge.
        self.badge_spans = None
        # Stack depth of the current card's <div>, or None outside a card.
        self.card_depth = None
        self.post = None

    def _inside(self, css_class):
        return any(css_class in classes for _, classes, _ in self.stack)

    def _has_open(self, tag_name):
        return any(tag == tag_name for tag, _, _ in self.stack)

    def _part(self):
        """Returns the key of self.post that text at the current position belongs to, or None to drop it."""
        if any(drop for _, _, drop in self.stack):
            return None
        if self._inside('time-stamps'):
            return 'date'
        if self._inside('strategy-author-detail'):
            if self._has_open('h6'):
                return 'author'
            if self._has_open('p'):
                return 'title'
            return None
        if self._inside('flashinsight-card-body'):
            return 'body'
        return None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        classes = set((attributes.get('class') or '').split())
        if tag == 'body' and 'logged-in' in classes:
            self.logged_in = True
        if tag in VOID_ELEMENTS:
            if tag == 'br' and self.post is not None:
                self.post['body'].append('\n')
            return
        # x-show elements are Alpine.js popups hidden until clicked (the "Share / Or copy link" dialog), and the <sup>
        # after the author's name is the "AC" analyst certification mark.
        drop = (tag in SKIPPED_ELEMENTS or bool(classes & SKIPPED_CLASSES) or 'x-show' in attributes or
                (tag == 'sup' and self._inside('strategy-author-detail')))
        # A ticker badge is <a class="ticker-badge-tag"><span>^TNX</span><span>2.45%</span></a>: keep the first span.
        if classes & BADGE_CLASSES:
            self.badge_spans = 0
        elif tag == 'span' and self.badge_spans is not None:
            self.badge_spans += 1
            drop = drop or self.badge_spans > 1
        self.stack.append((tag, classes, drop))
        if self.card_depth is None and tag == 'div' and 'sub-insight-card' in classes:
            self.card_depth = len(self.stack)
            self.post = {'id': attributes.get('id', ''), 'date': [], 'author': [], 'title': [], 'body': []}
            return
        if self.post is None:
            return
        if classes & BADGE_CLASSES:
            self.post['body'].append(' ')
        if tag in BLOCK_ELEMENTS and self._part() == 'body':
            self.post['body'].append('\n- ' if tag == 'li' else '\n')

    def handle_endtag(self, tag):
        # Chrome's DOM dump is well-formed, but pop to the matching element to stay safe on stray end tags.
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                break
        else:
            return
        if self.post is not None and tag in BLOCK_ELEMENTS and self._part() == 'body':
            self.post['body'].append('\n')
        del self.stack[i:]
        if not any(classes & BADGE_CLASSES for _, classes, _ in self.stack):
            self.badge_spans = None
        if self.card_depth is not None and len(self.stack) < self.card_depth:
            self.posts.append(self.post)
            self.card_depth = None
            self.post = None

    def handle_data(self, data):
        if self.post is None:
            return
        part = self._part()
        if part is not None:
            self.post[part].append(data)


def clean_inline(parts):
    """Joins text pieces into one line with single spaces."""
    return re.sub(r'\s+', ' ', ''.join(parts)).strip(' ,')


def clean_body(parts):
    """Joins body text pieces into paragraphs: single spaces within a line, no blank lines."""
    # [^\S\n] also matches the non-breaking spaces around ticker badges.
    lines = (re.sub(r'[^\S\n]+', ' ', line).strip() for line in ''.join(parts).split('\n'))
    text = '\n'.join(line for line in lines if line)
    # A ticker badge leaves a space before the punctuation that follows it ("^TNX ." -> "^TNX.").
    return re.sub(r' +([.,;:!?)])', r'\1', text)


def format_posts(posts):
    """Returns the posts as text, each starting with a header line naming its number, date and author."""
    blocks = []
    for number, post in enumerate(posts, start=1):
        header = [f'⚡ FlashInsights post {number} of {len(posts)}']
        header += [value for value in (clean_inline(post['date']),) if value]
        author = ', '.join(value for value in (clean_inline(post['author']), clean_inline(post['title'])) if value)
        if author:
            header.append(author)
        blocks.append(' | '.join(header) + '\n' + clean_body(post['body']))
    return '\n\n'.join(blocks) + '\n'


def main(argv):
    if len(argv) != 2:
        print(f'Usage: {argv[0]} PAGE_HTML', file=sys.stderr)
        return 2
    with open(argv[1], encoding='utf-8', errors='replace') as html_file:
        parser = FlashInsightsParser()
        parser.feed(html_file.read())
        parser.close()
    if not parser.logged_in:
        print(f'ERROR: {argv[1]} is not a signed-in page (no "logged-in" <body> class).', file=sys.stderr)
        return EXIT_NOT_LOGGED_IN
    posts = [post for post in parser.posts if clean_body(post['body'])]
    if not posts:
        print(f'ERROR: no div.sub-insight-card Flash Insights posts with text found in {argv[1]}.', file=sys.stderr)
        return EXIT_NO_POSTS
    sys.stdout.write(format_posts(posts))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
