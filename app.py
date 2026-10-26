"""StudySpace 2 — bilingual student library + GitHub-backed teacher dashboard.

The public catalog is read from GitHub, and teacher writes happen only after
server-side password authentication. GitHub credentials stay in st.secrets.
"""
from __future__ import annotations

import html
import hmac
import json
import mimetypes
from collections import Counter
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from github_store import GithubError, GithubStore
from portal_logic import (
    ALLOWED_EXTENSIONS, course_languages, display_course, human_size, parse_materials,
    safe_filename, slugify, upload_path, valid_slug,
)

st.set_page_config(page_title='StudySpace • Education Hub', page_icon='✳️', layout='wide', initial_sidebar_state='expanded')
BASE = Path(__file__).resolve().parent
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
LANG_LABELS = {'ru': '🇷🇺 Русский', 'kz': '🇰🇿 Қазақша'}
TEACHING_LANGUAGES = {'ru': '🇷🇺 Только русский', 'kz': '🇰🇿 Тек қазақша', 'both': '🌐 На двух языках'}
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


def refresh_data() -> None:
    github_data.clear()
    material_bytes.clear()


def retrieve() -> tuple[dict, list[dict], str | None]:
    repo, branch, token = settings()
    try:
        config, tree = github_data(repo, branch, token)
        if not isinstance(config.get('courses'), list):
            raise GithubError('Неверный формат catalog.json.')
        return config, parse_materials(tree, config['courses']), None
    except (GithubError, ValueError, KeyError, TypeError) as exc:
        # A failed remote read must never show made-up remote materials.
        try:
            local = json.loads((BASE / 'catalog.json').read_text(encoding='utf-8'))
        except Exception:
            local = {'site_name': 'StudySpace', 'courses': []}
        return local, [], str(exc)


def route(page: str, *, lang: str | None = None, course: str = '', material: str = '') -> None:
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
    st.rerun()


def style() -> None:
    st.markdown('<style>'+(BASE/'assets/style.css').read_text(encoding='utf-8')+'</style>', unsafe_allow_html=True)


def header(title: str, subtitle: str = '', eyebrow: str = '') -> None:
    st.markdown(
        '<div class="heading-block">'
        + (f'<span class="eyebrow">{esc(eyebrow)}</span>' if eyebrow else '')
        + f'<h2>{esc(title)}</h2>'
        + (f'<p>{esc(subtitle)}</p>' if subtitle else '') + '</div>', unsafe_allow_html=True,
    )


def badge(text: str, variant: str = '') -> str:
    return f'<span class="badge-text {esc(variant)}">{esc(text)}</span>'


def initial_route(materials: list[dict]) -> None:
    if 'page' in st.session_state:
        return
    lang = st.query_params.get('lang', '')
    material_id = st.query_params.get('material', '')
    found = next((i for i in materials if i['id'] == material_id), None)
    if found:
        st.session_state.update(page='reader', lang=found['lang'], course=found['course_id'], material=material_id)
    elif lang in LANG_LABELS:
        st.session_state.update(page='home', lang=lang, course='', material='')
    else:
        st.session_state.update(page='welcome', lang='', course='', material='')


def sidebar(config: dict, materials: list[dict]) -> None:
    lang = st.session_state.get('lang')
    t = I18N.get(lang, I18N['ru'])
    active = st.session_state.get('page', 'welcome')
    with st.sidebar:
        st.markdown('<div class="brand"><div class="brand-icon">✳</div><div><b>StudySpace</b><small>LEARNING PLATFORM</small></div></div>', unsafe_allow_html=True)
        st.markdown('<div class="side-kicker">НАВИГАЦИЯ / NAVIGATION</div>', unsafe_allow_html=True)
        if lang in LANG_LABELS:
            st.markdown(f'<div class="side-language"><span class="side-lang-dot"></span><b>{esc(LANG_LABELS[lang])}</b><span class="lang-chevron">⌄</span></div>', unsafe_allow_html=True)
            nav = [('welcome', '✦', t['landing']), ('home', '⌂', t['home']), ('library', '▦', t['library']), ('about', '◎', t['about'])]
            for page, icon, label in nav:
                is_active = active == page
                if st.button(f'{icon}   {label}', key=f'nav-{page}', use_container_width=True, type='primary' if is_active else 'secondary'):
                    if page == 'welcome':
                        route('welcome', lang='')
                    else:
                        route(page)
            if st.button('⇄   '+t['change_lang'], use_container_width=True, key='nav-change-lang'):
                route('welcome', lang='')
        else:
            st.markdown('<div class="sidebar-intro">Один портал. Два языка.<small>Бір платформа. Екі тіл.</small></div>', unsafe_allow_html=True)
            if st.button('🌐   Выбрать язык / Тілді таңдау', use_container_width=True, key='nav-choose-lang', type='primary'):
                route('welcome', lang='')
        st.markdown('<div class="side-rule"></div><div class="side-kicker">УПРАВЛЕНИЕ</div>', unsafe_allow_html=True)
        if st.button('⚙   Панель преподавателя', use_container_width=True, key='nav-admin', type='primary' if active == 'admin' else 'secondary'):
            route('admin')
        st.markdown('<div class="sidebar-note"><span class="note-spark">✦</span><b>Твоя библиотека знаний</b><p>Лекции, презентации и материалы для самостоятельной подготовки.</p><span class="note-footer">PDF  ·  PPTX  ·  DOCX</span></div>', unsafe_allow_html=True)
        st.markdown('<div class="sidebar-copy">© 2026 STUDYSPACE <span>V 3.2</span></div>', unsafe_allow_html=True)


