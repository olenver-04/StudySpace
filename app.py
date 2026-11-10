"""StudySpace 2 — bilingual student library + GitHub-backed teacher dashboard.

The public catalog is read from GitHub, and teacher writes happen only after
server-side password authentication. GitHub credentials stay in st.secrets.
"""
from __future__ import annotations

import base64
import hashlib
import html
import hmac
import json
import mimetypes
import os
import re
import time
from collections import Counter
from pathlib import Path
from urllib.parse import quote, unquote, urlencode

import requests
import segno
import streamlit as st

from fulltext import FullText, render_pages
from github_store import GithubError, GithubStore
from portal_logic import (
    ALLOWED_EXTENSIONS, course_languages, display_course, human_size, parse_materials,
    safe_filename, slugify, upload_path, valid_slug,
)

st.set_page_config(page_title='StudySpace • Education Hub', page_icon='🟥', layout='wide', initial_sidebar_state='collapsed')
BASE = Path(__file__).resolve().parent
# Generated covers, slides and the search index; served at app/static/ (enableStaticServing).
STATIC = Path(os.environ.get('STUDYSPACE_STATIC') or BASE / 'static')
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
LANG_LABELS = {'ru': '🇷🇺 Русский', 'kz': '🇰🇿 Қазақша'}
TEACHING_LANGUAGES = {'ru': '🇷🇺 Только русский', 'kz': '🇰🇿 Тек қазақша', 'both': '🌐 На двух языках'}
OFFICE_PREVIEW = {'.pptx', '.ppt', '.docx', '.doc'}
OFFICE_VIEWER_LIMIT = 10 * 1024 * 1024  # Office Online viewer refuses larger Word/PowerPoint files
NEW_DAYS = 7  # how long an upload keeps its "new" badge
LOGIN_MAX_FAILS, LOGIN_WINDOW =5, 300  # 5 wrong passwords per 5 minutes, across all visitors
EMOJIS = ['📘', '💻', '☕', '🧩', '🗄️', '🛠️', '🌐', '📊', '🔬', '🧮', '🎨', '📐', '📚', '⚙️']

I18N = {
    'ru': {
        'home':'Раздел', 'landing':'Заглавная', 'library':'Библиотека', 'about':'О платформе', 'choose':'Выбор языка',
        'hero_head':'Учебные материалы в одном месте.', 'hero_sub':'Лекции и презентации на русском языке — для учёбы, повторения и самостоятельной работы.',
        'hero_tag':'ОБРАЗОВАТЕЛЬНАЯ ПЛАТФОРМА', 'browse':'Открыть библиотеку', 'courses':'Дисциплины',
        'course_sub':'Выбери предмет, чтобы посмотреть лекции и презентации.', 'open':'Открыть предмет',
        'materials':'материалов', 'lectures':'лекций', 'presentations':'презентаций',
        'empty_courses':'Здесь скоро появятся дисциплины', 'empty_desc':'Преподаватель добавит предметы и учебные материалы. Загляни сюда позже.',
        'catalog_head':'Библиотека материалов', 'catalog_sub':'Поиск по лекциям и презентациям на русском языке.',
        'search':'Найти материал', 'search_hint':'Введите тему или название файла', 'subject':'Дисциплина', 'all_subjects':'Все дисциплины',
        'kind':'Тип материала', 'all_kinds':'Любой тип', 'lectures_one':'Лекция', 'presentations_one':'Презентация',
        'empty_materials':'По выбранным фильтрам материалов нет.', 'open_item':'Открыть материал',
        'back':'← Назад в библиотеку', 'download':'↓ Скачать материал', 'unavailable':'Материал не найден или удалён.',
        'preview':'Этот формат можно скачать и открыть на своём устройстве.',
        'about_head':'О StudySpace', 'about_body':'Выбирай дисциплину, читай лекции, просматривай презентации и скачивай файлы. Для каждого языка материалы хранятся отдельно.',
        'no_preview':'Предпросмотр не удался. Попробуй скачать файл.', 'change_lang':'Сменить язык',
        'view':'Просмотр и скачивание', 'quick':'Удобно на компьютере и телефоне',
        'manage':'УПРАВЛЕНИЕ', 'teacher_panel':'Панель преподавателя', 'filters':'Фильтры',
        'note_title':'Твоя библиотека знаний', 'note_body':'Лекции, презентации и материалы для самостоятельной подготовки.',
        'offline':'Материалы временно недоступны. Обнови страницу немного позже.',
        'office_hint':'Если файл не отобразился, скачай его кнопкой ниже.',
        'nav_home':'Главная', 'nav_admin':'Преподавателю',
        'studied':'изучено', 'studied_title':'Изучено', 'mark_done':'✓  Отметить как изученное',
        'unmark_done':'✓  Изучено · снять отметку', 'in_text':'В тексте',
        'slides_loading':'Готовим слайды…', 'w_head':'Учиться проще, когда всё рядом', 'w_langs':'Язык обучения',
        'w_lead':'Лекции, презентации и материалы в одном месте. Выбери язык обучения.',
        'save_slide':'Слайд', 'resume':'Продолжаем со слайда {n}', 'from_start':'С начала', 'slide_of':'слайд {i} из {n}',
        'copy':'Копировать', 'copied':'Скопировано ✓', 'fullscreen':'На весь экран', 'slide_word':'слайд', 'deck_hint':'← → или свайп',
        'new_week':'новых за неделю', 'f_slides':'Слайдов', 'strip':'Лента слайдов',
        'theme':'Светлая / тёмная тема', 'menu':'Меню', 'to_top':'Наверх',
        'search_open':'Поиск', 'search_ph':'Найти предмет или материал…', 'search_empty':'Ничего не найдено',
        'course_word':'Предмет', 'prev':'Предыдущий', 'next':'Следующий',
        'f_course':'Предмет', 'f_kind':'Тип', 'f_format':'Формат', 'f_size':'Размер', 'f_lang':'Язык',
        'poster':'Плакат A4 с QR-кодом', 'poster_download':'↓ Скачать плакат (HTML)', 'print':'Печать / PDF',
        'poster_scan':'Все материалы — по QR-коду',
        'poster_hint':'Наведи камеру телефона на код, чтобы открыть лекции и презентации этого предмета.',
        'recent_title':'Недавно открытые', 'recent_sub':'Материалы, которые ты открывал на этом устройстве.',
        'new':'НОВОЕ', 'new_title':'Новые материалы',
        'back_home':'← Ко всем предметам', 'back_course':'← К предмету',
        'lectures_title':'Лекции', 'presentations_title':'Презентации',
        'share':'ПОДЕЛИТЬСЯ', 'share_title':'Ссылка на этот материал', 'qr_big':'⛶  QR на весь экран',
        'share_hint':'Отсканируй QR-код телефоном или скопируй ссылку.',
    },
    'kz': {
        'home':'Бөлім', 'landing':'Басты бет', 'library':'Кітапхана', 'about':'Платформа туралы', 'choose':'Тілді таңдау',
        'hero_head':'Оқу материалдары бір жерде.', 'hero_sub':'Қазақ тіліндегі дәрістер мен презентациялар — білім алу, қайталау және өзіндік жұмыс үшін.',
        'hero_tag':'БІЛІМ БЕРУ ПЛАТФОРМАСЫ', 'browse':'Кітапхананы ашу', 'courses':'Пәндер',
        'course_sub':'Дәрістер мен презентацияларды көру үшін пәнді таңда.', 'open':'Пәнді ашу',
        'materials':'материал', 'lectures':'дәріс', 'presentations':'презентация',
        'empty_courses':'Пәндер жақында қосылады', 'empty_desc':'Оқытушы пәндер мен оқу материалдарын қосады. Кейінірек қайта кір.',
        'catalog_head':'Оқу материалдарының кітапханасы', 'catalog_sub':'Қазақ тіліндегі дәрістер мен презентацияларды іздеу.',
        'search':'Материалды іздеу', 'search_hint':'Тақырыпты немесе файл атауын енгіз', 'subject':'Пән', 'all_subjects':'Барлық пәндер',
        'kind':'Материал түрі', 'all_kinds':'Барлық түрі', 'lectures_one':'Дәріс', 'presentations_one':'Презентация',
        'empty_materials':'Таңдалған сүзгілер бойынша материал табылмады.', 'open_item':'Материалды ашу',
        'back':'← Кітапханаға оралу', 'download':'↓ Материалды жүктеу', 'unavailable':'Материал табылмады немесе жойылған.',
        'preview':'Бұл форматты жүктеп алып, құрылғыда ашуға болады.',
        'about_head':'StudySpace туралы', 'about_body':'Пәнді таңда, дәрістерді оқы, презентацияларды қара және файлдарды жүктеп ал. Әр тілге арналған материалдар бөлек сақталады.',
        'no_preview':'Алдын ала қарау мүмкін емес. Файлды жүктеп көр.', 'change_lang':'Тілді өзгерту',
        'view':'Қарау және жүктеу', 'quick':'Компьютер мен телефонда ыңғайлы',
        'manage':'БАСҚАРУ', 'teacher_panel':'Оқытушы панелі', 'filters':'Сүзгілер',
        'note_title':'Сенің білім кітапханаң', 'note_body':'Дәрістер, презентациялар және өзіндік дайындыққа арналған материалдар.',
        'offline':'Материалдар уақытша қолжетімсіз. Бетті сәл кейінірек жаңартып көр.',
        'office_hint':'Файл көрсетілмесе, оны төмендегі батырмамен жүктеп ал.',
        'nav_home':'Басты бет', 'nav_admin':'Оқытушыға',
        'studied':'оқылды', 'studied_title':'Оқылды', 'mark_done':'✓  Оқылды деп белгілеу',
        'unmark_done':'✓  Оқылды · белгіні алу', 'in_text':'Мәтінде',
        'slides_loading':'Слайдтар дайындалуда…', 'w_head':'Бәрі қолыңда болса, оқу оңай', 'w_langs':'Оқу тілі',
        'w_lead':'Дәрістер, презентациялар және материалдар бір жерде. Оқу тілін таңда.',
        'save_slide':'Слайд', 'resume':'{n}-слайдтан жалғастырамыз', 'from_start':'Басынан', 'slide_of':'{i}/{n} слайд',
        'copy':'Көшіру', 'copied':'Көшірілді ✓', 'fullscreen':'Толық экран', 'slide_word':'слайд', 'deck_hint':'← → немесе свайп',
        'new_week':'аптадағы жаңа', 'f_slides':'Слайд', 'strip':'Слайдтар таспасы',
        'theme':'Ашық / қараңғы режим', 'menu':'Мәзір', 'to_top':'Жоғары',
        'search_open':'Іздеу', 'search_ph':'Пән немесе материал іздеу…', 'search_empty':'Ештеңе табылмады',
        'course_word':'Пән', 'prev':'Алдыңғы', 'next':'Келесі',
        'f_course':'Пән', 'f_kind':'Түрі', 'f_format':'Формат', 'f_size':'Көлемі', 'f_lang':'Тілі',
        'poster':'QR-коды бар A4 плакат', 'poster_download':'↓ Плакатты жүктеу (HTML)', 'print':'Басып шығару / PDF',
        'poster_scan':'Барлық материал — QR-код арқылы',
        'poster_hint':'Осы пәннің дәрістері мен презентацияларын ашу үшін телефон камерасын кодқа бағытта.',
        'recent_title':'Соңғы ашылғандар', 'recent_sub':'Осы құрылғыда ашқан материалдарың.',
        'new':'ЖАҢА', 'new_title':'Жаңа материалдар',
        'back_home':'← Барлық пәндерге', 'back_course':'← Пәнге оралу',
        'lectures_title':'Дәрістер', 'presentations_title':'Презентациялар',
        'share':'БӨЛІСУ', 'share_title':'Осы материалға сілтеме', 'qr_big':'⛶  QR-код толық экранда',
        'share_hint':'QR-кодты телефонмен сканерле немесе сілтемені көшір.',
    },
}


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def secret(name: str, default: str = '') -> str:
    try:
        value = st.secrets.get(name, default)
        return str(value).strip() if value is not None else default
    except Exception:
        return default


