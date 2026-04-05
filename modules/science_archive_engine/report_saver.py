"""
Science Archive Engine — Report saver.
Save Digital Lab reports as JSON with timestamped filenames.
Does not modify Digital Lab; receives report payload and writes to science_archive.
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


def _reports_dir():
    return os.path.join(_archive_base(), 'reports')


def save_digital_lab_report(report_data, source='digital_lab'):
    """
    Save a Digital Lab–style report to science_archive/reports/.
    report_data: dict (e.g. pipeline result or report subset).
    Filename format: report_YYYYMMDD_HHMMSS.json
    """
    reports_dir = _reports_dir()
    os.makedirs(reports_dir, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    filename = f'report_{ts}.json'
    path = os.path.join(reports_dir, filename)
    payload = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'source': source,
        'report': report_data,
    }
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return {'path': path, 'filename': filename, 'timestamp': payload['timestamp']}


def list_reports(limit=50):
    """List recent report filenames and metadata (no full content)."""
    reports_dir = _reports_dir()
    if not os.path.isdir(reports_dir):
        return []
    out = []
    for name in sorted(os.listdir(reports_dir), reverse=True):
        if not name.endswith('.json'):
            continue
        path = os.path.join(reports_dir, name)
        try:
            stat = os.stat(path)
            out.append({
                'filename': name,
                'modified': datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            })
        except OSError:
            continue
        if len(out) >= limit:
            break
    return out