def welcome() -> None:
    with st.container(border=True):
        st.markdown('<div class="welcome-content"><div class="hero-overline"><span class="pulse-dot"></span> WELCOME TO STUDYSPACE <span class="overline-sep">/</span> EDUCATION HUB</div>'
                    '<div class="welcome-layout"><div class="welcome-copy"><div class="hero-mini">ТВОЁ ПРОСТРАНСТВО ДЛЯ УЧЁБЫ</div><h1>Учиться проще,<br><em>когда всё рядом.</em></h1>'
                    '<p>Лекции, презентации и полезные материалы собраны в одном удобном месте. Выбери язык — и открой нужный раздел обучения.</p>'
                    '<div class="hero-benefits"><span>✦ Без регистрации</span><span>◈ С любого устройства</span><span>↗ Всегда под рукой</span></div></div>'
                    '<div class="welcome-visual" aria-hidden="true"><div class="orbital-line orbital-one"></div><div class="orbital-line orbital-two"></div>'
                    '<div class="floating-doc main-doc"><div class="doc-head"><span></span><span></span><span></span></div><div class="doc-emblem">✳</div><div class="doc-line wide"></div><div class="doc-line"></div><div class="doc-line short"></div></div>'
                    '<div class="floating-doc side-doc"><div class="side-doc-icon">▦</div><div class="side-doc-text"><i></i><i></i></div></div>'
                    '<div class="visual-spark spark-a">✦</div><div class="visual-spark spark-b">✧</div></div></div></div>', unsafe_allow_html=True)
    st.markdown('<div class="section-head"><div><span class="eyebrow">01 / START LEARNING</span><h2>Выбери язык обучения <span class="text-gradient">↗</span></h2><p>Әр тілге арналған оқу материалдары бөлек көрсетіледі.</p></div></div>', unsafe_allow_html=True)
    a, b = st.columns(2, gap='large')
    with a:
        with st.container(border=True):
            st.markdown('<div class="language-card lang-ru"><div class="lang-card-top"><span class="lang-flag">RU</span><span class="lang-label">РУССКИЙ РАЗДЕЛ</span><span class="lang-arrow">↗</span></div><h3>Русский язык</h3><p>Лекции, презентации и дополнительные материалы на русском языке.</p><div class="lang-divider"></div><span class="lang-bottom">НАЧАТЬ ОБУЧЕНИЕ <span>→</span></span></div>', unsafe_allow_html=True)
            if st.button('Открыть библиотеку  ↗', type='primary', use_container_width=True, key='choose_ru'):
                route('home', lang='ru')
    with b:
        with st.container(border=True):
            st.markdown('<div class="language-card lang-kz"><div class="lang-card-top"><span class="lang-flag">KZ</span><span class="lang-label">ҚАЗАҚША БӨЛІМ</span><span class="lang-arrow">↗</span></div><h3>Қазақ тілі</h3><p>Қазақ тіліндегі дәрістер, презентациялар және оқу материалдары.</p><div class="lang-divider"></div><span class="lang-bottom">ОҚУДЫ БАСТАУ <span>→</span></span></div>', unsafe_allow_html=True)
            if st.button('Кітапхананы ашу  ↗', type='primary', use_container_width=True, key='choose_kz'):
                route('home', lang='kz')
    st.markdown('<div class="trustline"><span class="trust-icon">✳</span> Твой цифровой кампус. Просто открой и учись. <span>•</span> Жеке тіркелу қажет емес.</div>', unsafe_allow_html=True)