def settings() -> tuple[str, str, str]:
    return (secret('GITHUB_REPO', 'olenver-04/StudySpace'), secret('GITHUB_BRANCH', 'main'), secret('GITHUB_TOKEN'))


@st.cache_data(ttl=45, show_spinner=False)
def github_data(repo: str, branch: str, token: str) -> tuple[dict, list[dict]]:
    github = GithubStore(repo, branch, token)
    return github.read_catalog(), github.tree()


@st.cache_data(ttl=3600, show_spinner=False)
def material_bytes(repo: str, branch: str, path: str, sha: str) -> bytes:
    return GithubStore(repo, branch).raw_bytes(path, sha)


@st.cache_resource
def login_failures() -> list[float]:
    # One list shared by every visitor, so reloading the page does not reset the limit.
    return []


def login_wait() -> int:
    """Seconds until the next login attempt is allowed (0 = allowed now)."""
    fails = login_failures()
    now = time.time()
    fails[:] = [f for f in fails if now - f < LOGIN_WINDOW]
    return int(fails[0] + LOGIN_WINDOW - now) + 1 if len(fails) >= LOGIN_MAX_FAILS else 0


@st.cache_data(ttl=600, show_spinner=False)
def recent_uploads(repo: str, branch: str, token: str, since: str) -> dict[str, str]:
    return GithubStore(repo, branch, token).recent_files(since)


def mark_new(materials: list[dict]) -> None:
    """Sets item['new'] to the upload date for files added in the last NEW_DAYS days."""
    repo, branch, token = settings()
    since = time.strftime('%Y-%m-%dT00:00:00Z', time.gmtime(time.time() - NEW_DAYS * 86400))
    added = {}
    # Up to ~30 API calls per 10 min: only with a token, or it would eat the 60/h anonymous
    # limit that the catalog itself needs.
    if token:
        try:
            added = recent_uploads(repo, branch, token, since)
        except Exception:  # noqa: BLE001 — also covers a stale github_store module after a Cloud update
            pass  # the badge is a nicety; never break the catalog over it
    for item in materials:
        item['new'] = added.get(item['path'], '')


def refresh_data() -> None:
    github_data.clear()
    material_bytes.clear()
    recent_uploads.clear()


def retrieve() -> tuple[dict, list[dict], str | None]:
    repo, branch, token = settings()
    try:
        config, tree = github_data(repo, branch, token)
        if not isinstance(config.get('courses'), list):
            raise GithubError('Неверный формат catalog.json.')
        materials = parse_materials(tree, config['courses'])
        mark_new(materials)
        return config, materials, None
    except (GithubError, ValueError, KeyError, TypeError) as exc:
        # A failed remote read must never show made-up remote materials.
        try:
            local = json.loads((BASE / 'catalog.json').read_text(encoding='utf-8'))
        except Exception:
            local = {'site_name': 'StudySpace', 'courses': []}
        return local, [], str(exc)


def route(page: str, *, lang: str | None = None, course: str = '', material: str = '') -> None:
    if st.session_state.get('lang') in LANG_LABELS:
        st.session_state['ui_lang'] = st.session_state['lang']
    if lang is not None:
        st.session_state['lang'] = lang
    st.session_state['page'] = page
    st.session_state['course'] = course
    st.session_state['material'] = material
    # A keyed selectbox keeps its old value across reruns; synchronize it with navigation.
    current_lang = st.session_state.get('lang', '')
    if page == 'library' and current_lang in LANG_LABELS:
        st.session_state[f'course_selector_{current_lang}'] = course or 'all'
    st.query_params.clear()
    if st.session_state.get('lang') in LANG_LABELS:
        st.query_params['lang'] = st.session_state['lang']
    if page == 'reader' and material:
        st.query_params['material'] = material
    if page == 'course' and course:
        st.query_params['course'] = course
    if page in ('library', 'about'):
        st.query_params['view'] = page  # also lets fx.js notice the page change and scroll to top
    st.rerun()


THEMES = {
    'light': 'color-scheme: light; --paper: #F4F2EE; --paper-2: #EAE7E1; --white: #FFFFFF; --ink: #111111; --ink-2: #3A3A3A; '
             '--muted: #6E6B66; --rule: #111111; --rule-soft: #CFCAC2; --red: #E3241B;',
    'dark': 'color-scheme: dark; --paper: #0F0F0E; --paper-2: #1A1918; --white: #171615; --ink: #F1EEE8; --ink-2: #C9C5BE; '
            '--muted: #8F8A83; --rule: #F1EEE8; --rule-soft: #34322F; --red: #FF4136;',
}


def theme_css(saved: object) -> str:
    """System preference by default; a saved choice (cookie) is applied server-side so there is no flash.

    fx.js flips .ss-dark / .ss-light on <html> for an instant switch; those classes beat the rules below.
    """
    dark, light = THEMES['dark'], THEMES['light']
    css = (f'@media (prefers-color-scheme: dark) {{:root:not(.ss-light) {{{dark}}}}} '
           f':root.ss-dark {{{dark}}} :root.ss-light {{{light}}} ')
    if saved == 'dark':
        css += f':root:not(.ss-light) {{{dark}}}'
    elif saved == 'light':
        css += f':root:not(.ss-dark) {{{light}}}'
    return css


def style() -> None:
    try:
        saved = st.context.cookies.get('ss_theme')
    except Exception:
        saved = None
    st.markdown('<style>'+(BASE/'assets/style.css').read_text(encoding='utf-8')+theme_css(saved)+'</style>', unsafe_allow_html=True)


def effects() -> None:
    # Hidden iframe; the script copies itself into the main page once. It lives in the main area:
    # a collapsed sidebar (default on phones) does not render its contents, so the script would never run.
    st.iframe('<script>'+(BASE/'assets/fx.js').read_text(encoding='utf-8')+'</script>', height=1)


PLURALS = {
    'ru': {'slides': ('слайд', 'слайда', 'слайдов'), 'materials': ('материал', 'материала', 'материалов'),
           'pres': ('презентация', 'презентации', 'презентаций'), 'courses': ('предмет', 'предмета', 'предметов')},
    'kz': {'slides': ('слайд',) * 3, 'materials': ('материал',) * 3, 'pres': ('презентация',) * 3, 'courses': ('пән',) * 3},
}


def plural(n: int, lang: str, word: str) -> str:
    """1 слайд, 2 слайда, 5 слайдов; Kazakh nouns do not change after numbers."""
    one, few, many = PLURALS.get(lang, PLURALS['ru'])[word]
    if n % 100 in (11, 12, 13, 14):
        return many
    return one if n % 10 == 1 else few if n % 10 in (2, 3, 4) else many


def mixed() -> bool:
    """True once any lecture exists; until then the site is presentation-only and hides the split."""
    return st.session_state.get('mixed', False)


def slides(item: dict) -> int:
    return fulltext_index().pages.get(item.get('sha', ''), 0)


def cover_url(item: dict) -> str:
    """Static URL of the rendered first slide, or '' while it is not ready (or not a PDF)."""
    name = f'{item["sha"]}.webp'
    return f'app/static/thumbs/{name}' if (STATIC / 'thumbs' / name).exists() else ''


def accent(items: list[dict]) -> str:
    """Most common cover colour of these materials ('' until covers are analysed)."""
    colors = Counter(c for m in items if (c := fulltext_index().colors.get(m.get('sha', ''))))
    color = colors.most_common(1)[0][0] if colors else ''
    return color if re.fullmatch(r'#[0-9a-f]{6}', color) else ''


def use_accent(color: str) -> None:
    """Colours course-specific details (progress, numbers, hover frames, viewer) for this page."""
    if color:
        st.markdown(f'<style>:root {{--accent: {color}}}</style>', unsafe_allow_html=True)


def material_meta(item: dict, lang: str) -> str:
    n = slides(item)
    return ' · '.join(([f'{n} {plural(n, lang, "slides")}'] if n else []) + [item['extension'].lstrip('.').upper(), human_size(item['size'])])


def words(text: str) -> str:
    """Headline split into words that rise one after another (see .w in style.css).

    The red dot lives inside the last word, so it can never wrap onto a line of its own.
    """
    parts = text.split()
    return ' '.join(f'<span class="w" style="--i:{i}">{esc(w)}' + ('<span class="dot">.</span>' if i == len(parts) - 1 else '') + '</span>'
                    for i, w in enumerate(parts))


def header(title: str, subtitle: str = '', eyebrow: str = '') -> None:
    st.markdown(
        '<div class="heading-block">'
        + (f'<span class="eyebrow">{esc(eyebrow)}</span>' if eyebrow else '')
        + f'<h2>{esc(title)}</h2>'
        + (f'<p>{esc(subtitle)}</p>' if subtitle else '') + '</div>', unsafe_allow_html=True,
    )


def badge(text: str, variant: str = '') -> str:
    return f'<span class="badge-text {esc(variant)}">{esc(text)}</span>'


def key_of(*parts: str) -> str:
    # Widget/container keys become CSS classes, so file paths are hashed into a safe token.
    return hashlib.md5('|'.join(parts).encode('utf-8')).hexdigest()[:12]


