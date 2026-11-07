import json

from conftest import U, app, html_of
from fulltext import FullText, extract_text


def ok(at):
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


# ---------- full-text index ----------
def test_extract_text_plain_formats():
    assert extract_text('  Лекция\n\n  о   циклах '.encode('utf-8'), '.txt') == 'Лекция о циклах'
    assert extract_text(b'# Title', '.md') == '# Title'
    assert extract_text(b'PK', '.pptx') == ''


def test_index_build_skips_broken_files(tmp_path):
    target = tmp_path / 'static' / 'fulltext.json'
    docs = [{'u': '?a', 'path': 'a.txt', 'sha': '1', 'extension': '.txt'},
            {'u': '?b', 'path': 'b.pdf', 'sha': '2', 'extension': '.pdf'}]
    data = {'a.txt': 'жизненный цикл ПО'.encode('utf-8'), 'b.pdf': b'not a pdf'}
    index = FullText(target)
    index.build(docs, lambda path, sha: data[path], ('sig',))
    assert json.loads(target.read_text(encoding='utf-8')) == {'?a': 'жизненный цикл ПО'}
    assert not index.running and index.signature == ('sig',)


# ---------- studied marks ----------
LECTURE = U + 'algo/ru/lectures/Лекция_10.pdf'


def test_mark_as_studied_and_progress(gh):
    at = ok(app('reader', 'ru', course='algo', material=LECTURE))
    at.button(key='toggle_done').click().run()
    assert len(at.session_state['done']) == 1
    at.session_state['page'] = 'course'
    page = html_of(ok(at))
    assert page.count('class="card-badge done"') == 1 and 'Изучено' in page and '1/3 изучено' in page
    # Toggling again removes the mark.
    at.session_state['page'] = 'reader'
    ok(at)
    at.button(key='toggle_done').click().run()
    assert at.session_state['done'] == []


def test_fresh_visitor_has_nothing_studied(gh):
    page = html_of(ok(app('course', 'ru', course='algo')))
    assert 'class="card-badge done"' not in page and '0/3 изучено' in page


# ---------- admin dashboard ----------
def test_attention_flags_empty_sections_only():
    import app as site
    config = {'courses': [{'id': 'a', 'title_ru': 'A', 'languages': ['ru', 'kz'], 'title_kz': 'A'}]}
    materials = [{'course_id': 'a', 'lang': 'ru', 'kind': 'presentations'}]
    issues = site.attention(config, materials)
    assert issues == [i for i in issues if 'KZ' in i] and any('нет материалов' in i for i in issues)  # presentations-only is fine


def test_dashboard_renders(gh):
    page = html_of(ok(app('admin', admin=True, secrets={'ADMIN_PASSWORD': 'x'})))
    assert 'Требует внимания' in page and 'admin-stats' in page