def course_card(course: dict, lang: str, items: list[dict], index: int = 0) -> None:
    t = I18N[lang]
    count = sum(m['lang'] == lang and m['course_id'] == course['id'] for m in items)
    with st.container(border=True):
        st.markdown(
            f'<div class="course-card-body card-tone-{index % 6}"><div class="course-head">'
            f'<div class="course-emoji">{esc(course.get("icon", "📘"))}</div><span class="course-number">{index+1:02d} / COURSE</span></div>'
            f'<h3>{esc(display_course(course, lang))}</h3>'
            f'<div class="course-card-foot"><span><span class="course-dot"></span>{count} {esc(t["materials"])}</span><span class="course-go">↗</span></div></div>',
            unsafe_allow_html=True,
        )
        if st.button(t['open']+'   ↗', use_container_width=True, key=f'course_{lang}_{course["id"]}'):
            route('library', course=course['id'])


def card(item: dict, lang: str, prefix: str = '') -> None:
    t = I18N[lang]
    kindtext = t['lectures_one'] if item['kind'] == 'lectures' else t['presentations_one']
    file_icon = '▣' if item['kind'] == 'presentations' else '▤'
    with st.container(border=True):
        st.markdown(
            '<div class="material-card-body">'
            + f'<div class="material-top"><span class="file-icon">{file_icon}</span><div class="material-meta">'
            + badge(kindtext, 'lecture' if item['kind'] == 'lectures' else 'presentation')
            + badge(item['extension'].lstrip('.').upper())+'</div></div>'
            + f'<span class="material-course">{esc(display_course(item["course"], lang))}</span>'
            + f'<h3>{esc(item["title"])}</h3><p>{esc(human_size(item["size"]))} <span class="material-bullet">·</span> {esc(t["view"])}</p></div>',
            unsafe_allow_html=True,
        )
        if st.button(t['open_item']+'   ↗', use_container_width=True, key=f'item_{prefix}_{item["id"]}'):
            route('reader', course=item['course_id'], material=item['id'])


def home(config: dict, materials: list[dict], lang: str) -> None:
    t = I18N[lang]
    visible_courses = [c for c in config['courses'] if lang in course_languages(c)]
    visible = [m for m in materials if m['lang'] == lang]
    total_lectures = sum(i['kind'] == 'lectures' for i in visible)
    total_presentations = len(visible)-total_lectures
    headline = ('Знания ближе, чем <em>кажется.</em>' if lang == 'ru' else 'Білімнің бәрі <em>осында.</em>')
    with st.container(border=True):
        st.markdown(
            f'<div class="home-hero"><div class="hero-overline"><span class="pulse-dot"></span> {esc(t["hero_tag"])}</div>'
            f'<div class="home-content"><div class="home-copy"><span class="hero-mini">STUDYSPACE <span class="mini-line"></span> 2026</span>'
            f'<h1>{headline}</h1><p>{esc(t["hero_sub"])}</p>'
            f'<div class="hero-benefits"><span>◈ PDF / PPTX / DOCX</span><span>✦ RU / KZ</span><span>↗ ONLINE</span></div></div>'
            '<div class="home-art" aria-hidden="true"><div class="home-ring"></div><div class="art-glass art-back">▤</div><div class="art-glass art-front"><span class="art-star">✳</span><div class="art-bar"></div><div class="art-bar art-short"></div><span class="art-stamp">EDUCATION</span></div><span class="art-floating">✦</span></div></div></div>',
            unsafe_allow_html=True,
        )
        if st.button(t['browse']+'   ↗', type='primary', key='hero_browse'):
            route('library')
    st.markdown(
        f'<div class="stat-strip"><div><span class="stat-icon">◫</span><b>{len(visible_courses):02d}</b><span>{esc(t["courses"])}</span></div>'
        f'<div><span class="stat-icon">▦</span><b>{len(visible):02d}</b><span>{esc(t["materials"])}</span></div>'
        f'<div><span class="stat-icon">▤</span><b>{total_lectures:02d}</b><span>{esc(t["lectures"])}</span></div>'
        f'<div><span class="stat-icon">▣</span><b>{total_presentations:02d}</b><span>{esc(t["presentations"])}</span></div></div>',
        unsafe_allow_html=True,
    )
    header(t['courses'], t['course_sub'], '02 / DISCOVER')
    if not visible_courses:
        empty(t['empty_courses'], t['empty_desc'])
        return
    cols = st.columns(3, gap='medium')
    for index, course in enumerate(visible_courses):
        with cols[index % 3]:
            course_card(course, lang, materials, index)