def initial_route(materials: list[dict]) -> None:
    if 'page' in st.session_state:
        return
    lang = st.query_params.get('lang', '')
    material_id = st.query_params.get('material', '')
    found = next((i for i in materials if i['id'] == material_id), None)
    course_id = st.query_params.get('course', '')
    if found:
        st.session_state.update(page='reader', lang=found['lang'], course=found['course_id'], material=material_id)
    elif lang in LANG_LABELS and course_id:
        st.session_state.update(page='course', lang=lang, course=course_id, material='')
    elif lang in LANG_LABELS and st.query_params.get('view') in ('library', 'about'):
        st.session_state.update(page=st.query_params['view'], lang=lang, course='', material='')
    elif lang in LANG_LABELS:
        st.session_state.update(page='home', lang=lang, course='', material='')
    else:
        st.session_state.update(page='welcome', lang='', course='', material='')


def ui_lang() -> str:
    """Interface language: the chosen section, or on the welcome page the RU/KZ toggle (default RU)."""
    lang = st.session_state.get('lang', '')
    return lang if lang in LANG_LABELS else st.session_state.get('ui_lang', 'ru')


def switch_language(config: dict, materials: list[dict], other: str) -> None:
    """Same page in the other language. route() reruns, so the first matching branch wins."""
    page = st.session_state.get('page', 'home')
    if page in ('home', 'library', 'about', 'admin'):
        route(page, lang=other)
    course_id = st.session_state.get('course', '')
    course = next((c for c in config['courses'] if c.get('id') == course_id), None)
    if page in ('course', 'reader') and course and other in course_languages(course):
        if page == 'reader':
            # The counterpart is the material at the same position in the course (Тема 1.1 ↔ Тақырып 1.1);
            # order matches the reader and course page: lectures first, then natural title order.
            def order(lang: str) -> list[dict]:
                return sorted((m for m in materials if m['course_id'] == course_id and m['lang'] == lang),
                              key=lambda m: m['kind'] != 'lectures')
            here, there = order(st.session_state.get('lang', '')), order(other)
            position = next((i for i, m in enumerate(here) if m['id'] == st.session_state.get('material')), 0)
            if there:
                route('reader', lang=other, course=course_id, material=there[min(position, len(there) - 1)]['id'])
        route('course', lang=other, course=course_id)
    route('home', lang=other)


def topnav(config: dict, materials: list[dict]) -> None:
    """Top bar: brand, sections, teacher link, language switch. Replaces the old sidebar."""
    lang = st.session_state.get('lang', '')
    t = I18N[ui_lang()]
    page = st.session_state.get('page', 'welcome')
    current = {'course': 'home', 'reader': 'library'}.get(page, page)
    links = [('home', t['nav_home']), ('library', t['library']), ('about', t['about'])] if lang in LANG_LABELS else []
    links.append(('admin', t['nav_admin']))
    other = {'ru': 'kz', 'kz': 'ru'}[ui_lang()]
    with st.container(key='topnav'):
        # brand | search | links (desktop) | theme | language | menu (phones)
        cols = st.columns([3.2, 1.4] + [1] * len(links) + [0.35, 0.7, 0.7], vertical_alignment='center', gap='small')
        if cols[0].button('StudySpace', type='tertiary', key='nav-brand'):
            route('welcome', lang='')
        # Search and theme are plain HTML buttons handled by fx.js, so they never cause a Streamlit rerun.
        cols[1].markdown(f'<button class="ss-search" type="button" aria-label="{esc(t["search_open"])}">'
                         f'<span class="ss-search-label">{esc(t["search_open"])}</span><span class="ss-search-icon" aria-hidden="true">⌕</span>'
                         f'<kbd>/</kbd></button>', unsafe_allow_html=True)
        for col, (target, label) in zip(cols[2:], links):
            with col, st.container(key='navlink-'+target):
                if st.button(label, type='primary' if current == target else 'tertiary', key='nav-'+target):
                    route(target)
        cols[-3].markdown(f'<button class="ss-theme" type="button" aria-label="{esc(t["theme"])}" title="{esc(t["theme"])}">'
                          '<span aria-hidden="true">◐</span></button>', unsafe_allow_html=True)
        if cols[-2].button(other.upper(), key='nav-lang', help=t['change_lang']):
            if lang in LANG_LABELS:
                switch_language(config, materials, other)
            else:  # welcome page / teacher page before a section is chosen: just the interface language
                st.session_state['ui_lang'] = other
                st.rerun()
        with cols[-1], st.container(key='nav-menu'), st.popover(t['menu'], use_container_width=True):
            for target, label in links:
                if st.button(('● ' if current == target else '')+label, key='menu-'+target, type='tertiary', use_container_width=True):
                    route(target)


def row(key: str, number: int, title: str, *, kicker: str = '', sub: str = '', meta: str = '',
        new: str = '', big: bool = False, button: str = '', button_key: str = '', done: bool = False,
        extra: str = '', thumb: str = '', color: str = '') -> bool:
    """One line of a modernist index list; returns True when its button is pressed."""
    with st.container(key='row_'+key):
        left, right = st.columns([5, 1.25], vertical_alignment='center')
        left.markdown(
            f'<div class="row{" is-done" if done else ""}{" has-thumb" if thumb else ""}"'
            + (f' style="--accent:{color}"' if color else '') + f'><span class="row-n">{"✓" if done else f"{number:02d}"}</span>'
            + (f'<img class="row-thumb" src="{esc(thumb)}" alt="" loading="lazy">' if thumb else '') + '<div class="row-body">'
            + (f'<span class="row-kicker">{esc(kicker)}</span>' if kicker else '')
            + f'<b class="row-title{" big" if big else ""}">{esc(title)}</b>'
            + (f'<span class="row-sub">{esc(sub)}</span>' if sub else '') + extra
            + '</div><span class="row-meta">'
            + (f'<span class="tag-new">{esc(new)}</span>' if new else '') + f'{esc(meta)}</span></div>',
            unsafe_allow_html=True,
        )
        return right.button(button, key=button_key, type='tertiary', use_container_width=True)


def end_list() -> None:
    st.markdown('<div class="list-end"></div>', unsafe_allow_html=True)


def material_row(item: dict, lang: str, prefix: str, number: int) -> None:
    t = I18N[lang]
    kind = t['lectures_one'] if item['kind'] == 'lectures' else t['presentations_one']
    if row(f'{prefix}_{key_of(item["id"])}', number, item['title'],
           kicker=display_course(item['course'], lang) + (f' — {kind}' if mixed() else ''),
           meta=material_meta(item, lang), thumb=cover_url(item),
           new=t['new'] if item.get('new') else '', button=t['open_item']+' →', button_key=f'item_{prefix}_{item["id"]}',
           done=is_done(item)):
        route('reader', course=item['course_id'], material=item['id'])


def material_card(item: dict, lang: str, prefix: str, number: int) -> None:
    t = I18N[lang]
    cover, done = cover_url(item), is_done(item)
    total, at = slides(item), positions().get(key_of(item['id']), 0)
    resume = 1 < at <= total and not done
    badges = (f'<span class="card-badge done">✓ {esc(t["studied_title"])}</span>' if done else '') + \
             (f'<span class="card-badge new">{esc(t["new"])}</span>' if item.get('new') else '')
    with st.container(key=f'card_{prefix}_{key_of(item["id"])}'):
        st.markdown(
            '<div class="card"><div class="card-cover">'
            + (f'<img src="{esc(cover)}" alt="" loading="lazy">' if cover
               else f'<div class="card-ph"><b>{number:02d}</b><span>{esc(item["title"])}</span></div>')
            + f'<div class="card-badges">{badges}</div>'
            + (f'<div class="card-pos"><i style="width:{100 * at / total:.1f}%"></i></div>' if resume else '') + '</div>'
            f'<div class="card-body"><span class="card-n">{"✓" if done else f"{number:02d}"}</span>'
            f'<b class="card-title">{esc(item["title"])}</b><span class="card-meta">'
            + (f'<em>{esc(t["slide_of"].format(i=at, n=total))}</em> · ' if resume else '')
            # "slide 5 of 10" already says how long it is, so the slide total is dropped next to it.
            + (esc(item['extension'].lstrip('.').upper() + ' · ' + human_size(item['size'])) if resume else esc(material_meta(item, lang)))
            + '</span></div></div>',
            unsafe_allow_html=True,
        )
        if st.button(t['open_item']+' →', key=f'item_{prefix}_{item["id"]}', type='tertiary', use_container_width=True):
            route('reader', course=item['course_id'], material=item['id'])


def material_grid(items: list[dict], lang: str, prefix: str, per_row: int = 3) -> None:
    # One st.columns per row keeps reading order when columns stack on phones.
    for start in range(0, len(items), per_row):
        cols = st.columns(per_row, gap='medium')
        for offset, item in enumerate(items[start:start + per_row]):
            with cols[offset]:
                material_card(item, lang, prefix, start + offset + 1)


def slide_strip(items: list[dict], label: str) -> None:
    """Slowly moving ribbon of slide covers; plain links (a click opens the material)."""
    covers = [(m, cover_url(m)) for m in items]
    covers = [(m, c) for m, c in covers if c][:16]
    if len(covers) < 4:
        return
    cells = ''.join(
        f'<a class="strip-item" href="?{esc(urlencode({"lang": m["lang"], "material": m["id"]}))}" target="_self">'
        f'<img src="{esc(c)}" alt="{esc(m["title"])}" loading="lazy"><span>{esc(m["title"])}</span></a>' for m, c in covers)
    st.markdown(f'<div class="strip" role="region" aria-label="{esc(label)}" style="--n:{len(covers)}">'
                f'<div class="strip-track">{cells}<div class="strip-copy" aria-hidden="true">{cells}</div></div></div>',
                unsafe_allow_html=True)


def material_list(items: list[dict], lang: str, prefix: str) -> None:
    for n, item in enumerate(items, 1):
        material_row(item, lang, prefix, n)
    end_list()


def welcome(materials: list[dict] | None = None) -> None:
    ui = ui_lang()
    t, o = I18N[ui], I18N['kz' if ui == 'ru' else 'ru']
    # Main text in the interface language; the other language stays as a quiet second line.
    st.markdown(
        '<section class="hero hero-plain">'
        f'<h1>{words(t["w_head"])}</h1>'
        f'<p class="hero-lead">{esc(t["w_lead"])}<br><span>{esc(o["w_lead"])}</span></p></section>',
        unsafe_allow_html=True,
    )
    slide_strip(materials or [], t['strip'])
    header(f'{t["w_langs"]} / {o["w_langs"]}', '', '01')
    sections = [('ru', 'Русский', 'Лекции, презентации и материалы для самостоятельной работы на русском языке.', 'Открыть раздел'),
                ('kz', 'Қазақша', 'Қазақ тіліндегі дәрістер, презентациялар және өзіндік жұмысқа арналған материалдар.', 'Бөлімді ашу')]
    for col, (code, title, sub, label) in zip(st.columns(2, gap='small'), sections):
        with col, st.container(key='langpanel_'+code):
            st.markdown(f'<div class="langpanel"><span class="lp-code">{code.upper()}</span>'
                        f'<b>{esc(title)}<span class="dot">.</span></b><p>{esc(sub)}</p></div>', unsafe_allow_html=True)
            if st.button(label+'  →', key='choose_'+code, type='primary', use_container_width=True):
                route('home', lang=code)


