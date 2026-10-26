"""Pure catalog and path helpers; no Streamlit dependencies."""
from __future__ import annotations

import re
import unicodedata
from pathlib import PurePosixPath

ALLOWED_EXTENSIONS = {'.pdf', '.pptx', '.ppt', '.docx', '.doc', '.md', '.txt', '.html'}
LANGUAGES = ('ru', 'kz')
KINDS = ('lectures', 'presentations')
_ROOT = 'materials/uploads/'

_CYR = {
    'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'yo','ж':'zh','з':'z','и':'i',
    'й':'y','к':'k','л':'l','м':'m','н':'n','о':'o','п':'p','р':'r','с':'s','т':'t',
    'у':'u','ф':'f','х':'h','ц':'ts','ч':'ch','ш':'sh','щ':'shch','ъ':'','ы':'y',
    'ь':'','э':'e','ю':'yu','я':'ya','ә':'a','ғ':'g','қ':'q','ң':'n','ө':'o',
    'ұ':'u','ү':'u','һ':'h','і':'i',
}


def slugify(text: str) -> str:
    output = ''.join(_CYR.get(c, c) for c in text.lower())
    output = unicodedata.normalize('NFKD', output)
    output = ''.join(c for c in output if not unicodedata.combining(c))
    output = re.sub(r'[^a-z0-9]+', '-', output).strip('-')
    return output[:65]


def valid_slug(value: str) -> bool:
    return bool(re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', value or '')) and len(value) <= 65


def safe_filename(filename: str) -> str:
    # GitHub paths must never be influenced by a user's directory components.
    filename = filename.replace('\\', '/').split('/')[-1].strip()
    filename = re.sub(r'[<>:"|?*\x00-\x1f]', '_', filename)
    filename = filename.replace('..', '_')
    if not filename or filename.startswith('.') or len(filename) > 160:
        raise ValueError('Неподходящее название файла (макс. 160 символов).')
    if PurePosixPath(filename).suffix.lower() not in ALLOWED_EXTENSIONS:
        raise ValueError('Недопустимый формат файла.')
    return filename


def upload_path(course_id: str, lang: str, kind: str, filename: str) -> str:
    if not valid_slug(course_id) or lang not in LANGUAGES or kind not in KINDS:
        raise ValueError('Некорректная дисциплина, язык или тип файла.')
    return f'{_ROOT}{course_id}/{lang}/{kind}/{safe_filename(filename)}'


def is_valid_catalog(config: object) -> bool:
    return isinstance(config, dict) and isinstance(config.get('courses'), list)


def parse_materials(tree: list[dict], courses: list[dict]) -> list[dict]:
    """Index GitHub tree; only explicitly registered courses are visible."""
    accepted = {c['id']: c for c in courses if isinstance(c, dict) and valid_slug(c.get('id', ''))}
    result = []
    for obj in tree:
        if obj.get('type') != 'blob':
            continue
        path = obj.get('path', '')
        if not isinstance(path, str) or not path.startswith(_ROOT):
            continue
        parts = path[len(_ROOT):].split('/')
        if len(parts) == 4:
            course_id, language, kind, filename = parts
            if kind not in KINDS:
                continue
        elif len(parts) == 3:
            course_id, language, filename = parts
            kind = 'lectures' if PurePosixPath(filename).suffix.lower() in {'.md','.txt','.doc','.docx'} or re.search(r'(?i)lekciya|lecture|lektsiya|дәріс|лекция', filename) else 'presentations'
        else:
            continue
        if course_id not in accepted or language not in LANGUAGES:
            continue
        if filename.startswith('.') or PurePosixPath(filename).suffix.lower() not in ALLOWED_EXTENSIONS:
            continue
        stem = PurePosixPath(filename).stem
        stem = re.sub(r'(?i)[_-](ru|kz|kk)$', '', stem)
        title = re.sub(r'[_-]+', ' ', stem).strip()
        result.append({
            'id': path, 'path': path, 'title': title[:1].upper()+title[1:],
            'course_id': course_id, 'course': accepted[course_id],
            'lang': language, 'kind': kind, 'filename': filename,
            'extension': PurePosixPath(filename).suffix.lower(),
            'size': obj.get('size', 0), 'sha': obj.get('sha', ''),
        })
    return sorted(result, key=lambda i: (i['course_id'], i['title'].casefold()))


def display_course(course: dict, lang: str) -> str:
    return course.get('title_kz' if lang == 'kz' else 'title_ru') or course.get('title_ru') or course.get('id', '')


def human_size(size: int) -> str:
    return f'{size/(1024*1024):.1f} МБ' if size >= 1024*1024 else f'{max(1,round(size/1024))} КБ'
