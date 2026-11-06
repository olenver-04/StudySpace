"""Every page must render without an exception (the check that would have caught a broken deploy)."""
import pytest

from conftest import U, app, html_of


def ok(at):
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


@pytest.mark.parametrize('lang', ['ru', 'kz'])
def test_public_pages(gh, lang):
    ok(app('welcome'))
    ok(app('home', lang))
    ok(app('library', lang))
    ok(app('about', lang))
    ok(app('course', lang, course='algo'))


@pytest.mark.parametrize('name', ['algo/ru/lectures/Лекция_2.pdf', 'algo/kz/lectures/notes.txt',
                                  'algo/kz/lectures/page.html', 'algo/ru/presentations/Слайды.pptx', 'java/ru/lectures/intro.md'])
def test_reader_every_format(gh, name):
    lang = name.split('/')[1]
    at = ok(app('reader', lang, course=name.split('/')[0], material=U + name))
    assert at.code, 'share link block is missing'


def test_uploaded_html_is_isolated(gh):
    at = ok(app('reader', 'kz', course='algo', material=U + 'algo/kz/lectures/page.html'))
    frames = [e for e in at.get('iframe')]
    srcs = [str(getattr(f, 'proto', f)) for f in frames]
    assert any('data:text/html' in s for s in srcs), srcs


def test_new_badge_and_section(gh):
    gh.recent = {U + 'algo/kz/presentations/Дәріс_1.pdf': '2026-11-05'}
    page = html_of(ok(app('home', 'kz')))
    assert 'Жаңа материалдар' in page and 'badge-text new' in page


def test_badge_lookup_failure_does_not_break_site(gh):
    gh.recent = AttributeError("'GithubStore' object has no attribute 'recent_files'")  # the 2026-11 Cloud crash
    page = html_of(ok(app('home', 'kz')))
    assert 'Жаңа материалдар' not in page


def test_recently_opened(gh):
    at = app('home', 'ru')
    at.session_state['recent'] = [U + 'algo/ru/lectures/Лекция_10.pdf']
    assert 'Недавно открытые' in html_of(ok(at))


def test_course_page_groups(gh):
    page = html_of(ok(app('course', 'ru', course='algo')))
    assert 'course-hero' in page and 'Лекции' in page and 'Презентации' in page
