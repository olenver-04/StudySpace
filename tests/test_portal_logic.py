import pytest

from conftest import CATALOG, TREE
from portal_logic import natural_key, parse_materials, safe_filename, upload_path


def test_natural_order():
    assert sorted(['Лекция 10', 'Лекция 2', 'лекция 1'], key=natural_key) == ['лекция 1', 'Лекция 2', 'Лекция 10']


@pytest.mark.parametrize('name', ['../catalog.json', '.env', 'virus.exe', 'x' * 200 + '.pdf'])
def test_bad_filenames_rejected(name):
    with pytest.raises(ValueError):
        upload_path('algo', 'ru', 'lectures', safe_filename(name) if not name.startswith('..') else name)


def test_path_parts_are_stripped():
    assert safe_filename('C:\\Users\\me\\Лекция.pdf') == 'Лекция.pdf'


def test_disabled_language_hidden_and_sorted():
    items = parse_materials(TREE, CATALOG['courses'])
    paths = [m['path'] for m in items]
    assert not any('java/kz' in p for p in paths)
    ru_lectures = [m['title'] for m in items if m['course_id'] == 'algo' and m['lang'] == 'ru' and m['kind'] == 'lectures']
    assert ru_lectures == ['Лекция 2', 'Лекция 10']