def positions() -> dict[str, int]:
    """Last viewed slide per material (hashed id), from the ss_pos cookie that the viewer keeps up to date."""
    if 'positions' not in st.session_state:
        try:
            raw = st.context.cookies.get('ss_pos')
        except Exception:
            raw = None
        found = {}
        for pair in (unquote(raw).split('|') if isinstance(raw, str) else []):
            key, _, slide = pair.partition(':')
            if re.fullmatch(r'[0-9a-f]{12}', key) and slide.isdecimal():
                found[key] = int(slide)
        st.session_state['positions'] = found
    return st.session_state['positions']


def done_ids() -> list[str]:
    """Hashes of materials marked as studied. Loaded once from the cookie that fx.js keeps in sync."""
    if 'done' not in st.session_state:
        try:
            raw = st.context.cookies.get('ss_done')
        except Exception:
            raw = None
        saved = unquote(raw).split('|') if isinstance(raw, str) else []
        st.session_state['done'] = [h for h in saved if re.fullmatch(r'[0-9a-f]{12}', h)][:280]
    return st.session_state['done']


def is_done(item: dict) -> bool:
    return key_of(item['id']) in done_ids()


def toggle_done(item: dict) -> None:
    mark, current = key_of(item['id']), done_ids()
    # 280 x 13 chars stays under the 4 KB cookie limit.
    st.session_state['done'] = [h for h in current if h != mark] if mark in current else ([mark] + current)[:280]


def progress_bar(done: int, total: int, label: str) -> str:
    pct = round(100 * done / total) if total else 0
    return (f'<div class="progress"><div class="progress-track" role="progressbar" aria-valuenow="{pct}" '
            f'aria-valuemin="0" aria-valuemax="100"><i style="width:{pct}%"></i></div>'
            f'<span>{done}/{total} {esc(label)}</span></div>')


def recent_ids() -> list[str]:
    """Materials opened in this visit first, then earlier visits (cookie written by fx.js)."""
    try:
        raw = st.context.cookies.get('ss_recent')
    except Exception:
        raw = None
    saved = unquote(raw).split('|') if isinstance(raw, str) else []
    ids = st.session_state.get('recent', []) + saved
    return [i for n, i in enumerate(ids) if i and i not in ids[:n]]


def home(config: dict, materials: list[dict], lang: str) -> None:
    t = I18N[lang]
    visible_courses = [c for c in config['courses'] if lang in course_languages(c)]
    visible_ids = {c['id'] for c in visible_courses}
    visible = [m for m in materials if m['lang'] == lang and m['course_id'] in visible_ids]
    lectures = sum(i['kind'] == 'lectures' for i in visible)
    headline = 'Знания ближе, чем кажется' if lang == 'ru' else 'Білімнің бәрі осында'
    st.markdown(
        f'<section class="hero hero-plain">'
        f'<h1>{words(headline)}</h1><p class="hero-lead">{esc(t["hero_sub"])}</p></section>',
        unsafe_allow_html=True,
    )
    if st.button(t['browse']+'  →', type='primary', key='hero_browse'):
        route('library')
    total_slides = sum(slides(m) for m in visible)
    fresh_count = sum(bool(m.get('new')) for m in visible)
    stats = [(len(visible_courses), plural(len(visible_courses), lang, 'courses')),
             (len(visible), plural(len(visible), lang, 'materials'))]
    stats += [(lectures, t['lectures']), (len(visible) - lectures, t['presentations'])] if mixed() else []
    stats += [(total_slides, plural(total_slides, lang, 'slides'))] if total_slides else []
    stats += [(fresh_count, t['new_week'])]
    st.markdown('<div class="stats stats-auto">' + ''.join(f'<div><b data-count="{v}">{v:02d}</b><span>{esc(label)}</span></div>'
                                                for v, label in stats) + '</div>', unsafe_allow_html=True)
    slide_strip(sorted(visible, key=lambda m: m.get('new') or '', reverse=True), t['strip'])
    by_id = {m['id']: m for m in visible}
    recent = [by_id[i] for i in recent_ids() if i in by_id][:4]
    if recent:
        header(t['recent_title'], t['recent_sub'], '↺')
        material_grid(recent[:3], lang, 'recent')
    header(t['courses'], t['course_sub'], f'{len(visible_courses):02d}')
    if not visible_courses:
        empty(t['empty_courses'], t['empty_desc'])
        return
    for n, course in enumerate(visible_courses, 1):
        own = [m for m in visible if m['course_id'] == course['id']]
        lect = sum(m['kind'] == 'lectures' for m in own)
        fresh_count = sum(bool(m.get('new')) for m in own)
        studied = sum(is_done(m) for m in own)
        n_slides = sum(slides(m) for m in own)
        sub = (f'{lect} {t["lectures"]} · {len(own) - lect} {t["presentations"]}' if mixed()
               else f'{len(own)} {plural(len(own), lang, "pres")}' + (f' · {n_slides} {plural(n_slides, lang, "slides")}' if n_slides else ''))
        first_cover = next((cover_url(m) for m in own if cover_url(m)), '')
        if row('course_'+course['id'], n, display_course(course, lang), big=True, sub=sub, thumb=first_cover, color=accent(own),
               extra=progress_bar(studied, len(own), t['studied']) if studied else '',
               meta=f'{course.get("icon", "")}', new=f'+{fresh_count} {t["new"]}' if fresh_count else '',
               button=t['open']+' →', button_key=f'course_{lang}_{course["id"]}'):
            route('course', course=course['id'])
    end_list()


def course_page(config: dict, materials: list[dict], lang: str) -> None:
    t = I18N[lang]
    courses = [c for c in config['courses'] if lang in course_languages(c)]
    index = next((i for i, c in enumerate(courses) if c['id'] == st.session_state.get('course')), None)
    if st.button(t['back_home'], key='back_course_page', type='tertiary'):
        route('home')
    if index is None:
        st.warning(t['unavailable'])
        return
    course = courses[index]
    own = [m for m in materials if m['lang'] == lang and m['course_id'] == course['id']]
    groups = [(t['lectures_title'], [m for m in own if m['kind'] == 'lectures']),
              (t['presentations_title'], [m for m in own if m['kind'] == 'presentations'])]
    fresh = sum(bool(m.get('new')) for m in own)
    n_slides = sum(slides(m) for m in own)
    facts = (''.join(f'<div><b>{len(items):02d}</b><span>{esc(title)}</span></div>' for title, items in groups) if mixed()
             else f'<div><b>{len(own):02d}</b><span>{esc(plural(len(own), lang, "pres"))}</span></div>')
    facts += f'<div><b>{n_slides}</b><span>{esc(plural(n_slides, lang, "slides"))}</span></div>' if n_slides else ''
    facts += f'<div class="fact-new"><b>{fresh:02d}</b><span>{esc(t["new"])}</span></div>' if fresh else ''
    studied = sum(is_done(m) for m in own)
    facts += f'<div><b>{studied:02d}<small>/{len(own):02d}</small></b><span>{esc(t["studied_title"])}</span></div>'
    use_accent(accent(own))
    # A fanned stack of the course's first covers next to the title (hidden on phones).
    covers = [c for c in (cover_url(m) for m in own) if c][:3]
    fan = (''.join(f'<img src="{esc(c)}" alt="" style="--n:{n}">' for n, c in enumerate(covers))
           if len(covers) >= 2 else '')
    st.markdown(
        f'<section class="course-hero hero-plain">' + (f'<div class="course-fan" aria-hidden="true">{fan}</div>' if fan else '')
        + f'<h1>{words(display_course(course, lang))}</h1><div class="stats">{facts}</div>'
        f'{progress_bar(studied, len(own), t["studied"]) if own else ""}</section>',
        unsafe_allow_html=True,
    )
    if not own:
        empty(t['empty_materials'], t['empty_desc'])
        return
    if st.button(t['poster']+'  →', key='poster', type='secondary'):
        poster_dialog(poster_html(course, lang, groups[0][1] + groups[1][1], index + 1, len(courses)),
                      f'StudySpace-{course["id"]}-{lang}.html', t['poster_download'])
    if not mixed():
        st.markdown('<div class="grid-gap"></div>', unsafe_allow_html=True)
        material_grid(groups[1][1], lang, 'course')
        return
    for title, items in groups:
        if items:
            header(title, '', f'{len(items):02d}')
            material_grid(items, lang, 'course')


def empty(title: str, subtitle: str) -> None:
    st.markdown(f'<div class="empty-state"><span class="empty-mark">—</span><h3>{esc(title)}</h3><p>{esc(subtitle)}</p></div>', unsafe_allow_html=True)


def library(config: dict, materials: list[dict], lang: str) -> None:
    t = I18N[lang]
    header(t['catalog_head'], t['catalog_sub'], LANG_LABELS[lang].split()[0])
    courses = [c for c in config['courses'] if lang in course_languages(c)]
    if not courses:
        empty(t['empty_courses'], t['empty_desc'])
        return
    options = ['all']+[c['id'] for c in courses]
    if st.session_state.get(f'course_selector_{lang}', 'all') not in options:
        st.session_state[f'course_selector_{lang}'] = 'all'
    current = st.session_state.get('course', '')
    if current not in options:
        current = 'all'
    with st.container(key='filters'):
        a, b, *rest = st.columns([1.5, 1, 1] if mixed() else [1.5, 1], gap='medium')
        with a:
            query = st.text_input(t['search'], placeholder=t['search_hint'], key=f'catalog_search_{lang}')
        with b:
            selected_course = st.selectbox(t['subject'], options, index=options.index(current),
                                           format_func=lambda slug: t['all_subjects'] if slug == 'all' else display_course(next(c for c in courses if c['id'] == slug), lang),
                                           key=f'course_selector_{lang}')
        kind = 'all'
        if rest:
            with rest[0]:
                kind = st.selectbox(t['kind'], ['all', 'lectures', 'presentations'],
                                    format_func=lambda key: {'all':t['all_kinds'], 'lectures':t['lectures_one'], 'presentations':t['presentations_one']}[key],
                                    key=f'kind_selector_{lang}')
    query = query.strip().casefold()
    filtered = [m for m in materials if m['lang'] == lang and (selected_course == 'all' or m['course_id'] == selected_course)
                and (kind == 'all' or m['kind'] == kind)
                and (not query or query in (m['title']+' '+display_course(m['course'],lang)+' '+m['filename']).casefold())]
    st.markdown(f'<div class="result-count"><b>{len(filtered):02d}</b> {esc(plural(len(filtered), lang, "materials"))}</div>', unsafe_allow_html=True)
    if not filtered:
        empty(t['empty_materials'], t['course_sub'])
        return
    material_list(filtered, lang, 'library')


