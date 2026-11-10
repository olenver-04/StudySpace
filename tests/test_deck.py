from PIL import Image

from conftest import U, app, blank_pdf, html_of
from fulltext import PAGE_BREAK, dominant_color, extract_text, render_pages

LECTURE = U + 'algo/ru/lectures/Лекция_10.pdf'


def ok(at):
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def test_render_pages_writes_slides_and_filmstrip(tmp_path):
    assert render_pages(blank_pdf(3), tmp_path) == 3
    names = sorted(p.name for p in tmp_path.iterdir())
    assert names == ['1.webp', '2.webp', '3.webp', 't1.webp', 't2.webp', 't3.webp']


def test_pdf_opens_in_the_slide_viewer(gh):
    page = html_of(ok(app('reader', 'ru', course='algo', material=LECTURE)))
    assert 'class="deck"' in page and 'data-total="3"' in page and 'data-start="1"' in page
    assert page.count('class="deck-thumb') == 3
    assert 'class="deck-glow"' in page and '/t1.webp' in page  # backlight uses the small preview


def test_slide_parameter_opens_that_slide(gh):
    at = app('reader', 'ru', course='algo', material=LECTURE)
    at.query_params['slide'] = '2'
    page = html_of(ok(at))
    assert 'data-start="2"' in page and '/2.webp"' in page


def test_bad_slide_parameter_is_ignored(gh):
    at = app('reader', 'ru', course='algo', material=LECTURE)
    at.query_params['slide'] = '99'
    assert 'data-start="3"' in html_of(ok(at))  # clamped to the last slide
    at = app('reader', 'ru', course='algo', material=LECTURE)
    at.query_params['slide'] = 'x'
    assert 'data-start="1"' in html_of(ok(at))


def test_empty_pages_leave_no_stray_breaks():
    assert PAGE_BREAK not in extract_text(blank_pdf(3), '.pdf')


def test_accent_comes_from_the_coloured_area_not_the_background():
    image = Image.new('RGB', (320, 180), (24, 32, 60))           # dark navy background
    image.paste((230, 120, 40), (200, 20, 300, 160))            # orange block
    color = dominant_color(image)
    r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    assert r > g > b  # orange hue


def test_grey_cover_has_no_accent():
    assert dominant_color(Image.new('RGB', (64, 36), (128, 128, 128))) is None
