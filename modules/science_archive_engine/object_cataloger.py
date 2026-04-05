"""
Science Archive Engine — Object cataloger.
Store detected objects and maintain a catalog in science_archive/objects/.
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


def _objects_dir():
    return os.path.join(_archive_base(), 'objects')


def _catalog_path():
    return os.path.join(_objects_dir(), 'catalog.jsonl')


def add_objects(objects, source='archive_api'):
    """
    Append detected objects to the catalog.
    objects: list of dicts (e.g. [{"type": "star", "ra": ..., "dec": ...}, ...]).
    """
    obj_dir = _objects_dir()
    os.makedirs(obj_dir, exist_ok=True)
    catalog_path = _catalog_path()
    now = datetime.now(timezone.utc).isoformat()
    added = 0
    with open(catalog_path, 'a', encoding='utf-8') as f:
        for obj in objects:
            if not isinstance(obj, dict):
                continue
            entry = {
                'timestamp': now,
                'source': source,
                **obj,
            }
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')
            added += 1
    return {'added': added, 'timestamp': now}


def list_objects(limit=100):
    """Read recent catalog entries (newest first)."""
    path = _catalog_path()
    if not os.path.isfile(path):
        return []
    lines = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    lines.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    lines.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
    return lines[:limit]
