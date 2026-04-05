"""
Science Archive Engine — Central entry point.
Manages writing data into science_archive; delegates to report_saver, object_cataloger, discovery_saver, archive_indexer.
Does not modify existing modules.
"""
from .report_saver import save_digital_lab_report, list_reports
from .object_cataloger import add_objects, list_objects
from .discovery_saver import log_discovery, list_discoveries
from .archive_indexer import build_index, read_index


def save_report(report_data, source='digital_lab'):
    """Save a report and update index. Returns result from report_saver."""
    result = save_digital_lab_report(report_data, source=source)
    build_index()
    return result


def save_objects(objects, source='archive_api'):
    """Append objects to catalog and update index. Returns result from object_cataloger."""
    result = add_objects(objects, source=source)
    build_index()
    return result


def save_discovery(entry, source='archive_api'):
    """Log a discovery and update index. Returns the stored record."""
    result = log_discovery(entry, source=source)
    build_index()
    return result


def get_archive_index():
    """Return current index (builds if missing)."""
    return read_index()
