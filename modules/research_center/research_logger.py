"""
Research Center — Research logger.
Store JSON logs of detected events and summaries in data/research_logs/.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path


def _logs_dir():
    base = os.environ.get('STATION')
    if not base:
        base = str(Path(__file__).resolve().parent.parent.parent)
    return os.path.join(base, 'data', 'research_logs')


def write_log(kind, data):
    """
    Append a JSON log entry. kind: e.g. 'event', 'summary', 'solar', 'neo'
    data: dict (will get timestamp and kind added)
    """
    log_dir = _logs_dir()
    os.makedirs(log_dir, exist_ok=True)
    entry = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'kind': kind,
        **data,
    }
    path = os.path.join(log_dir, f'{kind}.jsonl')
    with open(path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + '\n')
    return entry


def list_logs(kind=None, limit=50):
    """Read recent log entries. kind: optional filter (event, summary, solar, neo)."""
    log_dir = _logs_dir()
    if not os.path.isdir(log_dir):
        return []
    pattern = f'{kind}.jsonl' if kind else '*.jsonl'
    import glob
    files = glob.glob(os.path.join(log_dir, pattern))
    lines = []
    for fp in files:
        try:
            with open(fp, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        lines.append(json.loads(line))
        except (IOError, json.JSONDecodeError):
            continue
    lines.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
    return lines[:limit]
