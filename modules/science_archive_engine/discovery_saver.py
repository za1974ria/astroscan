"""
Science Archive Engine — Discovery saver.
Log discoveries into data/science_archive/discoveries/.
Does not modify Space Analysis Engine; receives discovery payload and stores.
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


def _discoveries_dir():
    return os.path.join(_archive_base(), 'discoveries')


def _discoveries_log_path():
    return os.path.join(_discoveries_dir(), 'discoveries.jsonl')


def log_discovery(entry, source='archive_api'):
    """
    Append one discovery to science_archive/discoveries/discoveries.jsonl.
    entry: dict with optional timestamp, type, summary, details, classification, etc.
    """
    disc_dir = _discoveries_dir()
    os.makedirs(disc_dir, exist_ok=True)
    path = _discoveries_log_path()
    record = {
        'timestamp': entry.get('timestamp') or datetime.now(timezone.utc).isoformat(),
        'source': source,
        **{k: v for k, v in entry.items() if k != 'timestamp'},
    }
    with open(path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(record, ensure_ascii=False) + '\n')
    return record


def list_discoveries(limit=50):
    """List recent discovery entries (newest first)."""
    path = _discoveries_log_path()
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
