"""
Science Archive Engine — Archive indexer.
Build and maintain index file: data/science_archive/index.json
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path


def _archive_base():
    base = os.environ.get('STATION')
    if not base:
        base = str(Path(__file__).resolve().parent.parent.parent)
    return os.path.join(base, 'data', 'science_archive')


def _index_path():
    return os.path.join(_archive_base(), 'index.json')


def _count_reports():
    reports_dir = os.path.join(_archive_base(), 'reports')
    if not os.path.isdir(reports_dir):
        return 0
    return sum(1 for n in os.listdir(reports_dir) if n.endswith('.json'))


def _count_objects():
    path = os.path.join(_archive_base(), 'objects', 'catalog.jsonl')
    if not os.path.isfile(path):
        return 0
    with open(path, 'r', encoding='utf-8') as f:
        return sum(1 for line in f if line.strip())


def _count_discoveries():
    path = os.path.join(_archive_base(), 'discoveries', 'discoveries.jsonl')
    if not os.path.isfile(path):
        return 0
    with open(path, 'r', encoding='utf-8') as f:
        return sum(1 for line in f if line.strip())


def build_index():
    """Build or refresh index.json with counts and last_updated."""
    base = _archive_base()
    os.makedirs(base, exist_ok=True)
    index = {
        'last_updated': datetime.now(timezone.utc).isoformat(),
        'reports_count': _count_reports(),
        'objects_count': _count_objects(),
        'discoveries_count': _count_discoveries(),
    }
    path = _index_path()
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(index, f, indent=2)
    return index


def read_index():
    """Read index.json; if missing, build it and return."""
    path = _index_path()
    if not os.path.isfile(path):
        return build_index()
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return build_index()