def empty(title: str, subtitle: str) -> None:
    st.markdown(f'<div class="empty-state"><div class="empty-symbol"><span>✦</span>▤</div><span class="eyebrow">COMING SOON</span><h3>{esc(title)}</h3><p>{esc(subtitle)}</p><div class="empty-dashes"><i></i><i></i><i></i></div></div>', unsafe_allow_html=True)


def library(config: dict, materials: list[dict], lang: str) -> None:
    t = I18N[lang]
    header(t['catalog_head'], t['catalog_sub'], 'LIBRARY / '+LANG_LABELS[lang])
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
    with st.container(border=True):
        st.markdown('<div class="filter-header"><div><span class="filter-icon">⌕</span><b>Фильтры / Іздеу</b></div><span>FIND YOUR CONTENT</span></div>', unsafe_allow_html=True)
        a, b = st.columns([1.25, 1], gap='medium')
        with a:
            query = st.text_input(t['search'], placeholder=t['search_hint'], key=f'catalog_search_{lang}')
        with b:
            selected_course = st.selectbox(t['subject'], options, index=options.index(current),
                                           format_func=lambda slug: t['all_subjects'] if slug == 'all' else display_course(next(c for c in courses if c['id'] == slug), lang),
                                           key=f'course_selector_{lang}')
        c, _ = st.columns([1, 1], gap='medium')
        with c:
            kind = st.selectbox(t['kind'], ['all', 'lectures', 'presentations'],
                                format_func=lambda key: {'all':t['all_kinds'], 'lectures':t['lectures_one'], 'presentations':t['presentations_one']}[key],
                                key=f'kind_selector_{lang}')
    query = query.strip().casefold()
    filtered = [m for m in materials if m['lang'] == lang and (selected_course == 'all' or m['course_id'] == selected_course)
                and (kind == 'all' or m['kind'] == kind)
                and (not query or query in (m['title']+' '+display_course(m['course'],lang)+' '+m['filename']).casefold())]
    st.markdown(f'<div class="result-count"><span class="result-pip"></span>{esc(t["materials"])}: <b>{len(filtered)}</b><span class="result-rule"></span><span>STUDYSPACE CATALOG</span></div>', unsafe_allow_html=True)
    if not filtered:
        empty(t['empty_materials'], t['course_sub'])
        return
    cols = st.columns(2, gap='medium')
    for n, material in enumerate(filtered):
        with cols[n % 2]:
            card(material, lang, 'library')


def reader(materials: list[dict], lang: str) -> None:
    t = I18N[lang]
    item_id = st.session_state.get('material', '')
    item = next((m for m in materials if m['id'] == item_id), None)
    if not item:
        st.warning(t['unavailable'])
        if st.button(t['back']):
            route('library')
        return
    if item['lang'] != lang:
        lang = item['lang']; t = I18N[lang]
    if st.button(t['back'], key='back_reader'):
        route('library', lang=lang, course=item['course_id'])
    header(item['title'], display_course(item['course'], lang), t['lectures_one'] if item['kind'] == 'lectures' else t['presentations_one'])
    st.markdown(f'<div class="reader-tags">{badge(item["extension"].lstrip(".").upper())}{badge(LANG_LABELS[lang])}{badge(human_size(item["size"]))}</div>', unsafe_allow_html=True)
    repo, branch, _ = settings()
    try:
        filedata = material_bytes(repo, branch, item['path'], item['sha'])
    except GithubError as exc:
        st.error(str(exc))
        return
    suffix = item['extension']
    if suffix == '.pdf':
        try:
            st.pdf(filedata, height=680)
        except Exception:
            st.info(t['no_preview'])
    elif suffix in ('.md', '.txt'):
        with st.container(border=True):
            text = filedata.decode('utf-8-sig', errors='replace')
            if suffix == '.md':
                st.markdown(text)
            else:
                st.text(text)
    elif suffix == '.html':
        components.html(filedata.decode('utf-8-sig', errors='replace'), height=650, scrolling=True)
    else:
        st.info(t['preview'])
    st.download_button(t['download'], filedata, file_name=item['filename'],
                       mime=mimetypes.guess_type(item['filename'])[0] or 'application/octet-stream',
                       type='primary', use_container_width=True, key='reader_download')
    st.caption('StudySpace · '+t['quick'])


def about(lang: str) -> None:
    t = I18N[lang]
    header(t['about_head'], t['about_body'], 'ABOUT / STUDYSPACE')
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