def reader(materials: list[dict], lang: str) -> None:
    t = I18N[lang]
    item_id = st.session_state.get('material', '')
    item = next((m for m in materials if m['id'] == item_id), None)
    if not item:
        st.warning(t['unavailable'])
        if st.button(t['back']):
            route('library')
        return
    st.session_state['recent'] = [item['id']] + [i for i in st.session_state.get('recent', []) if i != item['id']][:7]
    if item['lang'] != lang:
        lang = item['lang']; t = I18N[lang]
    kind = t['lectures_one'] if item['kind'] == 'lectures' else t['presentations_one']
    with st.container(key='crumbs'):
        a, b, c = st.columns(3, vertical_alignment='center')
        if a.button(t['nav_home'], key='crumb_home', type='tertiary'):
            route('home', lang=lang)
        if b.button(display_course(item['course'], lang), key='crumb_course', type='tertiary'):
            route('course', lang=lang, course=item['course_id'])
        c.markdown(f'<span class="crumb-current">{esc(item["title"])}</span>', unsafe_allow_html=True)
    # Same order as the course page: lectures first, then presentations.
    siblings = sorted((m for m in materials if m['course_id'] == item['course_id'] and m['lang'] == lang),
                      key=lambda m: m['kind'] != 'lectures')
    position = next(i for i, m in enumerate(siblings) if m['id'] == item['id'])
    header(item['title'], '', f'{position + 1:02d}')
    view, side = st.columns([2.6, 1], gap='large')
    with side:
        facts = ([(t['f_course'], display_course(item['course'], lang))] + ([(t['f_kind'], kind)] if mixed() else [])
                 + ([(t['f_slides'], str(slides(item)))] if slides(item) else [])
                 + [(t['f_format'], item['extension'].lstrip('.').upper()), (t['f_size'], human_size(item['size'])),
                    (t['f_lang'], LANG_LABELS[lang])])
        st.markdown('<dl class="facts">' + ''.join(f'<div><dt>{esc(k)}</dt><dd>{esc(v)}</dd></div>' for k, v in facts)
                    + (f'<div><dt>{esc(t["new"])}</dt><dd><span class="tag-new">{esc(item["new"])}</span></dd></div>' if item.get('new') else '')
                    + f'<div><dt>№</dt><dd>{position + 1:02d} / {len(siblings):02d}</dd></div></dl>', unsafe_allow_html=True)
    repo, branch, _ = settings()
    try:
        filedata = material_bytes(repo, branch, item['path'], item['sha'])
    except GithubError as exc:
        st.error(str(exc))
        return
    suffix = item['extension']
    use_accent(accent(siblings))
    with view:
        if suffix == '.pdf':
            try:
                with st.spinner(t['slides_loading']):
                    count = render_pages(filedata, STATIC / 'slides' / item['sha'])
            except Exception:  # damaged or unusual PDF: the browser's own viewer may still cope
                count = 0
            if count:
                deck(item, count, t)
            else:
                try:
                    st.pdf(filedata, height=760)
                except Exception:
                    st.info(t['no_preview'])
        elif suffix in ('.md', '.txt'):
            with st.container(key='textdoc'):
                text = filedata.decode('utf-8-sig', errors='replace')
                if suffix == '.md':
                    st.markdown(text)
                else:
                    st.text(text)
        elif suffix == '.html':
            # A data: URL runs in an opaque origin, so scripts in an uploaded file cannot reach this app
            # (an HTML string would be embedded same-origin and could click admin buttons).
            st.iframe('data:text/html;charset=utf-8;base64,'+base64.b64encode(filedata).decode('ascii'), height=720)
        elif suffix in OFFICE_PREVIEW and item['size'] <= OFFICE_VIEWER_LIMIT:
            # Microsoft's viewer fetches the public raw GitHub file; the sha keeps its cache fresh.
            source = GithubStore(repo, branch).raw_url(item['path'])+'?rev='+item['sha']
            st.iframe('https://view.officeapps.live.com/op/embed.aspx?src='+quote(source, safe=''), height=720)
            st.caption(t['office_hint'])
        else:
            st.info(t['preview'])
    with side:
        st.download_button(t['download'], filedata, file_name=item['filename'],
                           mime=mimetypes.guess_type(item['filename'])[0] or 'application/octet-stream',
                           type='primary', use_container_width=True, key='reader_download')
        done = is_done(item)
        if st.button(t['unmark_done'] if done else t['mark_done'], key='toggle_done',
                     type='tertiary' if done else 'secondary', use_container_width=True):
            toggle_done(item)
            st.rerun()
        with st.container(key='pager'):
            if position > 0 and st.button('← '+siblings[position - 1]['title'], key='prev_item',
                                          help=t['prev'], use_container_width=True):
                route('reader', course=item['course_id'], material=siblings[position - 1]['id'])
            if position < len(siblings) - 1 and st.button('→ '+siblings[position + 1]['title'], key='next_item',
                                                          help=t['next'], use_container_width=True):
                route('reader', course=item['course_id'], material=siblings[position + 1]['id'])
        share(item, t)


def deck(item: dict, count: int, t: dict) -> None:
    """Slide viewer; fx.js adds arrows, swipe, filmstrip clicks and fullscreen. ?slide=N opens slide N."""
    try:
        start = min(max(int(st.query_params.get('slide', 1)), 1), count)
    except ValueError:
        start = 1
    base = f'app/static/slides/{item["sha"]}/'
    strip = ''.join(
        f'<button class="deck-thumb{" on" if n == start else ""}" type="button" data-i="{n}" aria-label="{esc(t["slide_word"])} {n}">'
        f'<img src="{base}t{n}.webp" alt="" loading="lazy"><span>{n:02d}</span></button>' for n in range(1, count + 1))
    st.markdown(
        f'<div class="deck" data-total="{count}" data-start="{start}" data-base="{base}" data-key="{key_of(item["id"])}" '
        f'data-title="{esc(item["title"])}" data-resume="{esc(t["resume"])}" data-restart="{esc(t["from_start"])}" '
        f'data-explicit="{1 if "slide" in st.query_params else 0}">'
        # The glow is the slide's own small preview, blurred by CSS: backlight in the slide's colours.
        f'<img class="deck-glow" src="{base}t{start}.webp" alt="" aria-hidden="true">'
        f'<div class="deck-stage"><img class="deck-img" src="{base}{start}.webp" alt="{esc(item["title"])}">'
        f'<button class="deck-nav deck-prev" type="button" aria-label="{esc(t["prev"])}">←</button>'
        f'<button class="deck-nav deck-next" type="button" aria-label="{esc(t["next"])}">→</button></div>'
        f'<div class="deck-bar"><span class="deck-count"><b>{start:02d}</b> / {count:02d}</span>'
        f'<div class="deck-progress"><i style="width:{100 * start / count:.2f}%"></i></div>'
        f'<span class="deck-hint">{esc(t["deck_hint"])}</span>'
        f'<button class="deck-save" type="button" title="PNG">↓ {esc(t["save_slide"])}</button>'
        f'<button class="deck-full" type="button">⛶ {esc(t["fullscreen"])}</button></div>'
        f'<div class="deck-strip">{strip}</div></div>',
        unsafe_allow_html=True,
    )


def site_url(**params: str) -> str:
    # SITE_URL in secrets wins; otherwise the address the visitor opened (Cloud adds a /~/+ prefix).
    base = secret('SITE_URL')
    if not base:
        try:
            base = (st.context.url or '').split('?')[0].replace('/~/+', '')
        except Exception:
            base = ''
    return base.rstrip('/')+'/?'+urlencode(params)


def share_url(item: dict) -> str:
    return site_url(lang=item['lang'], material=item['id'])


POSTER_ROWS = 14  # what fits on A4 under the title and above the QR block
POSTER_CSS = """
@page {size: A4; margin: 0}
* {box-sizing: border-box; margin: 0; padding: 0}
body {background: #d9d6d0; font-family: Inter, Arial, sans-serif; color: #111}
.bar {position: sticky; top: 0; z-index: 2; display: flex; justify-content: flex-end; padding: 10px; background: #d9d6d0}
.bar button {font: 600 14px Inter, Arial; background: #111; color: #fff; border: 0; padding: 12px 22px; cursor: pointer}
.bar button:hover {background: #E3241B}
.sheet {width: 210mm; height: 297mm; margin: 0 auto 20px; background: #F4F2EE; padding: 16mm 16mm 14mm;
        display: flex; flex-direction: column; transform-origin: top center}
.meta {display: grid; grid-template-columns: repeat(4, 1fr); border-top: 1.2pt solid #111; padding-top: 2.5mm;
       font: 8pt 'JetBrains Mono', monospace; text-transform: uppercase; letter-spacing: .04em}
.brand {font: 800 11pt 'Inter Tight', Arial; text-transform: none; letter-spacing: -.03em}
.red {color: #E3241B}
h1 {font-family: 'Inter Tight', Arial; font-weight: 700; line-height: .92; letter-spacing: -.05em; margin: 22mm 0 7mm; overflow-wrap: anywhere}
.facts {font: 9pt 'JetBrains Mono', monospace; text-transform: uppercase; margin-bottom: 9mm}
ol {list-style: none; border-top: 1.2pt solid #111}
li {display: grid; grid-template-columns: 12mm 1fr auto; gap: 3mm; align-items: baseline; padding: 2.4mm 0; border-bottom: .5pt solid #bdb8b0}
li span, li i {font: 8pt 'JetBrains Mono', monospace; font-style: normal; color: #555; text-transform: uppercase}
li b {font: 600 11.5pt 'Inter Tight', Arial; letter-spacing: -.01em}
.more {font: 8pt 'JetBrains Mono', monospace; margin-top: 2mm; color: #555}
.foot {margin-top: auto; display: grid; grid-template-columns: 62mm 1fr; gap: 8mm; align-items: end; border-top: 1.2pt solid #111; padding-top: 6mm}
.foot img {width: 62mm; height: 62mm; display: block}
.foot b {display: block; font: 700 24pt/1 'Inter Tight', Arial; letter-spacing: -.04em; margin-bottom: 4mm}
.foot p {font-size: 10pt; line-height: 1.45; color: #333}
.foot small {display: block; margin-top: 4mm; font: 7pt 'JetBrains Mono', monospace; color: #555; word-break: break-all}
@media print {body {background: none} .bar {display: none} .sheet {margin: 0; transform: none !important}}
"""
# Fit the A4 sheet into the preview width; printing ignores this (see @media print).
POSTER_JS = """
function fit() { var s = document.getElementById('sheet'); var k = Math.min(1, (innerWidth - 20) / s.offsetWidth);
  s.style.transform = 'scale(' + k + ')'; s.style.marginBottom = (s.offsetHeight * (k - 1) + 20) + 'px'; }
addEventListener('resize', fit); fit();
"""


