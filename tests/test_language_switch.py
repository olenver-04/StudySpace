"""The RU/KZ button keeps the visitor on the same page in the other language."""
from conftest import U, app


def switch(at):
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    at.button(key='nav-lang').click().run()
    assert not at.exception, [e.value for e in at.exception]
    return at.session_state


def test_section_pages_stay(gh):
    for page in ('home', 'library', 'about'):
        state = switch(app(page, 'ru'))
        assert (state['page'], state['lang']) == (page, 'kz')


def test_course_stays_when_it_has_the_other_language(gh):
    state = switch(app('course', 'ru', course='algo'))
    assert (state['page'], state['lang'], state['course']) == ('course', 'kz', 'algo')


def test_course_without_the_other_language_goes_home(gh):
    state = switch(app('course', 'ru', course='java'))  # java is RU only
    assert (state['page'], state['lang']) == ('home', 'kz')


def test_presentation_opens_its_counterpart(gh):
    # RU order: Лекция 2, Лекция 10, Слайды; KZ order: notes, page, Дәріс 1 (lectures first, then natural order)
    state = switch(app('reader', 'ru', course='algo', material=U + 'algo/ru/lectures/Лекция_10.pdf'))
    assert (state['page'], state['lang']) == ('reader', 'kz')
    assert state['material'] == U + 'algo/kz/lectures/page.html'  # same position: second


def test_last_position_is_clamped(gh):
    state = switch(app('reader', 'kz', course='algo', material=U + 'algo/kz/presentations/Дәріс_1.pdf'))
    assert state['material'] == U + 'algo/ru/presentations/Слайды.pptx'  # third of three


def test_welcome_page_switches_its_own_language(gh):
    from conftest import html_of
    at = app('welcome')
    state = switch(at)
    assert (state['page'], state['ui_lang']) == ('welcome', 'kz')
    page = html_of(at)
    assert 'Бәрі' in page and 'Оқу тілі / Язык обучения' in page
    at.button(key='nav-lang').click().run()  # and back
    assert at.session_state['ui_lang'] == 'ru' and 'Учиться' in html_of(at)


def test_back_to_welcome_keeps_the_section_language(gh):
    at = app('home', 'kz')
    at.run()
    at.button(key='nav-brand').click().run()
    assert at.session_state['page'] == 'welcome' and at.session_state['ui_lang'] == 'kz'
