# Science Archive Engine — AstroScan automatic archive for scientific outputs
# Does not modify existing modules; receives and stores results via API
from .archive_manager import save_report, save_objects, save_discovery, get_archive_index
from .report_saver import save_digital_lab_report, list_reports
from .object_cataloger import add_objects, list_objects
from .discovery_saver import log_discovery, list_discoveries
from .archive_indexer import build_index, read_index

__all__ = [
    'save_report', 'save_objects', 'save_discovery', 'get_archive_index',
    'save_digital_lab_report', 'list_reports',
    'add_objects', 'list_objects',
    'log_discovery', 'list_discoveries',
    'build_index', 'read_index',
]