def poster_html(course: dict, lang: str, items: list[dict], number: int, total: int) -> str:
    """Self-contained A4 poster (Swiss style) with a QR code to the course page."""
    t = I18N[lang]
    title = display_course(course, lang)
    link = site_url(lang=lang, course=course['id'])
    lectures = sum(m['kind'] == 'lectures' for m in items)
    def label(m: dict) -> str:
        # Type only matters when lectures exist; otherwise the slide count is the useful detail.
        if lectures:
            return t['lectures_one'] if m['kind'] == 'lectures' else t['presentations_one']
        return f'{slides(m)} {plural(slides(m), lang, "slides")}' if slides(m) else ''

    rows = ''.join(f'<li><span>{n:02d}</span><b>{esc(m["title"])}</b><i>{esc(label(m))}</i></li>'
                   for n, m in enumerate(items[:POSTER_ROWS], 1))
    more = f'<p class="more">+ {len(items) - POSTER_ROWS} {esc(t["materials"])}</p>' if len(items) > POSTER_ROWS else ''
    size = 84 if len(title) < 18 else 64 if len(title) < 32 else 48  # pt; long Kazakh titles must still fit
    return (
        f'<!doctype html><html lang="{"kk" if lang == "kz" else "ru"}"><head><meta charset="utf-8">'
        f'<title>{esc(title)} · StudySpace</title>'
        '<link href="https://fonts.googleapis.com/css2?family=Inter+Tight:wght@600;700;800&family=Inter:wght@400;500'
        '&family=JetBrains+Mono:wght@400&display=swap" rel="stylesheet">'
        f'<style>{POSTER_CSS} h1 {{font-size: {size}pt}}</style></head><body>'
        f'<div class="bar"><button onclick="window.print()">{esc(t["print"])}</button></div>'
        '<main class="sheet" id="sheet">'
        f'<div class="meta"><span class="brand">StudySpace<span class="red">■</span></span><span>{number:02d} / {total:02d}</span>'
        f'<span>{esc(LANG_LABELS[lang].split()[-1])}</span><span>2026</span></div>'
        f'<h1>{esc(title)}<span class="red">.</span></h1>'
        + (f'<div class="facts">{lectures} {esc(t["lectures"])} · {len(items) - lectures} {esc(t["presentations"])}</div>' if lectures
           else f'<div class="facts">{len(items)} {esc(plural(len(items), lang, "pres"))}</div>')
        + ""
        f'<ol>{rows}</ol>{more}'
        f'<div class="foot"><img src="{qr_uri(link, 10)}" alt="QR"><div><b>{esc(t["poster_scan"])}</b>'
        f'<p>{esc(t["poster_hint"])}</p><small>{esc(link)}</small></div></div>'
        f'</main><script>{POSTER_JS}</script></body></html>'
    )


@st.dialog('A4', width='large')
def poster_dialog(page: str, filename: str, label: str) -> None:
    # Isolated data: frame (like uploaded HTML); its own button prints just the poster.
    st.iframe('data:text/html;charset=utf-8;base64,'+base64.b64encode(page.encode('utf-8')).decode('ascii'), height=760)
    st.download_button(label, page.encode('utf-8'), file_name=filename, mime='text/html', use_container_width=True)


def qr_uri(link: str, scale: int) -> str:
    return segno.make(link, error='m').svg_data_uri(scale=scale, dark='#0B0912', light='#FFFFFF', border=2)


@st.dialog('QR', width='large')
def qr_dialog(link: str, title: str) -> None:
    st.markdown(f'<div class="qr-big"><img src="{qr_uri(link, 14)}" alt="QR"><b>{esc(title)}</b></div>', unsafe_allow_html=True)


def share(item: dict, t: dict) -> None:
    link = share_url(item)
    with st.container(key='share'):
        st.markdown(f'<div class="share-card"><img class="share-qr" src="{qr_uri(link, 5)}" alt="QR">'
                    f'<div><span class="eyebrow">{esc(t["share"])}</span><b>{esc(t["share_title"])}</b>'
                    f'<p>{esc(t["share_hint"])}</p></div></div>'
                    # fx.js copies data-copy to the clipboard and flips the label to data-done.
                    f'<div class="sharelink"><input type="text" readonly value="{esc(link)}" aria-label="{esc(t["share_title"])}">'
                    f'<button class="ss-copy" type="button" data-copy="{esc(link)}" data-done="{esc(t["copied"])}">'
                    f'{esc(t["copy"])}</button></div>', unsafe_allow_html=True)
        if st.button(t['qr_big'], key='qr_big', use_container_width=True):
            qr_dialog(link, item['title'])


def about(lang: str) -> None:
    t = I18N[lang]
    header(t['about_head'], t['about_body'], '§')
    if lang == 'kz':
        cards = [('Пәнді таңда', 'Барлық пәндер бір жерде.'),
                 ('Материалды тап', 'Ыңғайлы іздеу және сүзгілер.'),
                 ('Қай жерде болсаң да оқы', 'Дәрістерді оқы және файлдарды жүкте.')]
    else:
        cards = [('Выбери предмет', 'Список дисциплин всегда под рукой.'),
                 ('Найди материал', 'Удобный поиск, фильтры и оба языка.'),
                 ('Учись где угодно', 'Открывай лекции и скачивай файлы.')]
    html_cards = ''.join(f'<div><span>{i:02d}</span><b>{esc(name)}</b><p>{esc(desc)}</p></div>'
                         for i, (name, desc) in enumerate(cards, 1))
    st.markdown(f'<div class="about-features">{html_cards}</div>', unsafe_allow_html=True)


def flash() -> None:
    for key, fn in [('success_msg', st.success), ('warning_msg', st.warning)]:
        message = st.session_state.pop(key, None)
        if message:
            fn(message)


def telegram_ready() -> bool:
    return bool(secret('TELEGRAM_BOT_TOKEN') and secret('TELEGRAM_CHAT_ID'))


def telegram_api(method: str, **payload) -> dict:
    # Errors never include the URL: it contains the bot token.
    try:
        return requests.post(f'https://api.telegram.org/bot{secret("TELEGRAM_BOT_TOKEN")}/{method}', json=payload, timeout=15).json()
    except (requests.RequestException, ValueError):
        return {'ok': False, 'description': 'Telegram недоступен, попробуй позже.'}


def telegram_send(text: str) -> str | None:
    """Posts to the group chat; returns an error text, or None on success."""
    data = telegram_api('sendMessage', chat_id=secret('TELEGRAM_CHAT_ID'), text=text,
                        parse_mode='HTML', disable_web_page_preview=True)
    return None if data.get('ok') else 'Telegram: '+str(data.get('description', 'ошибка'))[:200]


def upload_message(course: dict, lang: str, kind: str, files: list[tuple[str, str]]) -> str:
    t = I18N[lang]
    kind_name = t['lectures_title'] if kind == 'lectures' else t['presentations_title']
    lines = [f'📚 <b>{html.escape(t["new_title"])}</b>',
             f'{html.escape(course.get("icon", "📘"))} {html.escape(display_course(course, lang))} · {html.escape(kind_name)}', '']
    for filename, path in files:
        title = Path(filename).stem.replace('_', ' ')
        lines.append(f'• <a href="{html.escape(share_url({"lang": lang, "id": path}), quote=True)}">{html.escape(title)}</a>')
    return '\n'.join(lines)


def telegram_settings() -> None:
    with st.expander('🔔 Уведомления в Telegram' + (' — включены' if telegram_ready() else ' — выключены')):
        if telegram_ready():
            st.caption('После каждой загрузки бот пишет в чат группы, какие файлы появились, со ссылками на них.')
            if st.button('Отправить тестовое сообщение', key='tg_test'):
                error = telegram_send('✅ StudySpace: уведомления работают.')
                if error:
                    st.error(error)
                else:
                    st.success('Сообщение отправлено, проверь чат.')
            return
        st.markdown(
            '1. В Telegram открой **@BotFather**, отправь `/newbot` и получи токен бота.\n'
            '2. Добавь бота в канал или группу (в канале — администратором).\n'
            '3. В Streamlit Cloud → Settings → Secrets добавь `TELEGRAM_BOT_TOKEN = "токен"`.\n'
            '4. Напиши что-нибудь в группе, нажми кнопку ниже и скопируй нужный ID в `TELEGRAM_CHAT_ID = "..."`.\n'
            '   Для публичного канала подойдёт и его адрес: `TELEGRAM_CHAT_ID = "@имя_канала"`.')
        if secret('TELEGRAM_BOT_TOKEN') and st.button('Найти ID чатов', key='tg_find'):
            data = telegram_api('getUpdates')
            chats = {}
            for update in data.get('result', []):
                for key in ('message', 'channel_post', 'my_chat_member'):
                    chat = (update.get(key) or {}).get('chat')
                    if chat:
                        chats[chat['id']] = chat.get('title') or chat.get('username') or chat.get('first_name', '')
            if chats:
                st.code('\n'.join(f'{cid}  —  {name}' for cid, name in chats.items()), language=None)
            else:
                st.info(data.get('description') if not data.get('ok') else 'Бот пока не видел сообщений. Напиши в группе и нажми ещё раз.')


def files_done(course_id: str, done: list[str], failed: list[str], prefix: str) -> None:
    """Report a bulk file action; on any success reload the catalog and clear the selection."""
    if failed:
        st.session_state['warning_msg'] = 'Не получилось:\n'+'\n'.join(failed)+'\nЕсли файлы только что меняли, обнови страницу через минуту.'
    if not done:
        st.warning(st.session_state.pop('warning_msg', 'Выбранные файлы уже этого типа.'))
        return
    refresh_data()
    st.session_state['success_msg'] = f'{prefix}{len(done)}.'
    for key in ('file_pick_'+course_id, 'confirm_file_'+course_id):
        st.session_state.pop(key, None)
    st.rerun()


def attention(config: dict, materials: list[dict]) -> list[str]:
    """Plain-language problems a teacher can fix: empty sections and sections without lectures."""
    issues = []
    for course in config['courses']:
        for lang in course_languages(course):
            own = [m for m in materials if m['course_id'] == course['id'] and m['lang'] == lang]
            name = f'{display_course(course, lang)} · {lang.upper()}'
            if not own:
                issues.append(f'{name} — нет материалов, студенты видят пустой раздел')
        if not course_languages(course):
            issues.append(f'{course.get("title_ru") or course.get("title_kz") or course["id"]} — не выбран язык, предмет скрыт')
    return issues


