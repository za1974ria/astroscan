"""
Space Analysis Engine — Discovery engine.
Orchestrates analysis, comparison, and discovery listing.
Consumes digital_lab pipeline results only; does not modify digital_lab.
"""
from .space_analyzer import analyze_pipeline_result
from .image_comparator import compare_results
from .data_logger import load_discoveries


def run_analysis(pipeline_result, source='upload'):
    """
    Run full analysis on a digital_lab pipeline result.
    pipeline_result: dict from modules.digital_lab.analysis_pipeline.run_pipeline
    source: optional label
    Returns: analysis result dict.
    """
    return analyze_pipeline_result(pipeline_result, source=source)


def compare_results_from_sources(result_a, result_b, source_a='source_a', source_b='source_b'):
    """
    Compare two pipeline results (e.g. NASA feed vs telescope feed).
    """
    return compare_results(result_a, result_b, source_a=source_a, source_b=source_b)


def get_discoveries(limit=100):
    """Return logged discoveries from data/science_discoveries.json."""
    discoveries = load_discoveries()
    return list(reversed(discoveries[-limit:])) if discoveries else []
