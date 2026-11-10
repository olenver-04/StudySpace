import io

import github_store
from pypdf import PdfWriter

from conftest import TREE, app, html_of
from fulltext import render_cover


def ok(at):
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def test_russian_plurals():
    import app as site
    forms = {n: site.plural(n, 'ru', 'slides') for n in (1, 2, 5, 11, 21, 22, 112)}
    assert forms == {1: 'слайд', 2: 'слайда', 5: 'слайдов', 11: 'слайдов', 21: 'слайд', 22: 'слайда', 112: 'слайдов'}
    assert site.plural(5, 'kz', 'slides') == 'слайд'


def test_render_cover_writes_webp_and_counts_pages(tmp_path):
    writer = PdfWriter()
    for _ in range(3):
        writer.add_blank_page(width=1440, height=810)
    buf = io.BytesIO()
    writer.write(buf)
    target = tmp_path / 'thumbs' / 'abc.webp'
    assert render_cover(buf.getvalue(), target) == (3, None)  # a white page has no accent colour
    assert target.read_bytes()[:4] == b'RIFF' and target.stat().st_size > 0


def presentations_only(monkeypatch):
    tree = [t for t in TREE if '/lectures/' not in t['path']]
    monkeypatch.setattr(github_store.GithubStore, 'tree', lambda self: [dict(t) for t in tree])


def test_presentation_only_site_hides_the_split(gh, monkeypatch):
    presentations_only(monkeypatch)
    home = ok(app('home', 'ru'))
    page = html_of(home)
    assert 'лекций' not in page.lower() and 'class="stats' not in page  # no numbers row on the home page
    library = ok(app('library', 'ru'))
    assert not any(s.key == 'kind_selector_ru' for s in library.selectbox)
    course = html_of(ok(app('course', 'ru', course='algo')))
    assert 'презентация' in course.lower() and 'Лекции' not in course


def test_mixed_site_keeps_the_split(gh):
    library = ok(app('library', 'ru'))
    assert any(s.key == 'kind_selector_ru' for s in library.selectbox)


def test_course_hero_shows_a_fan_of_covers(gh, tmp_path):
    thumbs = tmp_path / 'static' / 'thumbs'  # the same folder the gh fixture points STUDYSPACE_STATIC to
    thumbs.mkdir(parents=True)
    for sha in ('sha0', 'sha1'):  # the two RU lectures of "algo"
        (thumbs / f'{sha}.webp').write_bytes(b'RIFF')
    page = html_of(ok(app('course', 'ru', course='algo')))
    assert 'class="course-fan"' in page and page.count('app/static/thumbs/sha') >= 2


def test_no_fan_without_covers(gh):
    assert 'class="course-fan"' not in html_of(ok(app('course', 'ru', course='algo')))
