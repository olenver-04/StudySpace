"""StudySpace — публичный учебный портал на Streamlit.

Материалы автоматически обнаруживаются в materials/uploads/<id дисциплины>/.
Без БД и без платного API: новые файлы добавляются обычным коммитом в GitHub.
"""
from __future__ import annotations

import html
import json
import mimetypes
import re
from collections import Counter
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

BASE = Path(__file__).resolve().parent
UPLOADS = BASE / "materials" / "uploads"
CSS_FILE = BASE / "assets" / "style.css"
SUPPORTED = {".pdf", ".pptx", ".ppt", ".docx", ".doc", ".md", ".txt", ".html"}
PREVIEWABLE_TEXT = {".md", ".txt"}

st.set_page_config(
    page_title="StudySpace • Учебная библиотека",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def load_catalog() -> dict:
    with (BASE / "catalog.json").open(encoding="utf-8") as f:
        return json.load(f)


def friendly_filename(stem: str) -> str:
    stem = re.sub(r"(?i)[_-](?:ru|kz|kk)$", "", stem)
    return re.sub(r"[_-]+", " ", stem).strip().capitalize()


def detect_language(stem: str) -> str:
    return "KZ" if re.search(r"(?i)[_-](?:kz|kk)$", stem) else "RU"


def detect_type(filename: str, suffix: str) -> str:
    if suffix in {".html", ".ppt", ".pptx"}:
        return "Презентация"
    if suffix in {".md", ".txt", ".doc", ".docx"}:
        return "Лекция"
    if re.search(r"(?i)lekciya|lektsiya|lecture|лекция|дәріс|daris", filename):
        return "Лекция"
    return "Презентация"  # PDF: по умолчанию слайды, если не указано «лекция».


def file_size(num: int) -> str:
    if num < 1024 * 1024:
        return f"{max(1, round(num / 1024))} КБ"
    return f"{num / (1024 * 1024):.1f} МБ"


def get_materials(config: dict) -> list[dict]:
    items: list[dict] = []
    for course in config["courses"]:
        slug = course["id"]
        # catalog.json — доверенный код проекта, но пути всё равно ограничены папкой uploads.
        if not re.fullmatch(r"[a-z0-9_-]+", slug):
            continue
        folder = UPLOADS / slug
        if not folder.exists():
            continue
        for path in sorted(folder.iterdir(), key=lambda p: p.name.casefold()):
            if not path.is_file() or path.suffix.lower() not in SUPPORTED:
                continue
            suffix = path.suffix.lower()
            key = f"{slug}/{path.name}"
            items.append({
                "id": key,
                "path": path,
                "title": config.get("titles", {}).get(key, friendly_filename(path.stem)),
                "description": config.get("descriptions", {}).get(
                    key, f"Учебный материал по дисциплине «{course['title']}»."
                ),
                "course": course,
                "kind": detect_type(path.stem, suffix),
                "lang": detect_language(path.stem),
                "extension": suffix[1:].upper(),
                "size": file_size(path.stat().st_size),
            })
    return items


def go(page: str, *, course: str | None = None, item: str | None = None) -> None:
    st.session_state.page = page
    if course is not None:
        st.session_state.subject_filter = course
    if item is not None:
        st.session_state.item = item
        st.query_params["material"] = item
    else:
        st.query_params.clear()
    st.rerun()


def pill(text: str, tone: str = "") -> str:
    return f'<span class="tag {esc(tone)}">{esc(text)}</span>'


def heading(title: str, subtitle: str = "") -> None:
    st.markdown(
        f'<div class="section-title"><h2>{esc(title)}</h2>'
        + (f"<p>{esc(subtitle)}</p>" if subtitle else "")
        + "</div>",
        unsafe_allow_html=True,
    )


def course_card(course: dict, count: int) -> None:
    with st.container(border=True):
        st.markdown(
            f'<div class="course-content">'
            f'<div class="course-icon {esc(course["tone"])}">{esc(course["icon"])}</div>'
            f'<div class="course-info">{pill(course["level"])}<span class="course-count">{count} материалов</span></div>'
            f'<h3>{esc(course["title"])}</h3>'
            f'<p>{esc(course["description"])}</p></div>',
            unsafe_allow_html=True,
        )
        if st.button("Открыть дисциплину  →", key="course_" + course["id"], use_container_width=True):
            go("library", course=course["id"])


def material_card(item: dict, keyprefix: str = "") -> None:
    badge_kind = "is-presentation" if item["kind"] == "Презентация" else "is-lecture"
    with st.container(border=True):
        st.markdown(
            f'<div class="material-content">'
            f'<div class="material-meta">{pill(item["kind"], badge_kind)}{pill(item["lang"])}{pill(item["extension"])}</div>'
            f'<div class="material-course">{esc(item["course"]["title"])}</div>'
            f'<h3>{esc(item["title"])}</h3>'
            f'<p>{esc(item["description"])}</p>'
            f'<div class="material-size">↳ {esc(item["size"])} · для просмотра и скачивания</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        if st.button("Открыть материал  →", key=f"open_{keyprefix}_{item['id']}", use_container_width=True):
            go("reader", item=item["id"])


def render_home(config: dict, materials: list[dict]) -> None:
    counts = Counter(i["course"]["id"] for i in materials)
    st.markdown(
        '<div class="hero">'
        '<div class="hero-glow"></div>'
        '<span class="hero-eyebrow"><span class="live-dot"></span> ОБРАЗОВАТЕЛЬНАЯ ПЛАТФОРМА</span>'
        '<h1>Знания всегда <span>под рукой.</span></h1>'
        '<p>Все лекции, презентации и полезные материалы по специальным дисциплинам — '
        'в удобной цифровой библиотеке. Открывай, изучай, скачивай.</p>'
        '<div class="hero-chips"><span>✦ Учись в своём темпе</span><span>↗ Открывай с телефона</span>'
        '<span>↓ Сохраняй материалы</span></div>'
        '</div>',
        unsafe_allow_html=True,
    )
    a, b, _ = st.columns([1.1, 1.1, 2], gap="small")
    with a:
        if st.button("Смотреть все материалы  →", type="primary", key="hero_browse", use_container_width=True):
            go("library", course="all")
    with b:
        if st.button("Выбрать дисциплину  ↓", key="hero_subjects", use_container_width=True):
            st.session_state.page = "library"
            st.session_state.subject_filter = "all"
            st.rerun()

    presentations = sum(m["kind"] == "Презентация" for m in materials)
    lectures = sum(m["kind"] == "Лекция" for m in materials)
    st.markdown(
        '<div class="stats">'
        f'<div class="stat"><b>{len(config["courses"]):02d}</b><span>дисциплин</span></div>'
        f'<div class="stat"><b>{len(materials):02d}</b><span>учебных материалов</span></div>'
        f'<div class="stat"><b>{presentations:02d}</b><span>презентаций</span></div>'
        f'<div class="stat"><b>{lectures:02d}</b><span>лекций</span></div>'
        '</div>',
        unsafe_allow_html=True,
    )

    heading("Выбери дисциплину", "Все материалы распределены по предметам, чтобы нужное было легко найти.")
    columns = st.columns(3, gap="medium")
    for idx, course in enumerate(config["courses"]):
        with columns[idx % 3]:
            course_card(course, counts[course["id"]])

    heading("С чего начать", "Несколько материалов, которые уже можно открыть прямо на сайте.")
    featured = [m for m in materials if m["extension"] == "HTML"][:2]
    featured += [m for m in materials if m["extension"] == "MD"][:1]
    featured_columns = st.columns(3, gap="medium")
    for idx, item in enumerate(featured):
        with featured_columns[idx]:
            material_card(item, "featured")


def render_library(config: dict, materials: list[dict]) -> None:
    st.markdown('<span class="eyebrow">КАТАЛОГ / STUDYSPACE</span>', unsafe_allow_html=True)
    heading("Библиотека материалов", "Ищи по названию и предмету, выбирай язык и формат.")
    course_names = {"all": "Все дисциплины", **{c["id"]: c["title"] for c in config["courses"]}}
    st.session_state.setdefault("subject_filter", "all")
    if st.session_state.subject_filter not in course_names:
        st.session_state.subject_filter = "all"
    search_col, subject_col = st.columns([1.5, 1], gap="medium")
    with search_col:
        query = st.text_input("Поиск по материалам", placeholder="Например, циклы Java, SQL или ООП...", key="query")
    with subject_col:
        subject = st.selectbox(
            "Дисциплина", list(course_names),
            format_func=lambda c: course_names[c],
            key="subject_filter",
        )
    kind_col, lang_col, sort_col = st.columns(3, gap="medium")
    with kind_col:
        kind = st.selectbox("Тип материала", ["Все форматы", "Презентация", "Лекция"])
    with lang_col:
        lang = st.selectbox("Язык", ["Любой язык", "RU", "KZ"])
    with sort_col:
        sort = st.selectbox("Сортировка", ["По названию", "По дисциплине", "По формату"])
    q = query.strip().casefold()
    filtered = [
        m for m in materials
        if (subject == "all" or m["course"]["id"] == subject)
        and (kind == "Все форматы" or m["kind"] == kind)
        and (lang == "Любой язык" or m["lang"] == lang)
        and (not q or q in " ".join((m["title"], m["description"], m["course"]["title"], m["path"].name)).casefold())
    ]
    if sort == "По названию":
        filtered.sort(key=lambda m: m["title"].casefold())
    elif sort == "По дисциплине":
        filtered.sort(key=lambda m: (m["course"]["title"], m["title"]))
    else:
        filtered.sort(key=lambda m: (m["kind"], m["title"]))
    st.markdown(
        f'<div class="results">Найдено материалов: <strong>{len(filtered)}</strong></div>',
        unsafe_allow_html=True,
    )
    if not filtered:
        st.info("По этим фильтрам материалов пока нет. Попробуй другой запрос или дисциплину.")
        if st.button("Показать всё"):
            st.session_state.subject_filter = "all"
            st.session_state.query = ""
            st.rerun()
        return
    columns = st.columns(2, gap="medium")
    for idx, item in enumerate(filtered):
        with columns[idx % 2]:
            material_card(item, "catalog")


def render_reader(materials: list[dict], item_id: str) -> None:
    item = next((x for x in materials if x["id"] == item_id), None)
    if not item:
        st.warning("Этот материал не найден. Возможно, файл переименовали или удалили.")
        if st.button("← Вернуться в библиотеку"):
            go("library")
        return
    if st.button("← Назад к материалам", key="back_to_catalog"):
        go("library", course=item["course"]["id"])
    st.markdown(
        f'<div class="reader-head"><span class="eyebrow">{esc(item["course"]["title"])} / {esc(item["kind"])}</span>'
        f'<h1>{esc(item["title"])}</h1>'
        f'<p>{esc(item["description"])}</p><div class="material-meta">'
        f'{pill(item["kind"])}{pill(item["lang"])}{pill(item["extension"])}{pill(item["size"])}'
        f'</div></div>',
        unsafe_allow_html=True,
    )
    path = item["path"]
    suffix = path.suffix.lower()
    if suffix == ".html":
        components.html(path.read_text(encoding="utf-8"), height=600, scrolling=False)
        st.caption("Интерактивная презентация: переключай слайды стрелками, кнопками или свайпом. Значок ⛶ откроет её на весь экран.")
    elif suffix == ".pdf":
        try:
            st.pdf(str(path), height=700)
        except Exception:
            st.info("Предпросмотр PDF недоступен в этой среде. Скачай файл по кнопке ниже.")
    elif suffix in PREVIEWABLE_TEXT:
        with st.container(border=True):
            text = path.read_text(encoding="utf-8")
            if suffix == ".md":
                st.markdown(text)
            else:
                st.text(text)
    else:
        st.info(f"Файл {item['extension']} можно скачать и открыть в подходящей программе. Просмотр этого формата на сайте не предусмотрен.")

    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    st.download_button(
        "↓ Скачать материал",
        data=path.read_bytes(),
        file_name=path.name,
        mime=mime,
        key="download_" + item["id"],
        use_container_width=True,
        type="primary",
    )
    st.caption("Можно отправить одногруппникам ссылку на этот материал, скопировав адрес страницы в браузере.")
    related = [x for x in materials if x["course"]["id"] == item["course"]["id"] and x["id"] != item_id][:2]
    if related:
        heading("Ещё по этой дисциплине")
        cols = st.columns(2)
        for idx, m in enumerate(related):
            with cols[idx]:
                material_card(m, "related")


def render_about(config: dict) -> None:
    st.markdown('<span class="eyebrow">ОБРАЗОВАТЕЛЬНЫЙ ПРОЕКТ</span>', unsafe_allow_html=True)
    heading("О библиотеке", "Коротко о том, как пользоваться учебным порталом.")
    with st.container(border=True):
        st.markdown("""
### Для студентов

Зайди в **Библиотеку**, выбери дисциплину и найди нужную тему. Лекции Markdown доступны для чтения прямо на странице; PDF и интерактивные HTML-презентации можно просматривать в браузере. Любой материал можно скачать для самостоятельной работы.

### Для преподавателя

Чтобы добавить файл, открой репозиторий на GitHub и перейди в `materials/uploads/`. Затем выбери папку нужной дисциплины и добавь `.pdf`, `.pptx`, `.docx`, `.md`, `.txt` или `.html`. После сохранения коммита и обновления сайта новая карточка появится автоматически.

**Важно:** это публичная библиотека без регистрации. Размещай только учебные материалы, которые можно свободно показывать студентам. Временное хранилище самого Streamlit не используется для загрузок, поэтому файлы не пропадают после перезапуска приложения.
""")
    st.markdown(f'<div class="muted-note">{esc(config["site_name"])} · создано на Streamlit</div>', unsafe_allow_html=True)


def sidebar(config: dict, total: int) -> None:
    with st.sidebar:
        st.markdown(
            '<div class="side-brand"><div class="side-logo">✳</div>'
            '<div><b>StudySpace</b><small>EDUCATION HUB</small></div></div>',
            unsafe_allow_html=True,
        )
        st.markdown('<div class="side-label">НАВИГАЦИЯ</div>', unsafe_allow_html=True)
        for key, label in (("home", "⌂  Главная"), ("library", "▦  Библиотека"), ("about", "ⓘ  О портале")):
            if st.button(label, use_container_width=True, key=f"nav_{key}"):
                go(key)
        st.markdown('<div class="side-label space-top">УЧЕБНЫЙ КОНТЕНТ</div>', unsafe_allow_html=True)
        st.markdown(
            f'<div class="side-note"><b>{len(config["courses"])} дисциплин · {total} материалов</b>'
            '<p>Всё для самостоятельной подготовки и повторения тем.</p>'
            '<span>📖 Лекции &nbsp;·&nbsp; 🖥 Презентации</span></div>',
            unsafe_allow_html=True,
        )
        st.markdown('<div class="side-footer">Доступно с телефона и компьютера<br>StudySpace © 2026</div>', unsafe_allow_html=True)


def main() -> None:
    st.markdown(f"<style>{CSS_FILE.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)
    config = load_catalog()
    materials = get_materials(config)
    if "page" not in st.session_state:
        share_item = st.query_params.get("material")
        st.session_state.page = "reader" if share_item else "home"
        st.session_state.item = share_item or ""
    sidebar(config, len(materials))
    st.markdown('<div class="top-line"><span>✳ STUDYSPACE</span><span>УЧИСЬ · ПРАКТИКУЙСЯ · РАЗВИВАЙСЯ</span></div>', unsafe_allow_html=True)
    if st.session_state.page == "home":
        render_home(config, materials)
    elif st.session_state.page == "library":
        render_library(config, materials)
    elif st.session_state.page == "reader":
        render_reader(materials, st.session_state.get("item", ""))
    else:
        render_about(config)
    st.markdown('<div class="bottom-footer">StudySpace · Открытая библиотека учебных материалов · 2026</div>', unsafe_allow_html=True)


if __name__ == "__main__":
    main()
