"""Background full-text index for the search palette. No Streamlit imports.

The app serves the result as a static JSON file (url -> text); fx.js downloads it
the first time the palette opens and searches it in the browser.
"""
from __future__ import annotations

import io
import json
import re
import threading
from pathlib import Path
from typing import Callable

from pypdf import PdfReader

TEXT_LIMIT = 40_000  # characters kept per document; enough for lectures, keeps the JSON small
SEARCHABLE = {'.pdf', '.md', '.txt'}


def extract_text(data: bytes, extension: str) -> str:
    if extension == '.pdf':
        parts, size = [], 0
        for page in PdfReader(io.BytesIO(data)).pages:
            text = page.extract_text() or ''
            parts.append(text)
            size += len(text)
            if size > TEXT_LIMIT:
                break
        text = ' '.join(parts)
    elif extension in ('.md', '.txt'):
        text = data.decode('utf-8-sig', errors='replace')
    else:
        return ''
    return re.sub(r'\s+', ' ', text).strip()[:TEXT_LIMIT]


class FullText:
    """Rebuilds the JSON in a daemon thread whenever the set of (path, sha) changes."""

    def __init__(self, target: Path):
        self.target = target
        self.lock = threading.Lock()
        self.signature: tuple | None = None
        self.running = False
        self.cache: dict[str, str] = {}  # sha -> text, so unchanged files are never fetched twice

    def refresh(self, docs: list[dict], fetch: Callable[[str, str], bytes]) -> None:
        """docs: dicts with u (palette url), path, sha, extension."""
        docs = [d for d in docs if d['extension'] in SEARCHABLE]
        signature = tuple(sorted((d['path'], d['sha']) for d in docs))
        with self.lock:
            if self.running or signature == self.signature:
                return
            self.running = True
        threading.Thread(target=self.build, args=(docs, fetch, signature), daemon=True).start()

    def build(self, docs: list[dict], fetch: Callable[[str, str], bytes], signature: tuple) -> None:
        try:
            out = {}
            for doc in docs:
                text = self.cache.get(doc['sha'])
                if text is None:
                    try:
                        text = extract_text(fetch(doc['path'], doc['sha']), doc['extension'])
                    except Exception:  # noqa: BLE001 — a broken or scanned file just stays unsearchable
                        text = ''
                    self.cache[doc['sha']] = text
                if text:
                    out[doc['u']] = text
            self.target.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.target.with_suffix('.tmp')
            tmp.write_text(json.dumps(out, ensure_ascii=False), encoding='utf-8')
            tmp.replace(self.target)  # atomic: the browser never reads a half-written file
            self.signature = signature
        finally:
            self.running = False
