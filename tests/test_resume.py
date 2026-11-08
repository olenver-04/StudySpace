import json
import re
from pathlib import Path

from PIL import Image

from conftest import ROOT, U, app, html_of

LECTURE = U + 'algo/ru/lectures/Лекция_10.pdf'


def ok(at):
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def test_viewer_carries_resume_key_and_save_button(gh):
    page = html_of(ok(app('reader', 'ru', course='algo', material=LECTURE)))
    assert re.search(r'data-key="[0-9a-f]{12}"', page)
    assert 'data-explicit="0"' in page and 'class="deck-save"' in page and 'Продолжаем со слайда {n}' in page


def test_explicit_slide_link_wins_over_remembered_position(gh):
    at = app('reader', 'ru', course='algo', material=LECTURE)
    at.query_params['slide'] = '2'
    assert 'data-explicit="1"' in html_of(ok(at))


def test_manifest_and_icons_are_valid():
    static = Path(ROOT) / 'static'
    manifest = json.loads((static / 'manifest.json').read_text(encoding='utf-8'))
    assert manifest['display'] == 'standalone' and manifest['start_url'] == '/'
    for icon in manifest['icons']:
        width, height = map(int, icon['sizes'].split('x'))
        with Image.open(static / icon['src']) as image:
            assert image.size == (width, height), icon['src']
    with Image.open(static / 'icons' / 'apple-touch-icon.png') as image:
        assert image.size == (180, 180)
