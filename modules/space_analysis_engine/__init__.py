# Space Analysis Engine — Advanced scientific module
# Consumes results from modules.digital_lab.analysis_pipeline
from .space_analyzer import analyze_pipeline_result
from .discovery_engine import run_analysis, compare_results_from_sources, get_discoveries

__all__ = ['analyze_pipeline_result', 'run_analysis', 'compare_results_from_sources', 'get_discoveries']
