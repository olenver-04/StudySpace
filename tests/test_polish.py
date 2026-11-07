import html
import json
import re

from conftest import U, app, html_of


def ok(at):
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def search_items(at):
    tag = next(m.value for m in at.markdown if 'id="ss-index"' in str(m.value))
    return json.loads(html.unescape(re.search(r'data-items="([^"]*)"', tag).group(1)))


def test_search_index_lists_only_visible_material(gh):
    items = search_items(ok(app('home', 'ru')))
    urls = [i['u'] for i in items]
    assert any('course=algo' in u and 'lang=kz' in u for u in urls)        # both languages are searchable
    assert not any('java' in u and 'lang=kz' in u for u in urls)            # java has no kz section
    assert any(i['t'] == 'Лекция 2' and i['l'] == 'ru' for i in items)


def test_reader_prev_next_and_breadcrumbs(gh):
    at = ok(app('reader', 'ru', course='algo', material=U + 'algo/ru/lectures/Лекция_10.pdf'))
    keys = {b.key for b in at.button}
    assert {'crumb_home', 'crumb_course', 'prev_item', 'next_item'} <= keys   # Лекция 2 → 10 → Слайды
    at.button(key='next_item').click().run()
    assert at.session_state['material'].endswith('Слайды.pptx')


def test_first_material_has_no_prev(gh):
    at = ok(app('reader', 'ru', course='algo', material=U + 'algo/ru/lectures/Лекция_2.pdf'))
    keys = {b.key for b in at.button}
    assert 'prev_item' not in keys and 'next_item' in keys


def test_welcome_panels_and_footer(gh):
    page = html_of(ok(app('welcome')))
    assert 'langpanel' in page and 'wordmark' in page and 'ss-search' in page
    assert 'class="credit-name"' in page and '>denver<' in page  # author credit (easter egg in fx.js)
