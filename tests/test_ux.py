from conftest import app, html_of


def ok(at):
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def test_theme_defaults_to_system_and_honours_saved_choice():
    import app as site
    auto = site.theme_css(None)
    assert '@media (prefers-color-scheme: dark)' in auto and ':root.ss-dark' in auto and ':root.ss-light' in auto
    assert site.theme_css('dark').endswith(':root:not(.ss-light) {' + site.THEMES['dark'] + '}')
    assert site.theme_css('light').endswith(':root:not(.ss-dark) {' + site.THEMES['light'] + '}')
    assert site.theme_css('<script>') == auto  # anything else is ignored


def test_top_bar_has_theme_switch_and_mobile_menu(gh):
    at = ok(app('home', 'ru'))
    page = html_of(at)
    assert 'class="ss-theme"' in page and 'class="ss-search"' in page
    keys = {b.key for b in at.button}
    assert {'menu-home', 'menu-library', 'menu-about', 'menu-admin'} <= keys
    at.button(key='menu-library').click().run()
    assert at.session_state['page'] == 'library'
