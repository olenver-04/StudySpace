"""Offline test harness: a fake GitHub with a small catalog; writes are recorded, never sent."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import fulltext  # noqa: E402
import github_store  # noqa: E402
import requests  # noqa: E402
import streamlit as st  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(ROOT / 'app.py')
U = 'materials/uploads/'
CATALOG = {'courses': [
    {'id': 'algo', 'title_ru': 'Алгоритмы', 'title_kz': 'Алгоритмдер', 'icon': '🧮', 'languages': ['ru', 'kz']},
    {'id': 'java', 'title_ru': 'Java', 'title_kz': '', 'icon': '☕', 'languages': ['ru']},
]}
FILES = [
    'algo/ru/lectures/Лекция_10.pdf', 'algo/ru/lectures/Лекция_2.pdf', 'algo/ru/presentations/Слайды.pptx',
    'algo/kz/presentations/Дәріс_1.pdf', 'algo/kz/lectures/notes.txt', 'algo/kz/lectures/page.html',
    'java/ru/lectures/intro.md', 'java/kz/lectures/hidden.pdf',  # java has no kz section: must stay hidden
]
TREE = [{'path': U + f, 'type': 'blob', 'sha': f'sha{n}', 'size': 2048} for n, f in enumerate(FILES)]
BYTES = {'.pdf': b'%PDF-1.4\n%%EOF', '.html': b'<p>html lecture</p>', '.txt': b'plain text', '.md': b'# md', '.pptx': b'PK'}


class Recorder:
    def __init__(self):
        self.calls: list[tuple] = []
        self.recent: dict[str, str] | Exception = {}
        self.telegram: list[dict] = []


@pytest.fixture
def gh(monkeypatch):
    rec = Recorder()

    def recent_files(self, since, limit=30):
        if isinstance(rec.recent, Exception):
            raise rec.recent
        return rec.recent

    def post(url, json=None, timeout=None, **_):
        rec.telegram.append(json)

        class Reply:
            @staticmethod
            def json():
                return {'ok': True, 'result': []}
        return Reply()

    monkeypatch.setattr(github_store.GithubStore, 'read_catalog', lambda self: {'courses': [dict(c) for c in CATALOG['courses']]})
    monkeypatch.setattr(github_store.GithubStore, 'tree', lambda self: [dict(t) for t in TREE])
    monkeypatch.setattr(github_store.GithubStore, 'raw_bytes', lambda self, path, sha: BYTES[Path(path).suffix])
    monkeypatch.setattr(github_store.GithubStore, 'recent_files', recent_files)
    monkeypatch.setattr(github_store.GithubStore, 'write_file',
                        lambda self, path, data, message, replace=False: rec.calls.append(('write', path, len(data))))
    monkeypatch.setattr(github_store.GithubStore, 'delete_file', lambda self, path, sha, message: rec.calls.append(('delete', path)))
    monkeypatch.setattr(requests, 'post', post)
    # The background full-text build would write into the real static/ folder; its own tests call build() directly.
    monkeypatch.setattr(fulltext.FullText, 'refresh', lambda self, docs, fetch: None)
    st.cache_data.clear()
    st.cache_resource.clear()
    return rec


def app(page='welcome', lang='', course='', material='', admin=False, secrets=None) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=60)
    for key, value in {'GITHUB_TOKEN': 'test-token', **(secrets or {})}.items():
        at.secrets[key] = value
    at.session_state['page'] = page
    at.session_state['lang'] = lang
    at.session_state['course'] = course
    at.session_state['material'] = material
    at.session_state['admin_ok'] = admin
    return at


def html_of(at: AppTest) -> str:
    return '\n'.join(str(m.value) for m in at.markdown)
