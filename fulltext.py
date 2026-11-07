"""Background library index: searchable text, slide counts, covers and accent colours. No Streamlit imports.

One pass over the materials (each file is fetched once) produces:
  * static/fulltext.json      url -> text, pages separated by PAGE_BREAK, searched in the browser (fx.js);
  * static/thumbs/<sha>.webp  first page of each PDF, used as the material's cover;
  * FullText.pages / .colors  sha -> slide count / accent colour taken from the cover.
Full-size slides for the viewer are rendered on demand by render_pages (static/slides/<sha>/).
"""
from __future__ import annotations

import colorsys
import io
import json
import re
import threading
from pathlib import Path
from typing import Callable

import pypdfium2 as pdfium
from PIL import Image
from pypdf import PdfReader

TEXT_LIMIT = 40_000  # characters kept per document; enough for lectures, keeps the JSON small
THUMB_WIDTH = 640    # px; covers are shown at most ~400 px wide, 2x for sharp screens
SLIDE_WIDTH = 1600   # px; viewer slides, sharp on a projector
STRIP_WIDTH = 240    # px; viewer filmstrip
PAGE_BREAK = '\f'    # between pages in the text index, so search can tell which slide matched
SEARCHABLE = {'.pdf', '.md', '.txt'}


def extract_text(data: bytes, extension: str) -> str:
    if extension == '.pdf':
        pages, size = [], 0
        for page in PdfReader(io.BytesIO(data)).pages:
            text = re.sub(r'\s+', ' ', page.extract_text() or '').strip()
            pages.append(text)
            size += len(text)
            if size > TEXT_LIMIT:
                break
        return PAGE_BREAK.join(pages)[:TEXT_LIMIT].strip(PAGE_BREAK)
    if extension in ('.md', '.txt'):
        return re.sub(r'\s+', ' ', data.decode('utf-8-sig', errors='replace')).strip()[:TEXT_LIMIT]
    return ''


def save_webp(image: Image.Image, target: Path, quality: int = 78) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix('.tmp')
    image.save(tmp, 'WEBP', quality=quality)
    tmp.replace(target)  # atomic: the browser never gets half a file


def dominant_color(image: Image.Image) -> str | None:
    """Hue of the most prominent coloured area (dark backgrounds and greys skipped), made vivid, as #rrggbb.

    Thin accent lines vanish when an image is averaged down, so the cover is quantized at 160x90 into
    16 colours; the winner's hue is then brought to one brightness so every course accent is equally clear.
    """
    small = image.convert('RGB').resize((160, 90), Image.Resampling.NEAREST)
    quantized = small.quantize(colors=16)
    palette = quantized.getpalette() or []
    best = None
    # First pass: bright coloured areas. Fallback: the hue of a dark but coloured background (e.g. navy).
    for min_value in (.3, .1):
        best_score = 0.0
        for count, index in quantized.getcolors() or []:
            r, g, b = (c / 255 for c in palette[index * 3:index * 3 + 3])
            hue, saturation, value = colorsys.rgb_to_hsv(r, g, b)
            if saturation < .3 or value < min_value:
                continue
            score = count * saturation ** 2 * value
            if score > best_score:
                best, best_score = hue, score
        if best is not None:
            break
    if best is None:
        return None
    r, g, b = colorsys.hsv_to_rgb(best, .72, .82)
    return f'#{round(r * 255):02x}{round(g * 255):02x}{round(b * 255):02x}'


def render_cover(data: bytes, target: Path) -> tuple[int, str | None]:
    """Writes the first page as WebP if missing; returns (page count, accent colour)."""
    pdf = pdfium.PdfDocument(data)
    try:
        count = len(pdf)
        if not count:
            return 0, None
        if target.exists():
            with Image.open(target) as existing:
                return count, dominant_color(existing)
        page = pdf[0]
        image = page.render(scale=THUMB_WIDTH / (page.get_size()[0] or THUMB_WIDTH)).to_pil()
        save_webp(image, target)
        return count, dominant_color(image)
    finally:
        pdf.close()


def render_pages(data: bytes, folder: Path) -> int:
    """Viewer images: <n>.webp (full size) and t<n>.webp (filmstrip), 1-based; existing files are kept."""
    pdf = pdfium.PdfDocument(data)
    try:
        count = len(pdf)
        for n in range(1, count + 1):
            big, small = folder / f'{n}.webp', folder / f't{n}.webp'
            if big.exists() and small.exists():
                continue
            page = pdf[n - 1]
            image = page.render(scale=SLIDE_WIDTH / (page.get_size()[0] or SLIDE_WIDTH)).to_pil()
            save_webp(image, big, quality=82)
            image.thumbnail((STRIP_WIDTH, STRIP_WIDTH * 2))
            save_webp(image, small, quality=72)
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
        self.colors: dict[str, str] = {}  # sha -> accent colour of the cover

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
                            self.pages[sha], color = render_cover(data, cover)
                            if color:
                                self.colors[sha] = color
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
