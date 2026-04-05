"""
Space Analysis Engine — Space analyzer.
Analyzes results produced by the digital_lab pipeline.
Detects anomalies and unusual structures (no modification of digital_lab).
"""
from .event_classifier import classify_objects
from .data_logger import log_discovery, load_discoveries


def analyze_pipeline_result(pipeline_result, source='unknown'):
    """
    Analyze a pipeline result from modules.digital_lab.analysis_pipeline.run_pipeline.
    pipeline_result: dict (output of digital_lab run_pipeline)
    source: optional label (e.g. 'nasa_apod', 'telescope_feed')
    Returns: dict with analysis, classifications, anomalies_detected, discoveries_logged.
    """
    if pipeline_result.get('error'):
        return {
            'success': False,
            'error': pipeline_result['error'],
            'classifications': [],
            'anomalies_detected': [],
            'discoveries_logged': 0,
        }

    classifications = classify_objects(pipeline_result)
    anomalies = pipeline_result.get('anomalies') or {}
    anomaly_list = anomalies.get('anomalies') or []

    # Unusual structures: many sources, or high anomaly count
    discoveries_logged = 0
    if anomaly_list and len(anomaly_list) >= 2:
        entry = {
            'type': 'multiple_anomalies',
            'source': source,
            'summary': f"{len(anomaly_list)} anomalies in pipeline result",
            'details': {'anomaly_count': len(anomaly_list), 'classifications_count': len(classifications)},
        }
        log_discovery(entry)
        discoveries_logged += 1

    stars = pipeline_result.get('stars') or []
    objects = pipeline_result.get('objects') or []
    if len(stars) > 300 and discoveries_logged == 0:
        entry = {
            'type': 'crowded_field',
            'source': source,
            'summary': f"Very crowded field: {len(stars)} point sources",
            'details': {'star_count': len(stars), 'object_count': len(objects)},
        }
        log_discovery(entry)
        discoveries_logged += 1

    return {
        'success': True,
        'source': source,
        'classifications': classifications,
        'anomalies_detected': anomaly_list,
        'classification_count': len(classifications),
        'discoveries_logged': discoveries_logged,
    }
