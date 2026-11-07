"""Background library index: searchable text, slide counts and cover thumbnails. No Streamlit imports.

One pass over the materials (each file is fetched once) produces:
  * static/fulltext.json   url -> text, searched in the browser by the palette (fx.js);
  * static/thumbs/<sha>.webp  first page of each PDF, used as the material's cover;
  * FullText.pages          sha -> page (slide) count, read by the app.
"""
from __future__ import annotations

import io
import json
import re
import threading
from pathlib import Path
from typing import Callable

import pypdfium2 as pdfium
from pypdf import PdfReader

TEXT_LIMIT = 40_000  # characters kept per document; enough for lectures, keeps the JSON small
THUMB_WIDTH = 640    # px; covers are shown at most ~400 px wide, 2x for sharp screens
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


def render_cover(data: bytes, target: Path) -> int:
    """Writes the first page as WebP (atomically) and returns the page count."""
    pdf = pdfium.PdfDocument(data)
    try:
        count = len(pdf)
        if count and not target.exists():
            page = pdf[0]
            width = page.get_size()[0] or THUMB_WIDTH
            image = page.render(scale=THUMB_WIDTH / width).to_pil()
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_suffix('.tmp')
            image.save(tmp, 'WEBP', quality=78)
            tmp.replace(target)
        return count
    finally:
        pdf.close()


class FullText:
    """Rebuilds the index in a daemon thread whenever the set of (path, sha) changes."""

    def __init__(self, target: Path, thumbs: Path | None = None):
        self.target = target
        self.thumbs = thumbs or target.parent / 'thumbs'
        self.lock = threading.Lock()
        self.signature: tuple | None = None
        self.running = False
        self.cache: dict[str, str] = {}  # sha -> text, so unchanged files are never fetched twice
        self.pages: dict[str, int] = {}  # sha -> number of pages (slides)

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
                sha, cover = doc['sha'], self.thumbs / f'{doc["sha"]}.webp'
                needs_cover = doc['extension'] == '.pdf' and (sha not in self.pages or not cover.exists())
                text = self.cache.get(sha)
                if text is None or needs_cover:
                    try:
                        data = fetch(doc['path'], sha)
                        if text is None:
                            text = extract_text(data, doc['extension'])
                        if doc['extension'] == '.pdf':
                            self.pages[sha] = render_cover(data, cover)
                    except Exception:  # noqa: BLE001 — a broken or scanned file just stays without text/cover
                        text = text or ''
                        self.pages.setdefault(sha, 0)
                    self.cache[sha] = text
                if text:
                    out[doc['u']] = text
            self.target.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.target.with_suffix('.tmp')
            tmp.write_text(json.dumps(out, ensure_ascii=False), encoding='utf-8')
            tmp.replace(self.target)  # atomic: the browser never reads a half-written file
            self.signature = signature
        finally:
            self.running = False
