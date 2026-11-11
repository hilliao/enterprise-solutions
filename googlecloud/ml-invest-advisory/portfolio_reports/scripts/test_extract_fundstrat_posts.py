"""
Unit tests for extract_fundstrat_posts.py with a synthetic Flash Insights page in the layout of
fundstratdirect.com/members/flashinsights/ (as of 2026-11):

    python -m pytest -v test_extract_fundstrat_posts.py
"""
import extract_fundstrat_posts as efp


def card(post_id, date, author, title, body):
    """Returns one div.sub-insight-card post with the header, share popup and footer of the real page."""
    return f'''
<div class="sub-insight-card" id="fsi-alert-{post_id}" x-data="{{ shareOpen: false }}">
 <div class="card strategies-card">
  <div class="py-2.5 px-3 flex"><p class="font-semibold">⚡ Flash<span class="italic font-bold">Insights</span></p>
   <div class="time-stamps"><span class="text-sm">{date}</span></div></div>
  <div class="flashinsight-header"><div class="strategy-author-detail">
   <a href="#"><img class="h-14 w-14" alt="{author}"></a>
   <div class="card-title-name"><a href="#"><h6>{author}<sup class="inline-block">AC</sup></h6></a><a href="#"><p>{title}</p></a></div>
  </div><div class="date-time-section flex-col"><div class="min-w-20">🔥</div></div></div>
  <div class="flashinsight-card-body">
   <div class="text-cp-description-text">{body}</div>
   <div class="pb-3"><a class="smartphotosite"><img class="block" alt="FlashInsights"></a></div>
   <div x-show="shareOpen" @click.away="shareOpen = false"><h3>Share</h3><p>Or copy link</p><button>Copy</button></div>
   <div class="flashinsight-card-footer"><div class="flashinsight-social-icns"><div class="hidden">17</div>
    <a @click="shareOpen = true" href="javascript:void(0);" aria-label="Share"></a></div></div>
  </div>
 </div>
</div>'''


def page(cards, logged_in=True):
    body_class = 'page logged-in' if logged_in else 'page'
    return (f'<html><head><title>FlashInsights</title></head><body class="{body_class}">'
            f'<h1>⚡FlashInsights</h1><div id="latest-research-content">{"".join(cards)}</div></body></html>')


TNX_BADGE = ('<a class="card-inn-tag-badge ticker-badge-tag" href="#"><span class="uppercase">^TNX</span>'
             '<span class="text-green-600">2.45%</span></a>')
POSTS = [
    card(2, 'Tue, November 10, 2026 | 11:57AM ET', 'Mark L. Newton, CMT', 'Head of Technical Strategy',
         f'This move in&nbsp;{TNX_BADGE}&nbsp;of 11 bps. today to 4.759% is important.<br>Rates should push higher.'),
    card(1, 'Thu, November 5, 2026 | 2:48PM ET', 'Tom Lee, CFA', 'Co-founder and Head of Research',
         '<p>Today\'s carnage:</p><ul><li>tariff shock</li><li>AI "shock"</li></ul>'),
]


def run(tmp_path, html, capsys):
    page_file = tmp_path / 'page.html'
    page_file.write_text(html, encoding='utf-8')
    status = efp.main(['extract_fundstrat_posts.py', str(page_file)])
    return status, capsys.readouterr()


def test_extracts_posts_with_header_lines(tmp_path, capsys):
    status, captured = run(tmp_path, page(POSTS), capsys)
    assert status == 0
    assert captured.out == (
        '⚡ FlashInsights post 1 of 2 | Tue, November 10, 2026 | 11:57AM ET | Mark L. Newton, CMT, '
        'Head of Technical Strategy\n'
        'This move in ^TNX of 11 bps. today to 4.759% is important.\n'
        'Rates should push higher.\n'
        '\n'
        '⚡ FlashInsights post 2 of 2 | Thu, November 5, 2026 | 2:48PM ET | Tom Lee, CFA, Co-founder and Head of Research\n'
        "Today's carnage:\n"
        '- tariff shock\n'
        '- AI "shock"\n')


def test_drops_live_ticker_change_share_popup_footer_and_images(tmp_path, capsys):
    _, captured = run(tmp_path, page(POSTS), capsys)
    for dropped in ('2.45%', 'Share', 'Or copy link', 'Copy', '17', 'AC', '🔥', '[FlashInsights]'):
        assert dropped not in captured.out


def test_not_logged_in(tmp_path, capsys):
    status, captured = run(tmp_path, page(POSTS, logged_in=False), capsys)
    assert status == efp.EXIT_NOT_LOGGED_IN
    assert captured.out == ''
    assert 'logged-in' in captured.err


def test_no_posts(tmp_path, capsys):
    status, captured = run(tmp_path, page([]), capsys)
    assert status == efp.EXIT_NO_POSTS
    assert captured.out == ''


def test_post_without_body_text_is_skipped(tmp_path, capsys):
    empty = card(3, 'Wed, November 11, 2026 | 9:00AM ET', 'Mark L. Newton, CMT', 'Head of Technical Strategy', '')
    status, captured = run(tmp_path, page([empty] + POSTS), capsys)
    assert status == 0
    assert captured.out.startswith('⚡ FlashInsights post 1 of 2 | Tue, November 10, 2026')