def dashboard(config: dict, materials: list[dict]) -> None:
    lectures = sum(m['kind'] == 'lectures' for m in materials)
    fresh = sorted((m for m in materials if m.get('new')), key=lambda m: m['new'], reverse=True)
    by_lang = Counter(m['lang'] for m in materials)
    stats = [(len(config['courses']), 'Дисциплины'), (len(materials), 'Материалы')]
    stats += [(lectures, 'Лекции')] if lectures else []
    stats += [(sum(slides(m) for m in materials), 'Слайдов'), (len(fresh), 'Новые за 7 дней')]
    st.markdown('<div class="stats admin-stats">' + ''.join(f'<div><b data-count="{v}">{v:02d}</b><span>{esc(k)}</span></div>' for v, k in stats)
                + f'</div><div class="lang-split"><span>RU {by_lang["ru"]}</span><i style="flex:{max(by_lang["ru"], 0.001)}"></i>'
                  f'<i class="kz" style="flex:{max(by_lang["kz"], 0.001)}"></i><span>KZ {by_lang["kz"]}</span></div>',
                unsafe_allow_html=True)
    issues = attention(config, materials)
    recent = [f'{m["title"]} — {display_course(m["course"], m["lang"])} · {m["lang"].upper()} · {m["new"]}' for m in fresh[:6]]
    left, right = st.columns(2, gap='large')
    left.markdown(
        f'<div class="apanel"><span class="eyebrow">01</span><h4>Требует внимания</h4><ul>'
        + (''.join(f'<li class="warn">{esc(i)}</li>' for i in issues) or '<li class="ok">Всё в порядке: в каждом разделе есть материалы.</li>')
        + '</ul></div>', unsafe_allow_html=True)
    right.markdown(
        f'<div class="apanel"><span class="eyebrow">02</span><h4>Загружено за 7 дней</h4><ul>'
        + (''.join(f'<li>{esc(r)}</li>' for r in recent) or '<li class="muted">Пока ничего нового. Метки появляются, если в Secrets есть GITHUB_TOKEN.</li>')
        + '</ul></div>', unsafe_allow_html=True)


def admin(config: dict, materials: list[dict]) -> None:
    header('Твоя учебная платформа.', 'Создавай дисциплины, загружай файлы и управляй цифровой библиотекой.', '⚙')
    admin_password = secret('ADMIN_PASSWORD')
    token = secret('GITHUB_TOKEN')
    repo, branch, _ = settings()
    if not admin_password:
        st.warning('Панель пока не настроена. Сначала добавь ADMIN_PASSWORD и GITHUB_TOKEN в Settings → Secrets приложения на Streamlit Cloud.')
        st.code('ADMIN_PASSWORD = "придумай-длинный-пароль"\nGITHUB_TOKEN = "github_pat_..."\nGITHUB_REPO = "olenver-04/StudySpace"\nGITHUB_BRANCH = "main"', language='toml')
        st.caption('Токен должен иметь Contents: Read and write только для StudySpace. Не публикуй его в GitHub.')
        return
    if not st.session_state.get('admin_ok', False):
        st.markdown('<div class="login-intro"><span class="login-lock">⌘</span><div><h3>Вход для преподавателя</h3><p>Админ-панель защищена паролем. Для студентов доступна только библиотека.</p></div></div>', unsafe_allow_html=True)
        with st.form('login_form'):
            pwd = st.text_input('Пароль администратора', type='password')
            submit = st.form_submit_button('Войти', type='primary', use_container_width=True)
        if submit:
            wait = login_wait()
            if wait:
                st.error(f'Слишком много неверных попыток. Попробуй снова через {wait // 60} мин {wait % 60} с.')
            elif hmac.compare_digest(pwd.encode('utf-8'), admin_password.encode('utf-8')):
                st.session_state['admin_ok'] = True
                st.rerun()
            else:
                login_failures().append(time.time())
                time.sleep(1)  # slows down guessing scripts
                left = LOGIN_MAX_FAILS - len(login_failures())
                st.error('Неверный пароль.' + (f' Осталось попыток: {left}.' if left > 0 else ' Вход временно заблокирован на 5 минут.'))
        return
    with st.container(key='adminbar'):
        bar, out = st.columns([5, 1], vertical_alignment='center')
        bar.markdown(f'<div class="adminbar"><i></i>Вход выполнен · {esc(repo)} · {esc(branch)}</div>', unsafe_allow_html=True)
        if out.button('Выйти →', use_container_width=True, key='logout', type='tertiary'):
            st.session_state['admin_ok'] = False
            route('welcome', lang='')
    flash()
    if not token:
        st.error('Добавь GITHUB_TOKEN в секреты Streamlit Cloud: без токена создавать дисциплины и загружать файлы нельзя.')
        return
    github = GithubStore(repo, branch, token)
    dashboard(config, materials)
    st.markdown('<div class="admin-section-heading"><span class="eyebrow">03</span><h3>Управление</h3><p>Все изменения сохраняются прямо в репозитории GitHub; любое действие можно откатить по истории коммитов.</p></div>', unsafe_allow_html=True)
    create_tab, upload_tab, manage_tab = st.tabs(['✳   Создать дисциплину', '↥   Загрузить материалы', '▦   Мои дисциплины'])
    with create_tab:
        st.markdown('#### ✦ Новая дисциплина')
        st.caption('Выбери, на каком языке преподаётся дисциплина. Для каждого выбранного языка появится отдельная папка и раздел для студентов.')
        teaching = st.radio(
            'Язык преподавания *', list(TEACHING_LANGUAGES),
            format_func=lambda choice: TEACHING_LANGUAGES[choice], horizontal=True,
            key='new_course_language',
        )
        selected_languages = ['ru', 'kz'] if teaching == 'both' else [teaching]
        details = {
            'ru': 'Дисциплина появится только в русском разделе. Создастся папка ru.',
            'kz': 'Пән тек қазақша бөлімде көрсетіледі. kz қалтасы жасалады.',
            'both': 'Дисциплина появится в обоих разделах. Создадутся папки ru и kz, материалы для них загружаются отдельно.',
        }
        st.markdown(
            f'<div class="language-choice-summary"><span>✦</span><div><b>{esc(TEACHING_LANGUAGES[teaching])}</b>'
            f'<p>{esc(details[teaching])}</p></div></div>',
            unsafe_allow_html=True,
        )
        with st.form('create_course', clear_on_submit=True):
            title_ru = (st.text_input('Название на русском *', placeholder='Например: Программирование на Java')
                        if 'ru' in selected_languages else '')
            title_kz = (st.text_input('Қазақша атауы *', placeholder='Мысалы: Java бағдарламалау')
                        if 'kz' in selected_languages else '')
            slug_override = st.text_input('Название папки латиницей (необязательно)', placeholder='Например: java')
            icon = st.selectbox('Иконка дисциплины', EMOJIS)
            created = st.form_submit_button('＋ Создать дисциплину', type='primary', use_container_width=True)
        if created:
            course_id = (slug_override.strip().lower() or slugify(title_ru or title_kz))
            if ('ru' in selected_languages and not title_ru.strip()) or ('kz' in selected_languages and not title_kz.strip()):
                st.error('Заполни название на каждом выбранном языке.')
            elif not valid_slug(course_id):
                st.error('Название папки: только латинские буквы, цифры и дефис (до 65 символов).')
            else:
                try:
                    live = github.read_catalog()
                    if any(c.get('id') == course_id for c in live.get('courses', [])):
                        st.error('Дисциплина с такой папкой уже существует. Используй другое название.')
                    else:
                        # GitHub does not store empty directories. Create only selected languages.
                        for enabled_lang in selected_languages:
                            github.ensure_folder(f'materials/uploads/{course_id}/{enabled_lang}')
                        live.setdefault('courses', []).append({
                            'id': course_id, 'title_ru': title_ru.strip(),
                            'title_kz': title_kz.strip(), 'icon': icon,
                            'languages': selected_languages,
                        })
                        github.write_file('catalog.json', (json.dumps(live, ensure_ascii=False, indent=2)+'\n').encode('utf-8'),
                                          'StudySpace: add course '+course_id, replace=True)
                        refresh_data()
                        lang_names = ', '.join(selected_languages)
                        st.session_state['success_msg'] = f'✅ Дисциплина создана. Языки: {lang_names}. Папки появились в GitHub.'
                        st.rerun()
                except GithubError as exc:
                    st.error(f'Не удалось завершить создание: {exc}. Если папки уже появились, повтори создание — они не пропадут.')
    with upload_tab:
        st.markdown('#### ↥ Новые лекции и презентации')
        if not config['courses']:
            st.info('Сначала создай хотя бы одну дисциплину.')
        else:
            # Outside the form so language options refresh as soon as a course is chosen.
            course = st.selectbox('Дисциплина *', config['courses'],
                                  format_func=lambda c: (c.get('title_ru') or c.get('title_kz') or c['id']),
                                  key='upload_course')
            allowed_languages = list(course_languages(course))
            if not allowed_languages:
                st.error('У дисциплины не настроен язык. Измени доступные языки во вкладке «Мои дисциплины».')
            else:
                st.caption('Доступные языки: '+', '.join(LANG_LABELS[v] for v in allowed_languages))
                with st.form('upload_files', clear_on_submit=False):
                    language = st.radio('Язык материала *', allowed_languages,
                                        format_func=lambda v: LANG_LABELS[v], horizontal=True,
                                        key=f'upload_language_choice_{course["id"]}')
                    kind = st.radio('Что загружаем? *', ['lectures', 'presentations'], index=1,
                                    format_func=lambda k: '📖 Лекция' if k == 'lectures' else '🖥 Презентация', horizontal=True)
                    files = st.file_uploader('Добавить файлы', accept_multiple_files=True,
                                             type=[s[1:] for s in sorted(ALLOWED_EXTENSIONS)],
                                             help='PDF, PPTX, DOCX, DOC, PPT, MD, TXT, HTML. До 20 МБ на файл.')
                    replace = st.checkbox('Заменять файлы с тем же названием', value=False)
                    uploaded = st.form_submit_button('↑ Опубликовать материалы', type='primary', use_container_width=True)
                if uploaded:
                    if language not in course_languages(course):
                        st.error('Этот язык отключён для выбранной дисциплины. Обнови страницу.')
                    elif not files:
                        st.warning('Выбери хотя бы один файл.')
                    else:
                        successes, failures = [], []
                        for file in files:
                            try:
                                if file.size > MAX_UPLOAD_BYTES:
                                    raise ValueError('Файл больше 20 МБ.')
                                filename = safe_filename(file.name)
                                path = upload_path(course['id'], language, kind, filename)
                                github.write_file(path, file.getvalue(), 'StudySpace: upload '+path, replace=replace)
                                successes.append((filename, path))
                            except (GithubError, ValueError) as exc:
                                failures.append(f'{file.name}: {exc}')
                        if successes:
                            refresh_data()
                            st.session_state['success_msg'] = f'✅ Загружено файлов: {len(successes)}. Они уже сохранены в GitHub.'
                            if telegram_ready():
                                tg_error = telegram_send(upload_message(course, language, kind, successes))
                                if tg_error:
                                    failures.append(tg_error)
                                else:
                                    st.session_state['success_msg'] += ' Уведомление отправлено в Telegram.'
                        if failures:
                            st.session_state['warning_msg'] = 'Не получилось:\n'+'\n'.join(failures)
                        if successes:
                            st.rerun()
                        if failures:
                            st.warning(st.session_state.pop('warning_msg'))
        telegram_settings()
    with manage_tab:
        st.markdown('#### ▦ Дисциплины в каталоге')
        if not config['courses']:
            st.info('Дисциплин ещё нет. Создай первую в соседней вкладке.')
        for c in config['courses']:
            count = sum(m['course_id'] == c['id'] for m in materials)
            with st.expander(f'{c.get("icon", "📘")}  {c.get("title_ru") or c.get("title_kz") or c["id"]} — {count} материалов'):
                active_languages = list(course_languages(c))
                st.write('**Языки преподавания:** '+', '.join(LANG_LABELS[l] for l in active_languages))
                st.code('\n'.join(f'materials/uploads/{c["id"]}/{l}/' for l in active_languages), language='text')
                selected_mode = ('both' if set(active_languages) == {'ru', 'kz'} else active_languages[0] if active_languages else 'both')
                new_mode = st.radio('Изменить языки дисциплины', list(TEACHING_LANGUAGES),
                                    index=list(TEACHING_LANGUAGES).index(selected_mode),
                                    format_func=lambda mode: TEACHING_LANGUAGES[mode],
                                    horizontal=True, key='edit_language_'+c['id'])
                new_languages = ['ru', 'kz'] if new_mode == 'both' else [new_mode]
                # Adding a language requires its own localized title, not the other language's label.
                edited_ru = (st.text_input('Название на русском', value=c.get('title_ru', ''),
                                           key='edit_ru_title_'+c['id'])
                             if 'ru' in new_languages else c.get('title_ru', ''))
                edited_kz = (st.text_input('Қазақша атауы', value=c.get('title_kz', ''),
                                           key='edit_kz_title_'+c['id'])
                             if 'kz' in new_languages else c.get('title_kz', ''))
                has_changes = (new_languages != active_languages
                               or edited_ru.strip() != (c.get('title_ru') or '')
                               or edited_kz.strip() != (c.get('title_kz') or ''))
                if has_changes:
                    st.caption('При отключении языка файлы сохранятся в GitHub, но раздел станет скрыт для студентов.')
                    if st.button('Сохранить настройки дисциплины', key='save_lang_'+c['id'], type='primary'):
                        if ('ru' in new_languages and not edited_ru.strip()) or ('kz' in new_languages and not edited_kz.strip()):
                            st.error('Для каждого включённого языка укажи название дисциплины.')
                        else:
                            try:
                                live = github.read_catalog()
                                for lang_to_add in new_languages:
                                    github.ensure_folder(f'materials/uploads/{c["id"]}/{lang_to_add}')
                                for entry in live.get('courses', []):
                                    if entry.get('id') == c['id']:
                                        entry.update(languages=new_languages,
                                                     title_ru=edited_ru.strip(), title_kz=edited_kz.strip())
                                github.write_file('catalog.json', (json.dumps(live, ensure_ascii=False, indent=2)+'\n').encode('utf-8'),
                                                  'StudySpace: update course settings '+c['id'], replace=True)
                                refresh_data()
                                st.session_state['success_msg'] = 'Настройки дисциплины сохранены. Файлы сохранены.'
                                st.rerun()
                            except GithubError as exc:
                                st.error(str(exc))
                course_files = [m for m in materials if m['course_id'] == c['id']]
                if course_files:
                    st.markdown('**Файлы дисциплины**')
                    by_path = {m['path']: m for m in course_files}
                    picked = st.multiselect(
                        'Выбери файлы', list(by_path), key='file_pick_'+c['id'], placeholder='Один или несколько файлов',
                        format_func=lambda p: f'{by_path[p]["lang"].upper()} · {"Лекция" if by_path[p]["kind"] == "lectures" else "Презентация"} · {by_path[p]["filename"]}')
                    picked = [by_path[p] for p in picked if p in by_path]
                    to_lect_col, to_pres_col = st.columns(2)
                    to_lect = to_lect_col.button('▤ Сделать лекциями', disabled=not picked, key='to_lect_'+c['id'], use_container_width=True)
                    to_pres = to_pres_col.button('▣ Сделать презентациями', disabled=not picked, key='to_pres_'+c['id'], use_container_width=True)
                    if to_lect or to_pres:
                        target = 'lectures' if to_lect else 'presentations'
                        done, failed = [], []
                        with st.spinner('Переношу файлы в GitHub…'):
                            for m in picked:
                                if m['kind'] == target:
                                    continue
                                try:
                                    new_path = upload_path(c['id'], m['lang'], target, m['filename'])
                                    # Copy first, delete second: a failure can leave a duplicate, never a lost file.
                                    github.write_file(new_path, github.raw_bytes(m['path'], m['sha']), f'StudySpace: move {m["path"]} -> {new_path}')
                                    github.delete_file(m['path'], m['sha'], 'StudySpace: moved to '+new_path)
                                    done.append(m['filename'])
                                except (GithubError, ValueError) as exc:
                                    failed.append(f'{m["filename"]}: {exc}')
                        files_done(c['id'], done, failed, 'Тип изменён у файлов: ')
                    sure = st.checkbox('Подтверждаю удаление выбранных файлов', key='confirm_file_'+c['id'])
                    if st.button('🗑 Удалить выбранные файлы', disabled=not (sure and picked), key='delete_file_'+c['id']):
                        done, failed = [], []
                        for m in picked:
                            try:
                                github.delete_file(m['path'], m['sha'], 'StudySpace: delete '+m['path'])
                                done.append(m['filename'])
                            except GithubError as exc:
                                failed.append(f'{m["filename"]}: {exc}')
                        files_done(c['id'], done, failed, 'Удалено (можно восстановить из истории GitHub): ')
                    st.markdown('<div class="side-rule"></div>', unsafe_allow_html=True)
                st.caption('Удаление из каталога скрывает предмет для студентов, но не стирает файлы из GitHub.')
                confirm = st.checkbox('Подтверждаю удаление из каталога', key='confirm_delete_'+c['id'])
                if st.button('Убрать дисциплину', disabled=not confirm, key='delete_course_'+c['id']):
                    try:
                        live = github.read_catalog()
                        live['courses'] = [x for x in live.get('courses',[]) if x.get('id') != c['id']]
                        github.write_file('catalog.json', (json.dumps(live,ensure_ascii=False,indent=2)+'\n').encode('utf-8'),
                                          'StudySpace: hide course '+c['id'], replace=True)
                        refresh_data()
                        st.session_state['success_msg']='Дисциплина скрыта из каталога. Файлы в GitHub сохранены.'
                        st.rerun()
                    except GithubError as exc:
                        st.error(str(exc))
        st.caption('Открыть GitHub: '+f'https://github.com/{repo}/tree/{branch}/materials/uploads')