def admin(config: dict, materials: list[dict]) -> None:
    header('Твоя учебная платформа.', 'Создавай дисциплины, загружай файлы и управляй цифровой библиотекой.', 'ADMIN / TEACHER WORKSPACE')
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
            if hmac.compare_digest(pwd.encode('utf-8'), admin_password.encode('utf-8')):
                st.session_state['admin_ok'] = True
                st.rerun()
            else:
                st.error('Неверный пароль.')
        return
    top, out = st.columns([4, 1])
    with top:
        st.caption(f'🟢 Вход выполнен · Репозиторий: {repo} · Ветка: {branch}')
    with out:
        if st.button('Выйти', use_container_width=True, key='logout'):
            st.session_state['admin_ok'] = False
            route('welcome', lang='')
    flash()
    if not token:
        st.error('Добавь GITHUB_TOKEN в секреты Streamlit Cloud: без токена создавать дисциплины и загружать файлы нельзя.')
        return
    github = GithubStore(repo, branch, token)
    stats = st.columns(3, gap='medium')
    for col, label, number, symbol in zip(stats, ['Дисциплины', 'Лекции', 'Презентации'], [len(config['courses']), sum(m['kind'] == 'lectures' for m in materials), sum(m['kind'] == 'presentations' for m in materials)], ['▦','▤','▣']):
        with col:
            st.markdown(f'<div class="admin-stat"><div class="admin-stat-head"><span>{esc(label)}</span><i>{symbol}</i></div><strong>{number:02d}</strong><div class="admin-stat-foot">STUDYSPACE · LIVE</div></div>',unsafe_allow_html=True)
    st.markdown('<div class="admin-section-heading"><span class="eyebrow">TOOLS / УПРАВЛЕНИЕ</span><h3>Контент и дисциплины</h3><p>Все изменения сохраняются непосредственно в твоём репозитории GitHub.</p></div>', unsafe_allow_html=True)
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
                    kind = st.radio('Что загружаем? *', ['lectures', 'presentations'],
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
                                successes.append(filename)
                            except (GithubError, ValueError) as exc:
                                failures.append(f'{file.name}: {exc}')
                        if successes:
                            refresh_data()
                            st.session_state['success_msg'] = f'✅ Загружено файлов: {len(successes)}. Они уже сохранены в GitHub.'
                        if failures:
                            st.session_state['warning_msg'] = 'Не удалось загрузить:\n'+'\n'.join(failures)
                        if successes:
                            st.rerun()
                        if failures:
                            st.warning(st.session_state.pop('warning_msg'))
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
                st.caption('Удаление из каталога скрывает предмет для студентов, но не стирает файлы из GitHub.')
                confirm = st.checkbox('Подтверждаю удаление из каталога', key='confirm_delete_'+c['id'])
                if st.button('Убрать дисциплину', disabled=not confirm, key='delete_course_'+c['id']):
                    try:
                        live = github.read_catalog()
                        live['courses'] = [x for x in live.get('courses',[]) if x['id'] != c['id']]
                        github.write_file('catalog.json', (json.dumps(live,ensure_ascii=False,indent=2)+'\n').encode('utf-8'),
                                          'StudySpace: hide course '+c['id'], replace=True)
                        refresh_data()
                        st.session_state['success_msg']='Дисциплина скрыта из каталога. Файлы в GitHub сохранены.'
                        st.rerun()
                    except GithubError as exc:
                        st.error(str(exc))
        st.caption('Открыть GitHub: '+f'https://github.com/{repo}/tree/{branch}/materials/uploads')


def main() -> None:
    style()
    config, materials, error = retrieve()
    initial_route(materials)
    sidebar(config, materials)
    page = st.session_state.get('page', 'welcome')
    lang = st.session_state.get('lang', '')
    top_label = 'ADMIN CONSOLE' if page == 'admin' else ('ҚАЗАҚША БӨЛІМ' if lang == 'kz' else 'РУССКИЙ РАЗДЕЛ' if lang == 'ru' else 'RU / KZ')
    st.markdown(f'<div class="top-brand"><span><span class="top-mark">✳</span> STUDYSPACE <span class="top-slash">/</span> EDUCATION HUB</span><span class="top-status"><i></i>{esc(top_label)}</span></div>', unsafe_allow_html=True)
    if error and page == 'admin':
        st.warning('Каталог GitHub временно недоступен. Показана локальная версия. '+error)
    if page == 'admin':
        admin(config, materials)
    elif page == 'welcome' or lang not in LANG_LABELS:
        welcome()
    elif page == 'home':
        home(config, materials, lang)
    elif page == 'library':
        library(config, materials, lang)
    elif page == 'reader':
        reader(materials, lang)
    elif page == 'about':
        about(lang)
    else:
        welcome()
    st.markdown('<div class="footer"><span>✳ STUDYSPACE</span><span>MADE FOR LEARNING  ·  © 2026</span></div>', unsafe_allow_html=True)


if __name__ == '__main__':
    main()
