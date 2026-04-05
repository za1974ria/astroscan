"""
Space Analysis Engine — Data logger.
Read/write discoveries to data/science_discoveries.json.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path


def _discoveries_path():
    base = os.environ.get('STATION')
    if not base:
        # Resolve project root from this module: .../astro_scan/modules/space_analysis_engine/
        base = str(Path(__file__).resolve().parent.parent.parent)
    return os.path.join(base, 'data', 'science_discoveries.json')


def load_discoveries():
    """Load list of discoveries from JSON file."""
    path = _discoveries_path()
    if not os.path.isfile(path):
        return []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def save_discoveries(discoveries):
    """Save list of discoveries to JSON file."""
    path = _discoveries_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(discoveries, f, indent=2, ensure_ascii=False)


def log_discovery(entry):
    """
    Append one discovery entry.
    entry: dict with at least timestamp, type, summary; optional source, details, classification.
    """
    discoveries = load_discoveries()
    entry['timestamp'] = entry.get('timestamp') or datetime.now(timezone.utc).isoformat()
    entry['id'] = len(discoveries) + 1
    discoveries.append(entry)
    save_discoveries(discoveries)
    return entry