@st.cache_resource
def fulltext_index() -> FullText:
    return FullText(STATIC / 'fulltext.json')


def start_index(config: dict, materials: list[dict]) -> None:
    """Text, slide counts and covers for every file students can open, built in the background."""
    repo, branch, _ = settings()
    docs = [{'u': '?'+urlencode({'lang': m['lang'], 'material': m['id']}), 'path': m['path'], 'sha': m['sha'],
             'extension': m['extension']}
            for c in config['courses'] for m in materials
            if m['course_id'] == c['id'] and m['lang'] in course_languages(c)]
    fulltext_index().refresh(docs, lambda path, sha: GithubStore(repo, branch).raw_bytes(path, sha))


def search_index(config: dict, materials: list[dict]) -> None:
    """Hidden JSON for the client-side search palette in fx.js: only what students can already open."""
    lang = st.session_state.get('lang', '')
    t = I18N[ui_lang()]
    entries = []
    for code in LANG_LABELS:
        tl = I18N[code]
        courses = [c for c in config['courses'] if code in course_languages(c)]
        ids = {c['id'] for c in courses}
        entries += [{'k': tl['course_word'], 't': display_course(c, code), 's': c.get('icon', ''), 'l': code, 'c': 1,
                     'u': '?'+urlencode({'lang': code, 'course': c['id']})} for c in courses]
        entries += [{'k': tl['lectures_one'] if m['kind'] == 'lectures' else tl['presentations_one'], 't': m['title'],
                     's': display_course(m['course'], code), 'l': code, 'u': '?'+urlencode({'lang': code, 'material': m['id']})}
                    for m in materials if m['lang'] == code and m['course_id'] in ids]
    st.markdown(f'<div id="ss-index" hidden data-lang="{esc(lang)}" data-ph="{esc(t["search_ph"])}" '
                f'data-ft="app/static/fulltext.json" data-in-text="{esc(t["in_text"])}" data-top="{esc(t["to_top"])}" '
                f'data-slide="{esc(t["slide_word"])}" '
                f'data-empty="{esc(t["search_empty"])}" data-items="{esc(json.dumps(entries, ensure_ascii=False))}"></div>',
                unsafe_allow_html=True)


def footer() -> None:
    st.markdown(
        '<footer class="footer-big">'
        '<div class="wordmark" aria-hidden="true">StudySpace<span>■</span></div>'
        '<div class="fbottom"><span>© 2026 StudySpace</span>'
        '<span class="credit">Created by <button class="credit-name" type="button" title="?">denver</button></span>'
        '</div></footer>',
        unsafe_allow_html=True,
    )


def main() -> None:
    style()
    effects()
    config, materials, error = retrieve()
    initial_route(materials)
    st.session_state['mixed'] = any(m['kind'] == 'lectures' for m in materials)
    start_index(config, materials)
    topnav(config, materials)
    page = st.session_state.get('page', 'welcome')
    lang = st.session_state.get('lang', '')
    if error and page == 'admin':
        st.warning('Каталог GitHub временно недоступен. Показана локальная версия. '+error)
    elif error:
        st.warning(I18N[lang]['offline'] if lang in I18N else I18N['ru']['offline']+' / '+I18N['kz']['offline'])
    if page == 'admin':
        admin(config, materials)
    elif page == 'welcome' or lang not in LANG_LABELS:
        welcome(materials)
    elif page == 'home':
        home(config, materials, lang)
    elif page == 'library':
        library(config, materials, lang)
    elif page == 'course':
        course_page(config, materials, lang)
    elif page == 'reader':
        reader(materials, lang)
    elif page == 'about':
        about(lang)
    else:
        welcome(materials)
    footer()
    search_index(config, materials)
    # fx.js copies this into the ss_done cookie, so marks survive the next visit.
    st.markdown(f'<div id="ss-done" hidden data-done="{"|".join(done_ids())}"></div>', unsafe_allow_html=True)


if __name__ == '__main__':
    main()
