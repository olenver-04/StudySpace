from conftest import U, app


def ok(at):
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def test_admin_without_password_shows_setup(gh):
    at = ok(app('admin'))
    assert at.code  # setup instructions with the secrets template


def test_login_limit(gh):
    at = ok(app('admin', secrets={'ADMIN_PASSWORD': 'right'}))

    def login(password):
        at.text_input[0].input(password)
        next(b for b in at.button if b.label == 'Войти').click()
        at.run()

    login('wrong')
    assert any('Осталось попыток: 4' in e.value for e in at.error), [e.value for e in at.error]
    for _ in range(4):
        login('wrong')
    login('right')  # even the right password waits out the lockout
    assert any('Слишком много' in e.value for e in at.error), [e.value for e in at.error]
    assert not at.session_state['admin_ok']


def test_admin_dashboard_and_bulk_move(gh):
    at = ok(app('admin', admin=True, secrets={'ADMIN_PASSWORD': 'x'}))
    pick = next(m for m in at.multiselect if m.key == 'file_pick_algo')
    lectures = [o for o in pick.options if 'Презентация' in o]
    pick.set_value(lectures).run()
    at.button(key='to_lect_algo').click().run()
    assert not at.exception
    writes = [c for c in gh.calls if c[0] == 'write']
    deletes = [c for c in gh.calls if c[0] == 'delete']
    assert len(writes) == len(deletes) == 2
    assert all('/lectures/' in w[1] and w[2] > 0 for w in writes)
    assert all('/presentations/' in d[1] for d in deletes)


def test_telegram_message_escapes_and_links(gh):
    import app as site
    text = site.upload_message({'id': 'algo', 'title_ru': 'A<b>', 'icon': '🧮'}, 'ru', 'lectures',
                               [('Лекция_1.pdf', U + 'algo/ru/lectures/Лекция_1.pdf')])
    assert 'A&lt;b&gt;' in text and 'Лекция 1' in text and 'material=' in text
